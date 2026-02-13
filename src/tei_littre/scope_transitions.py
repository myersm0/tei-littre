"""
Phase 5: Resolve the forward scope of grammatical transitions.

Transitions (voice_transition, nature_label) are labels with implicit
forward scope. This pass determines that scope and restructures the
model accordingly.

Three scope outcomes:
  strong  → new form + POS → nested sub-entry scoping following variantes
  medium  → usage partition → sense group scoping following variantes
  intra   → indent-level grouping within a variante
  zero    → annotation only (terminal / solitary, no restructuring)
"""

import re
from dataclasses import dataclass, field
from tei_littre.model import Entry, Variante, Indent, IndentRole
from tei_littre.classify_indents import strip_tags


strong_transition_pattern = re.compile(
	r"^(S'[A-ZÉÈÊÀÂÎÏÔÙÛÜÇ].+),\s+(v\.\s*.+)"
)

form_pos_pattern = re.compile(
	r"^([A-ZÉÈÊÀÂÎÏÔÙÛÜÇ][A-ZÉÈÊÀÂÎÏÔÙÛÜÇ '-]+),\s+"
	r"(v\.\s*(?:n|a|réfl)|s\.\s*[mf]|adj)\b"
)

pos_pattern = re.compile(
	r"\b(v\.\s*(?:n|a|réfl)|s\.\s*[mf]|adj)\b",
	re.IGNORECASE,
)


@dataclass
class ScopeLog:
	strong_scoped: int = 0
	medium_scoped: int = 0
	intra_grouped: int = 0
	zero_scope: int = 0
	ambiguous: list[str] = field(default_factory=list)


def parse_strong_transition(plain: str) -> tuple[str, str] | None:
	match = strong_transition_pattern.match(plain)
	if match:
		return match.group(1).strip(), match.group(2).strip()
	match = form_pos_pattern.match(plain)
	if match:
		return match.group(1).strip(), match.group(2).strip()
	return None


def scope_intra_variante(variante: Variante, log: ScopeLog) -> None:
	"""Group indents after a transition into its children."""
	indents = variante.indents
	if len(indents) < 2:
		return

	new_indents: list[Indent] = []
	i = 0
	while i < len(indents):
		indent = indents[i]
		if indent.role in (IndentRole.nature_label, IndentRole.voice_transition):
			if i < len(indents) - 1:
				followers = []
				j = i + 1
				while j < len(indents):
					if indents[j].role in (IndentRole.nature_label, IndentRole.voice_transition):
						break
					followers.append(indents[j])
					j += 1
				if followers:
					indent.children.extend(followers)
					log.intra_grouped += len(followers)
					new_indents.append(indent)
					i = j
					continue
		new_indents.append(indent)
		i += 1

	variante.indents = new_indents


def scope_inter_variante(entry: Entry, log: ScopeLog) -> None:
	"""Scope transitions at variante boundaries into container variantes."""
	body = entry.body_variantes
	if not body:
		return

	new_body: list[Variante] = []
	i = 0

	while i < len(body):
		var = body[i]

		if not var.indents or var.indents[-1].role != IndentRole.voice_transition:
			new_body.append(var)
			i += 1
			continue

		transition = var.indents[-1]

		if transition.citations:
			new_body.append(var)
			i += 1
			continue
		plain = strip_tags(transition.content)
		remaining = body[i + 1:]

		if not remaining:
			log.zero_scope += 1
			new_body.append(var)
			i += 1
			continue

		parsed = parse_strong_transition(plain)

		# Find scope end: next inter-variante transition or end of entry
		scope_end = len(remaining)
		for k, future_var in enumerate(remaining):
			if not future_var.indents:
				continue
			last_indent = future_var.indents[-1]
			if last_indent.role == IndentRole.voice_transition and not last_indent.citations:
				scope_end = k
				break

		if scope_end == 0:
			log.zero_scope += 1
			new_body.append(var)
			i += 1
			continue

		scoped = remaining[:scope_end]

		# Remove transition indent from the source variante
		var.indents = var.indents[:-1]
		new_body.append(var)

		container = Variante(content="")
		container.transition_content = transition.content
		container.sub_variantes = scoped

		if parsed:
			container.transition_type = "strong"
			container.transition_form = parsed[0]
			container.transition_pos = parsed[1]
			log.strong_scoped += len(scoped)
		else:
			container.transition_type = "medium"
			container.transition_content = transition.content
			log.medium_scoped += len(scoped)

		if len(scoped) > 15:
			log.ambiguous.append(
				f"{entry.headword}: {plain[:50]} scopes {len(scoped)} variantes"
			)

		new_body.append(container)
		i += 1 + scope_end

	entry.body_variantes = new_body


def scope_all(entries: list[Entry]) -> ScopeLog:
	log = ScopeLog()

	for entry in entries:
		scope_inter_variante(entry, log)
		for var in entry.body_variantes:
			scope_intra_variante(var, log)
			for sub in var.sub_variantes:
				scope_intra_variante(sub, log)

	print(f"  Strong-scoped variantes (nested entry): {log.strong_scoped}")
	print(f"  Medium-scoped variantes (usage group): {log.medium_scoped}")
	print(f"  Intra-variante grouped indents: {log.intra_grouped}")
	print(f"  Zero-scope transitions (annotation): {log.zero_scope}")
	if log.ambiguous:
		print(f"  Ambiguous ({len(log.ambiguous)}):")
		for msg in log.ambiguous:
			print(f"    {msg}")

	return log
