import tempfile
from pathlib import Path
from lxml import etree

from tei_littre.model import (
	Entry, Variante, Citation, Indent, Rubrique,
	RubriqueType, IndentRole, ClassificationMethod,
)
from tei_littre.parse import parse_file, make_xml_id
from tei_littre.resolve_authors import resolve_authors, citations_in_order
from tei_littre.classify_indents import classify_indent
from tei_littre.emit_tei import markup_to_tei, emit_entry, emit_tei


sample_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<dictionary>
<entree terme="CHAT" sens="1">
<entete>
	<prononciation>cha</prononciation>
	<nature>s. m.</nature>
</entete>
<corps>
<variante num="1">Animal domestique.
<cit aut="LA FONT." ref="Fab. II, 3">Notre chat, qui n'était pas gros</cit>
<cit aut="ID." ref="ib. IV, 5">Un chat faisait ses tours</cit>
<indent><semantique type="indicateur">Fig.</semantique> Éveillé comme un chat.
<cit aut="MOL." ref="Tart. I, 2">Il a des griffes de chat</cit>
</indent>
<indent><exemple>Chat échaudé craint l'eau froide</exemple>, se dit de celui qui a été trompé.
</indent>
<indent>Garder le chat, voy. <a ref="garder">GARDER</a>.
</indent>
</variante>
<variante num="2"><semantique type="domaine">Terme de marine.</semantique> Grappin à quatre branches.
</variante>
</corps>
<rubrique nom="ÉTYMOLOGIE">
<indent>Bas-lat. cattus ; ital. gatto.</indent>
</rubrique>
</entree>

<entree terme="CHAT" sens="2">
<entete>
	<prononciation>cha</prononciation>
	<nature>s. m.</nature>
</entete>
<corps>
<variante>Jeu d'enfants.
</variante>
</corps>
</entree>
</dictionary>
"""


def _parse_sample() -> list[Entry]:
	with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
		f.write(sample_xml)
		f.flush()
		return parse_file(Path(f.name))


# --- parse tests ---

class TestParse:
	def test_entry_count(self):
		entries = _parse_sample()
		assert len(entries) == 2

	def test_headword_and_homograph(self):
		entries = _parse_sample()
		assert entries[0].headword == "CHAT"
		assert entries[0].homograph_index == 1
		assert entries[1].homograph_index == 2

	def test_pronunciation_and_pos(self):
		entries = _parse_sample()
		assert entries[0].pronunciation == "cha"
		assert entries[0].pos == "s. m."

	def test_variante_count(self):
		entries = _parse_sample()
		assert len(entries[0].body_variantes) == 2
		assert entries[0].body_variantes[0].num == 1
		assert entries[0].body_variantes[1].num == 2

	def test_citations_parsed(self):
		entries = _parse_sample()
		v1 = entries[0].body_variantes[0]
		assert len(v1.citations) == 2
		assert v1.citations[0].author == "LA FONT."
		assert v1.citations[1].author == "ID."

	def test_indents_parsed(self):
		entries = _parse_sample()
		v1 = entries[0].body_variantes[0]
		assert len(v1.indents) == 3

	def test_figurative_indent_content(self):
		entries = _parse_sample()
		fig_indent = entries[0].body_variantes[0].indents[0]
		assert "Fig." in fig_indent.content
		assert len(fig_indent.citations) == 1

	def test_domain_label_in_variante(self):
		entries = _parse_sample()
		v2 = entries[0].body_variantes[1]
		assert "domaine" in v2.content

	def test_rubrique_parsed(self):
		entries = _parse_sample()
		assert len(entries[0].rubriques) == 1
		assert entries[0].rubriques[0].type == RubriqueType.etymologie

	def test_simple_entry(self):
		entries = _parse_sample()
		assert len(entries[1].body_variantes) == 1
		assert entries[1].body_variantes[0].num is None


# --- xml_id tests ---

class TestXmlId:
	def test_simple(self):
		assert make_xml_id("MAISON") == "maison"

	def test_accents_stripped(self):
		assert make_xml_id("ÉLÉPHANT") == "elephant"

	def test_homograph(self):
		assert make_xml_id("CHAT", 2) == "chat.2"

	def test_reflexive(self):
		assert make_xml_id("ABEAUSIR (S')") == "abeausir_s"

	def test_leading_digit(self):
		assert make_xml_id("1ER").startswith("e_")


# --- author resolution tests ---

class TestResolveAuthors:
	def test_id_resolved(self):
		entries = _parse_sample()
		resolve_authors(entries[0])
		cits = citations_in_order(entries[0])
		assert cits[0].resolved_author == "LA FONT."
		assert cits[1].resolved_author == "LA FONT."

	def test_new_author_resets(self):
		entries = _parse_sample()
		resolve_authors(entries[0])
		cits = citations_in_order(entries[0])
		mol_cit = next(c for c in cits if c.author == "MOL.")
		assert mol_cit.resolved_author == "MOL."


# --- indent classification tests ---

class TestClassifyIndents:
	def test_figurative_deterministic(self):
		indent = Indent(content='<semantique type="indicateur">Fig.</semantique> Foo.')
		classify_indent(indent)
		assert indent.role == IndentRole.figurative
		assert indent.classification_method == ClassificationMethod.deterministic

	def test_domain_deterministic(self):
		indent = Indent(content='<semantique type="domaine">Marine.</semantique> A thing.')
		classify_indent(indent)
		assert indent.role == IndentRole.domain

	def test_nature_label(self):
		indent = Indent(content="<nature>V. réfl.</nature> Se conjugue avec être.")
		classify_indent(indent)
		assert indent.role == IndentRole.nature_label

	def test_locution_with_exemple(self):
		indent = Indent(content="<exemple>Avoir beau jeu</exemple>, se dit quand...")
		classify_indent(indent)
		assert indent.role == IndentRole.locution

	def test_proverb_heuristic(self):
		indent = Indent(content="Prov. Qui dort dîne.")
		classify_indent(indent)
		assert indent.role == IndentRole.proverb

	def test_cross_ref_deterministic(self):
		indent = Indent(content='Voy. <a ref="garder">GARDER</a>.')
		classify_indent(indent)
		assert indent.role == IndentRole.cross_reference


# --- markup_to_tei tests ---

class TestMarkupToTei:
	def test_domain(self):
		result = markup_to_tei('<semantique type="domaine">Marine.</semantique>')
		assert result == '<usg type="domain">Marine.</usg>'

	def test_indicateur(self):
		result = markup_to_tei('<semantique type="indicateur">Fig.</semantique>')
		assert result == '<usg type="hint">Fig.</usg>'

	def test_cross_ref(self):
		result = markup_to_tei('<a ref="chat">CHAT</a>')
		assert result == '<xr><ref target="#chat">CHAT</ref></xr>'

	def test_exemple(self):
		result = markup_to_tei("<exemple>Bon gré mal gré</exemple>")
		assert result == "<mentioned>Bon gré mal gré</mentioned>"

	def test_latin(self):
		result = markup_to_tei('<i lang="la">cattus</i>')
		assert result == '<foreign xml:lang="la">cattus</foreign>'

	def test_italic(self):
		result = markup_to_tei("<i>abaisser</i>")
		assert result == "<mentioned>abaisser</mentioned>"

	def test_chained(self):
		result = markup_to_tei(
			'<semantique type="domaine">Bot.</semantique> <i>Rosa</i>, genre de plantes.'
		)
		assert '<usg type="domain">Bot.</usg>' in result
		assert "<mentioned>Rosa</mentioned>" in result


# --- TEI emission round-trip ---

class TestEmitTei:
	def test_emit_entry_valid_xml(self):
		entries = _parse_sample()
		resolve_authors(entries[0])
		xml_str = emit_entry(entries[0])
		wrapped = f'<body xmlns="http://www.tei-c.org/ns/1.0">{xml_str}</body>'
		etree.fromstring(wrapped.encode())

	def test_full_round_trip_valid(self):
		entries = _parse_sample()
		from tei_littre.resolve_authors import resolve_all
		from tei_littre.classify_indents import classify_all
		resolve_all(entries)
		classify_all(entries)
		with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
			emit_tei(entries, f.name)
			tree = etree.parse(f.name)
			ns = {"tei": "http://www.tei-c.org/ns/1.0"}
			found = tree.findall(".//tei:entry", ns)
			assert len(found) == 2

	def test_author_resolved_in_output(self):
		entries = _parse_sample()
		resolve_authors(entries[0])
		xml_str = emit_entry(entries[0])
		assert "LA FONT." in xml_str
		assert "ID." not in xml_str
