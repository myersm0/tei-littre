from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class RubriqueType(Enum):
	historique = "HISTORIQUE"
	etymologie = "ÉTYMOLOGIE"
	remarque = "REMARQUE"
	synonyme = "SYNONYME"
	proverbes = "PROVERBES"
	supplement = "SUPPLÉMENT AU DICTIONNAIRE"


class SemantiqueType(Enum):
	domaine = "domaine"
	indicateur = "indicateur"
	untyped = ""


class IndentRole(Enum):
	"""Assigned during enrichment (Phase 3). Unknown until classified."""
	unknown = "unknown"
	figurative = "figurative"
	domain = "domain"
	nature_label = "nature_label"
	cross_reference = "cross_reference"
	register_label = "register_label"
	proverb = "proverb"
	voice_transition = "voice_transition"
	locution = "locution"
	constructional = "constructional"
	elaboration = "elaboration"
	continuation = "continuation"


class ClassificationMethod(Enum):
	deterministic = "deterministic"
	heuristic = "heuristic"
	llm = "llm"
	manual = "manual"


# --- Mixed content ---
# Stored as lightly normalized XML fragment strings.
# Inline tags preserved: <i>, <semantique>, <a>, <exemple>, <i lang="la">.
# Each emitter interprets these for its own output format.
Markup = str


# --- Citation ---

@dataclass
class Citation:
	text: Markup
	author: str = ""
	reference: str = ""
	hide: str = ""
	resolved_author: str = ""


# --- Indent (the overloaded element) ---

@dataclass
class Indent:
	content: Markup
	citations: list[Citation] = field(default_factory=list)
	children: list[Indent] = field(default_factory=list)
	role: IndentRole = IndentRole.unknown
	classification_method: ClassificationMethod | None = None
	classification_confidence: float | None = None
	canonical_form: str = ""


# --- Variante (sense) ---

@dataclass
class Variante:
	content: Markup
	num: int | None = None
	is_resume: bool = False
	is_supplement: bool = False
	citations: list[Citation] = field(default_factory=list)
	indents: list[Indent] = field(default_factory=list)
	rubriques: list[Rubrique] = field(default_factory=list)


# --- Rubrique (back-matter sections) ---

@dataclass
class Rubrique:
	type: RubriqueType
	content: Markup
	citations: list[Citation] = field(default_factory=list)
	indents: list[Indent] = field(default_factory=list)


# --- Entry ---

@dataclass
class Entry:
	headword: str
	xml_id: str = ""
	homograph_index: int | None = None
	is_supplement: bool = False
	pronunciation: str = ""
	pos: str = ""
	body_variantes: list[Variante] = field(default_factory=list)
	rubriques: list[Rubrique] = field(default_factory=list)
	resume_text: Markup = ""
	source_letter: str = ""
