"""Tests for indent_id and xml_id generation in SQLite output.

Covers ID normalization edge cases: accented headwords, commas,
apostrophes, hyphens, homographs, dedup suffixes, unnumbered variantes,
empty variantes, and cross-output consistency.

Run with: PYTHONPATH=src python -m pytest tests/test_sense_ids.py -v
"""

import sqlite3
import pytest
from pathlib import Path

from tei_littre.parse import parse_all, make_xml_id
from tei_littre.resolve_authors import resolve_all
from tei_littre.classify_indents import classify_all
from tei_littre.extract_locutions import extract_all
from tei_littre.scope_transitions import scope_all
from tei_littre.collect_flags import collect_flags
from tei_littre.emit_sqlite import emit_sqlite


db_path = "data/test_sense_ids.db"


@pytest.fixture(scope="module")
def db():
	entries = parse_all("data/source")
	resolve_all(entries)
	classify_all(entries)
	extract_all(entries)
	scope_all(entries)
	flags = collect_flags(entries)
	Path(db_path).unlink(missing_ok=True)
	emit_sqlite(entries, flags, db_path)
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	yield conn
	conn.close()
	Path(db_path).unlink(missing_ok=True)


def query_indent_ids(db, entry_id, limit=5):
	cur = db.execute(
		"SELECT indent_id, xml_id, content_plain, role FROM senses "
		"WHERE entry_id = ? AND indent_id IS NOT NULL ORDER BY sense_id LIMIT ?",
		(entry_id, limit),
	)
	return cur.fetchall()


class TestIndentIdNormalization:

	def test_accented_headword(self, db):
		rows = query_indent_ids(db, "defaut")
		assert rows[0]["indent_id"] == "defaut.1"
		assert rows[1]["indent_id"] == "defaut.1.1"

	def test_comma_headword(self, db):
		rows = query_indent_ids(db, "degoute_ee")
		assert rows[0]["indent_id"] == "degoute_ee.1"

	def test_apostrophe_headword(self, db):
		rows = query_indent_ids(db, "d_abord")
		assert rows[0]["indent_id"].startswith("d_abord.")

	def test_hyphenated_headword(self, db):
		rows = query_indent_ids(db, "demi_aigrette")
		assert rows[0]["indent_id"].startswith("demi_aigrette.")

	def test_no_accents_in_indent_id(self, db):
		cur = db.execute("SELECT indent_id FROM senses WHERE indent_id IS NOT NULL")
		non_ascii = [r[0] for r in cur.fetchall() if not r[0].isascii()]
		assert len(non_ascii) == 0, f"Non-ASCII indent_ids found: {non_ascii[:5]}"


class TestXmlIdConsistency:

	def test_xml_id_matches_indent_id_structure(self, db):
		rows = query_indent_ids(db, "defaut", limit=20)
		for row in rows:
			indent_id = row["indent_id"]
			xml_id = row["xml_id"]
			assert xml_id.startswith("defaut_s")
			parts = indent_id.replace("defaut.", "").split(".")
			xml_parts = xml_id.replace("defaut_s", "").split(".")
			assert parts == xml_parts

	def test_locution_has_xml_id(self, db):
		cur = db.execute(
			"SELECT xml_id FROM senses WHERE role = 'locution' AND xml_id IS NULL"
		)
		missing = cur.fetchall()
		assert len(missing) == 0

	def test_all_xml_ids_unique(self, db):
		cur = db.execute(
			"SELECT xml_id, COUNT(*) FROM senses WHERE xml_id IS NOT NULL "
			"GROUP BY xml_id HAVING COUNT(*) > 1"
		)
		dupes = cur.fetchall()
		assert len(dupes) == 0, f"Duplicate xml_ids: {[r[0] for r in dupes[:5]]}"


class TestHomographs:

	def test_homograph_entry_ids_distinct(self, db):
		cur = db.execute(
			"SELECT entry_id FROM entries WHERE entry_id LIKE 'degrossi%' ORDER BY entry_id"
		)
		ids = [r[0] for r in cur.fetchall()]
		assert "degrossi_ie.1" in ids
		assert "degrossi.2" in ids

	def test_homograph_indent_ids_include_index(self, db):
		rows = query_indent_ids(db, "degrossi_ie.1")
		assert rows[0]["indent_id"].startswith("degrossi_ie.1.")

	def test_dedup_suffix(self, db):
		cur = db.execute("SELECT entry_id FROM entries WHERE entry_id = 'damas_2'")
		assert cur.fetchone() is not None


class TestUnnumberedVariantes:

	def test_unnumbered_gets_one(self, db):
		rows = query_indent_ids(db, "d")
		assert rows[0]["indent_id"] == "d.1"

	def test_unnumbered_children(self, db):
		rows = query_indent_ids(db, "d")
		child_ids = [r["indent_id"] for r in rows if "." in r["indent_id"].replace("d.", "", 1)]
		assert "d.1.1" in child_ids


class TestEmptyVariantes:

	def test_empty_variantes_have_indent_id(self, db):
		cur = db.execute(
			"SELECT indent_id FROM senses WHERE content_plain IS NULL AND indent_id IS NOT NULL LIMIT 1"
		)
		row = cur.fetchone()
		assert row is not None

	def test_empty_variantes_have_no_role(self, db):
		cur = db.execute(
			"SELECT COUNT(*) FROM senses WHERE content_plain IS NULL AND role IS NOT NULL AND indent_id IS NOT NULL"
		)
		assert cur.fetchone()[0] == 0
