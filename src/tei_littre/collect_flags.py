"""
Collect review flags from enriched entries.

Flags are generated post-hoc by scanning the enriched model,
rather than being emitted inline during processing. This keeps
the enrichment phases simple and the flagging logic centralized.
"""

import random
from collections import defaultdict
from tei_littre.model import (
	Entry, ReviewFlag, IndentRole, ClassificationMethod,
)
from tei_littre.classify_indents import strip_tags


low_confidence_threshold = 0.5
low_confidence_roles = {
	IndentRole.locution,
	IndentRole.figurative,
	IndentRole.domain,
	IndentRole.proverb,
	IndentRole.cross_reference,
	IndentRole.register_label,
	IndentRole.voice_transition,
	IndentRole.nature_label,
}
large_scope_threshold = 15
calibration_per_bucket = 5
calibration_seed = 42


def collect_flags(entries: list[Entry]) -> list[ReviewFlag]:
	flags: list[ReviewFlag] = []
	flags.extend(_flag_low_confidence(entries))
	flags.extend(_flag_skipped_locutions(entries))
	flags.extend(_flag_scope_decisions(entries))
	flags.extend(_flag_calibration_sample(entries))
	return flags


def _flag_low_confidence(entries: list[Entry]) -> list[ReviewFlag]:
	flags = []
	for entry in entries:
		for var in _all_variantes(entry):
			for i, indent in enumerate(var.indents):
				conf = indent.classification_confidence
				if conf is not None and conf <= low_confidence_threshold and indent.role in low_confidence_roles:
					neighbors = _indent_neighbors(var.indents, i)
					flags.append(ReviewFlag(
						entry_id=entry.xml_id,
						headword=entry.headword,
						phase="phase3",
						flag_type="low_confidence",
						reason=f"confidence={conf:.2f}, role={indent.role.value}",
						context={
							"variante_num": var.num,
							"indent_content": indent.content[:200],
							"role": indent.role.value,
							"confidence": conf,
							"method": indent.classification_method.value if indent.classification_method else None,
							**neighbors,
						},
					))
	return flags


def _flag_skipped_locutions(entries: list[Entry]) -> list[ReviewFlag]:
	flags = []
	for entry in entries:
		for var in _all_variantes(entry):
			for indent in var.indents:
				if indent.role == IndentRole.locution and not indent.canonical_form:
					flags.append(ReviewFlag(
						entry_id=entry.xml_id,
						headword=entry.headword,
						phase="phase4",
						flag_type="skipped_locution",
						reason="no canonical form extracted",
						context={
							"variante_num": var.num,
							"indent_content": indent.content[:200],
						},
					))
	return flags


def _flag_scope_decisions(entries: list[Entry]) -> list[ReviewFlag]:
	flags = []
	for entry in entries:
		for var in entry.body_variantes:
			if not var.transition_type:
				continue
			num_scoped = len(var.sub_variantes)
			flag_type = "large_scope" if num_scoped > large_scope_threshold else "scope_decision"
			flags.append(ReviewFlag(
				entry_id=entry.xml_id,
				headword=entry.headword,
				phase="phase5",
				flag_type=flag_type,
				reason=f"{var.transition_type} scope, {num_scoped} variantes",
				context={
					"transition_content": strip_tags(var.transition_content)[:100],
					"scope_type": var.transition_type,
					"transition_form": var.transition_form,
					"transition_pos": var.transition_pos,
					"num_scoped": num_scoped,
					"first_scoped": strip_tags(var.sub_variantes[0].content)[:80] if var.sub_variantes else "",
					"last_scoped": strip_tags(var.sub_variantes[-1].content)[:80] if var.sub_variantes else "",
				},
			))
			# Also flag nature_labels that scoped many children
			for sub in var.sub_variantes:
				_flag_large_intra(entry, sub, flags)
		for var in entry.body_variantes:
			_flag_large_intra(entry, var, flags)
	return flags


def _flag_large_intra(entry: Entry, var, flags: list[ReviewFlag]) -> None:
	for indent in var.indents:
		if indent.role in (IndentRole.nature_label, IndentRole.voice_transition) and len(indent.children) > 5:
			flags.append(ReviewFlag(
				entry_id=entry.xml_id,
				headword=entry.headword,
				phase="phase5",
				flag_type="large_intra_scope",
				reason=f"{indent.role.value} scoped {len(indent.children)} children",
				context={
					"variante_num": var.num,
					"indent_content": strip_tags(indent.content)[:100],
					"num_children": len(indent.children),
				},
			))


def _flag_calibration_sample(entries: list[Entry]) -> list[ReviewFlag]:
	buckets: dict[tuple[str, str], list[tuple[Entry, object, int, object]]] = defaultdict(list)
	for entry in entries:
		for var in _all_variantes(entry):
			for i, indent in enumerate(var.indents):
				if indent.classification_method is None:
					continue
				key = (indent.role.value, indent.classification_method.value)
				buckets[key].append((entry, var, i, indent))

	rng = random.Random(calibration_seed)
	flags = []
	for (role, method), items in sorted(buckets.items()):
		sample_size = min(calibration_per_bucket, len(items))
		sample = rng.sample(items, sample_size)
		for entry, var, i, indent in sample:
			neighbors = _indent_neighbors(var.indents, i)
			flags.append(ReviewFlag(
				entry_id=entry.xml_id,
				headword=entry.headword,
				phase="calibration",
				flag_type="calibration_sample",
				reason=f"sample from {role}/{method} (n={len(items)})",
				context={
					"variante_num": var.num,
					"indent_content": indent.content[:200],
					"role": role,
					"confidence": indent.classification_confidence,
					"method": method,
					"bucket_size": len(items),
					**neighbors,
				},
			))
	return flags


def _all_variantes(entry: Entry):
	for var in entry.body_variantes:
		yield var
		yield from var.sub_variantes


def _indent_neighbors(indents: list, index: int) -> dict:
	result = {}
	if index > 0:
		result["prev_indent"] = strip_tags(indents[index - 1].content)[:100]
	if index < len(indents) - 1:
		result["next_indent"] = strip_tags(indents[index + 1].content)[:100]
	return result
