"""
Phase 4: Extract canonical forms from locution indents.

Populates indent.canonical_form with the locution phrase,
separating it from the gloss/definition.
"""

import re
from tei_littre.model import Entry, Indent, IndentRole, ClassificationMethod
from tei_littre.classify_indents import strip_tags


exemple_pattern = re.compile(r"<exemple>(.*?)</exemple>")

reflexive_pattern = re.compile(
	r"^S'[A-ZÉÈÊÀÂÎÏÔÙÛÜÇ].*,\s*v\.\s*réfl",
)

gloss_boundary = re.compile(
	r"^(se dit|se disait|il se dit|on dit|signifie|c'est-à-dire|c\.-à-d\.)",
	re.IGNORECASE,
)


def extract_locution(indent: Indent) -> None:
	if indent.role != IndentRole.locution:
		return

	plain = strip_tags(indent.content)

	if reflexive_pattern.match(plain):
		indent.role = IndentRole.voice_transition
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.9
		return

	match = exemple_pattern.search(indent.content)
	if match:
		indent.canonical_form = match.group(1).strip()
		return

	if "," not in plain:
		return

	form, gloss = plain.split(",", 1)
	form = form.strip()
	if len(form) > 60:
		return
	indent.canonical_form = form


def extract_all(entries: list[Entry]) -> dict[str, int]:
	extracted = 0
	reclassified = 0
	skipped = 0

	for entry in entries:
		for variante in entry.body_variantes:
			for indent in variante.indents:
				if indent.role != IndentRole.locution:
					continue
				old_role = indent.role
				extract_locution(indent)
				if indent.role != old_role:
					reclassified += 1
				elif indent.canonical_form:
					extracted += 1
				else:
					skipped += 1

	print(f"  Extracted canonical forms: {extracted}")
	print(f"  Reclassified to voice_transition: {reclassified}")
	print(f"  Skipped (no clear form): {skipped}")
	return {"extracted": extracted, "reclassified": reclassified, "skipped": skipped}
