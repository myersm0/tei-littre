"""
Phase 7b: Emit SQLite database from the enriched internal model.

Tables:
  entries        — one row per headword
  senses         — flattened hierarchy (variantes, indents, children)
  citations      — linked to senses
  locutions      — canonical forms for locution senses
  rubriques      — etymology, historical notes, remarks, etc.
  review_queue   — flagged items for human/LLM review

FTS5 virtual tables:
  senses_fts     — full-text search on definitions
  citations_fts  — full-text search on citation text
"""

import json
import sqlite3
import re
from tei_littre.model import (
	Entry, Variante, Indent, Citation, Rubrique,
	RubriqueType, IndentRole, ReviewFlag,
)
from tei_littre.classify_indents import strip_tags


schema = """
CREATE TABLE entries (
	entry_id TEXT PRIMARY KEY,
	headword TEXT NOT NULL,
	homograph_index INTEGER,
	pronunciation TEXT,
	pos TEXT,
	is_supplement INTEGER DEFAULT 0,
	source_letter TEXT
);

CREATE TABLE senses (
	sense_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL REFERENCES entries(entry_id),
	parent_sense_id INTEGER REFERENCES senses(sense_id),
	num INTEGER,
	indent_id TEXT,
	xml_id TEXT,
	sense_type TEXT NOT NULL DEFAULT 'sense',
	role TEXT,
	content_plain TEXT,
	content_markup TEXT,
	is_supplement INTEGER DEFAULT 0,
	transition_type TEXT,
	transition_form TEXT,
	transition_pos TEXT,
	depth INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE citations (
	citation_id INTEGER PRIMARY KEY AUTOINCREMENT,
	sense_id INTEGER NOT NULL REFERENCES senses(sense_id),
	text_plain TEXT,
	text_markup TEXT,
	author TEXT,
	resolved_author TEXT,
	reference TEXT,
	is_hidden INTEGER DEFAULT 0
);

CREATE TABLE locutions (
	sense_id INTEGER PRIMARY KEY REFERENCES senses(sense_id),
	canonical_form TEXT NOT NULL
);

CREATE TABLE rubriques (
	rubrique_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL REFERENCES entries(entry_id),
	rubrique_type TEXT NOT NULL,
	content_plain TEXT,
	content_markup TEXT
);

CREATE TABLE review_queue (
	review_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL,
	headword TEXT NOT NULL,
	phase TEXT NOT NULL,
	flag_type TEXT NOT NULL,
	reason TEXT,
	context TEXT,
	resolution TEXT,
	resolved_by TEXT
);

CREATE INDEX idx_senses_entry ON senses(entry_id);
CREATE INDEX idx_senses_parent ON senses(parent_sense_id);
CREATE INDEX idx_senses_role ON senses(role);
CREATE INDEX idx_senses_indent_id ON senses(indent_id);
CREATE INDEX idx_senses_xml_id ON senses(xml_id);
CREATE INDEX idx_citations_sense ON citations(sense_id);
CREATE INDEX idx_citations_author ON citations(resolved_author);
CREATE INDEX idx_locutions_form ON locutions(canonical_form);
CREATE INDEX idx_rubriques_entry ON rubriques(entry_id);
CREATE INDEX idx_review_phase ON review_queue(phase);
CREATE INDEX idx_review_type ON review_queue(flag_type);
CREATE INDEX idx_review_unresolved ON review_queue(resolution) WHERE resolution IS NULL OR resolution = '';
"""

fts_schema = """
CREATE VIRTUAL TABLE senses_fts USING fts5(
	content_plain,
	content='senses',
	content_rowid='sense_id'
);

INSERT INTO senses_fts(rowid, content_plain)
	SELECT sense_id, content_plain FROM senses WHERE content_plain IS NOT NULL;

CREATE VIRTUAL TABLE citations_fts USING fts5(
	text_plain,
	content='citations',
	content_rowid='citation_id'
);

INSERT INTO citations_fts(rowid, text_plain)
	SELECT citation_id, text_plain FROM citations WHERE text_plain IS NOT NULL;
"""


def _sense_type_for_indent(indent: Indent) -> str:
	match indent.role:
		case IndentRole.figurative:
			return "figurative"
		case IndentRole.locution:
			return "locution"
		case IndentRole.proverb:
			return "proverb"
		case IndentRole.cross_reference:
			return "cross_reference"
		case IndentRole.nature_label | IndentRole.voice_transition:
			return "transition_group" if indent.children else "annotation"
		case IndentRole.domain:
			return "domain"
		case IndentRole.register_label:
			return "register"
		case _:
			return "sense"


def _insert_citations(cursor: sqlite3.Cursor, sense_id: int, citations: list[Citation]) -> None:
	for cit in citations:
		cursor.execute(
			"INSERT INTO citations (sense_id, text_plain, text_markup, author, resolved_author, reference, is_hidden) "
			"VALUES (?, ?, ?, ?, ?, ?, ?)",
			(
				sense_id,
				strip_tags(cit.text),
				cit.text,
				cit.author,
				cit.resolved_author or cit.author,
				cit.reference,
				1 if cit.hide else 0,
			),
		)


def _insert_indent(
	cursor: sqlite3.Cursor, entry_id: str, parent_sense_id: int,
	indent: Indent, depth: int,
	indent_id: str = "", xml_id: str = "",
) -> None:
	plain = strip_tags(indent.content)
	sense_type = _sense_type_for_indent(indent)
	cursor.execute(
		"INSERT INTO senses (entry_id, parent_sense_id, indent_id, xml_id, sense_type, role, content_plain, content_markup, depth) "
		"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
		(entry_id, parent_sense_id, indent_id or None, xml_id or None,
		 sense_type, indent.role.value, plain, indent.content, depth),
	)
	sense_id = cursor.lastrowid
	_insert_citations(cursor, sense_id, indent.citations)

	if indent.role == IndentRole.locution and indent.canonical_form:
		cursor.execute("INSERT INTO locutions (sense_id, canonical_form) VALUES (?, ?)", (sense_id, indent.canonical_form))

	child_counter = 0
	for child in indent.children:
		child_counter += 1
		child_indent_id = f"{indent_id}.{child_counter}" if indent_id else ""
		child_xml_id = f"{xml_id}.{child_counter}" if xml_id else ""
		_insert_indent(cursor, entry_id, sense_id, child, depth + 1,
			indent_id=child_indent_id, xml_id=child_xml_id)


def _insert_variante(
	cursor: sqlite3.Cursor, entry_id: str, parent_sense_id: int | None,
	variante: Variante, depth: int,
	headword: str = "", xml_id: str = "",
) -> None:
	if variante.transition_type:
		plain = strip_tags(variante.transition_content)
		sense_type = "grammatical_variant" if variante.transition_type == "strong" else "usage_group"
		cursor.execute(
			"INSERT INTO senses (entry_id, parent_sense_id, xml_id, sense_type, content_plain, content_markup, depth, "
			"transition_type, transition_form, transition_pos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
			(
				entry_id, parent_sense_id, xml_id or None,
				sense_type, plain, variante.transition_content, depth,
				variante.transition_type, variante.transition_form or None, variante.transition_pos or None,
			),
		)
		container_id = cursor.lastrowid
		child_counter = 0
		for sub in variante.sub_variantes:
			child_counter += 1
			child_xml_id = f"{xml_id}.{child_counter}" if xml_id else ""
			_insert_variante(cursor, entry_id, container_id, sub, depth + 1,
				headword=headword, xml_id=child_xml_id)
		return

	vnum = variante.num or "0"
	indent_id_base = f"{headword.lower()}.{vnum}" if headword else ""
	plain = strip_tags(variante.content) if variante.content else None
	cursor.execute(
		"INSERT INTO senses (entry_id, parent_sense_id, num, indent_id, xml_id, sense_type, content_plain, content_markup, is_supplement, depth) "
		"VALUES (?, ?, ?, ?, ?, 'sense', ?, ?, ?, ?)",
		(entry_id, parent_sense_id, variante.num, indent_id_base or None, xml_id or None,
		 plain, variante.content or None, 1 if variante.is_supplement else 0, depth),
	)
	sense_id = cursor.lastrowid
	_insert_citations(cursor, sense_id, variante.citations)

	indent_counter = 0
	for indent in variante.indents:
		indent_counter += 1
		child_indent_id = f"{indent_id_base}.{indent_counter}" if indent_id_base else ""
		child_xml_id = f"{xml_id}.{indent_counter}" if xml_id else ""
		_insert_indent(cursor, entry_id, sense_id, indent, depth + 1,
			indent_id=child_indent_id, xml_id=child_xml_id)


def _insert_rubriques(cursor: sqlite3.Cursor, entry_id: str, rubriques: list[Rubrique]) -> None:
	for rub in rubriques:
		parts = [rub.content] if rub.content else []
		for indent in rub.indents:
			parts.append(indent.content)
		full_markup = " ".join(p for p in parts if p)
		full_plain = strip_tags(full_markup)
		cursor.execute(
			"INSERT INTO rubriques (entry_id, rubrique_type, content_plain, content_markup) VALUES (?, ?, ?, ?)",
			(entry_id, rub.type.value, full_plain, full_markup),
		)


def emit_sqlite(entries: list[Entry], flags: list[ReviewFlag], output_path: str) -> None:
	conn = sqlite3.connect(output_path)
	cursor = conn.cursor()
	cursor.executescript(schema)

	for entry in entries:
		cursor.execute(
			"INSERT INTO entries (entry_id, headword, homograph_index, pronunciation, pos, is_supplement, source_letter) "
			"VALUES (?, ?, ?, ?, ?, ?, ?)",
			(
				entry.xml_id,
				entry.headword,
				entry.homograph_index,
				entry.pronunciation or None,
				entry.pos or None,
				1 if entry.is_supplement else 0,
				entry.source_letter or None,
			),
		)
		sense_counter = 0
		for variante in entry.body_variantes:
			sense_counter += 1
			xml_id = f"{entry.xml_id}_s{sense_counter}"
			_insert_variante(cursor, entry.xml_id, None, variante, depth=0,
				headword=entry.headword, xml_id=xml_id)
		_insert_rubriques(cursor, entry.xml_id, entry.rubriques)

	for flag in flags:
		cursor.execute(
			"INSERT INTO review_queue (entry_id, headword, phase, flag_type, reason, context, resolution, resolved_by) "
			"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
			(
				flag.entry_id,
				flag.headword,
				flag.phase,
				flag.flag_type,
				flag.reason,
				json.dumps(flag.context, ensure_ascii=False),
				flag.resolution or None,
				flag.resolved_by or None,
			),
		)

	conn.commit()
	cursor.executescript(fts_schema)
	conn.commit()

	row_counts = {}
	for table in ("entries", "senses", "citations", "locutions", "rubriques", "review_queue"):
		cursor.execute(f"SELECT COUNT(*) FROM {table}")
		row_counts[table] = cursor.fetchone()[0]
	conn.close()

	print(f"  Wrote {output_path}")
	for table, count in row_counts.items():
		print(f"    {table:15} {count:>8,}")