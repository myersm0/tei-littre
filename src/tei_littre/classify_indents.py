"""
Phase 3: Classify indent blocks into semantic roles.

Tier A — deterministic: presence of specific XML tags.
Tier B — heuristic: text patterns in stripped content.
Tier C — LLM-assisted: deferred to a separate batch script.
"""

import re
from tei_littre.model import Entry, Indent, IndentRole, ClassificationMethod


def strip_tags(markup: str) -> str:
	return re.sub(r"<[^>]+>", "", markup).strip()


# --- Tier A: deterministic tag-based classification ---

def classify_deterministic(indent: Indent) -> bool:
	c = indent.content

	if '<semantique type="indicateur">Fig.' in c:
		indent.role = IndentRole.figurative
		indent.classification_method = ClassificationMethod.deterministic
		indent.classification_confidence = 1.0
		return True

	if '<semantique type="domaine">' in c:
		indent.role = IndentRole.domain
		indent.classification_method = ClassificationMethod.deterministic
		indent.classification_confidence = 1.0
		return True

	if "<nature>" in c:
		indent.role = IndentRole.nature_label
		indent.classification_method = ClassificationMethod.deterministic
		indent.classification_confidence = 1.0
		return True

	if "<a ref=" in c and len(strip_tags(c)) < 120:
		plain = strip_tags(c)
		if re.match(r"^(voy\.|V\.|Voy\.|voyez)", plain, re.IGNORECASE):
			indent.role = IndentRole.cross_reference
			indent.classification_method = ClassificationMethod.deterministic
			indent.classification_confidence = 1.0
			return True
		if re.search(r",\s*voy\.\s*$", plain):
			indent.role = IndentRole.cross_reference
			indent.classification_method = ClassificationMethod.deterministic
			indent.classification_confidence = 0.95
			return True

	return False


# --- Tier B: heuristic text patterns ---

register_pattern = re.compile(
	r"^(Populaire|Familière|Familièrement|Vulgaire|Vulgairement|"
	r"Triviale|Trivialemen|Bas|Ironiquement|Plaisamment|Burlesque|"
	r"Poétiquement|Par euphémisme|Par exagération|Par ironie|"
	r"Par dérision|Par extension|Par analogie|Par métaphore|"
	r"Par plaisanterie|Par antiphrase|Néologisme)",
	re.IGNORECASE,
)

proverb_pattern = re.compile(
	r"^(Prov\.|Proverbe|Proverbialement)",
	re.IGNORECASE,
)

voice_transition_pattern = re.compile(
	r"^(V\.\s*(n|a|réfl)|Se\s+conjugue|Absolument|"
	r"Substantivement|Adverbialement|Adjectivement|"
	r"Intransitivement|Neutralement|Impersonnellement|"
	r"Activement|Au\s+pluriel|Au\s+féminin|Au\s+singulier|"
	r"Au\s+masc|Au\s+fém|Avec\s+un\s+nom\s+de)",
)

locution_intro_pattern = re.compile(
	r"^(<exemple>|Loc\.\s|Locution)",
	re.IGNORECASE,
)

definition_like_pattern = re.compile(
	r"^(Se dit|Il se dit|On dit|On appelle|Se disait|"
	r"Qui se dit|Il s'est dit|Celui qui|Celle qui|"
	r"Ce qui|Chose qui|Action de|État de|Qualité de|"
	r"Nom (donné|que l'on donne)|Terme (de|d')|"
	r"En termes? (de|d'))",
	re.IGNORECASE,
)

cross_ref_heuristic = re.compile(
	r"^(Il est|C'est|On dit|Se dit).{0,40}<a ref=",
)


def classify_heuristic(indent: Indent) -> bool:
	c = indent.content
	plain = strip_tags(c)

	if proverb_pattern.match(plain):
		indent.role = IndentRole.proverb
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.9
		return True

	if register_pattern.match(plain):
		indent.role = IndentRole.register_label
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.85
		return True

	if voice_transition_pattern.match(plain):
		indent.role = IndentRole.voice_transition
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.85
		return True

	if "<exemple>" in c or locution_intro_pattern.match(c):
		indent.role = IndentRole.locution
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.8
		return True

	if "<a ref=" in c and cross_ref_heuristic.match(c):
		indent.role = IndentRole.cross_reference
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.8
		return True

	if definition_like_pattern.match(plain):
		indent.role = IndentRole.elaboration
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.75
		return True

	if re.match(r"^Fig\.", plain):
		indent.role = IndentRole.figurative
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.9
		return True

	# Locution heuristic: short text with comma, looks like a phrase
	if (
		len(plain) < 100
		and not indent.citations
		and "," in plain
		and re.match(r"^[A-Z]", plain)
		and not re.match(r"^(Il|On|Se|C'|Qui|Que|Ce|La|Le|Les|Un|Une|Des) ", plain)
	):
		indent.role = IndentRole.locution
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.6
		return True

	# Fallback: content with citations is a continuation (sub-sense)
	if indent.citations:
		indent.role = IndentRole.continuation
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.5
		return True

	# Remaining text blocks are elaborations
	if len(plain) > 20:
		indent.role = IndentRole.elaboration
		indent.classification_method = ClassificationMethod.heuristic
		indent.classification_confidence = 0.4
		return True

	return False


def classify_indent(indent: Indent) -> None:
	if classify_deterministic(indent):
		return
	if classify_heuristic(indent):
		return
	for child in indent.children:
		classify_indent(child)


def classify_entry(entry: Entry) -> None:
	for variante in entry.body_variantes:
		for indent in variante.indents:
			classify_indent(indent)


def classify_all(entries: list[Entry]) -> dict[str, int]:
	counts: dict[str, int] = {}
	for entry in entries:
		classify_entry(entry)
		for variante in entry.body_variantes:
			for indent in variante.indents:
				role = indent.role.value
				counts[role] = counts.get(role, 0) + 1

	return counts
