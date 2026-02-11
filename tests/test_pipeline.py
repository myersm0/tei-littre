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

	def test_obsolescence_vieux(self):
		indent = Indent(content="Vieux.")
		classify_indent(indent)
		assert indent.role == IndentRole.register_label

	def test_obsolescence_peu_usite(self):
		indent = Indent(content="Peu usité.")
		classify_indent(indent)
		assert indent.role == IndentRole.register_label

	def test_obsolescence_il_a_vieilli(self):
		indent = Indent(content="Il a vieilli.")
		classify_indent(indent)
		assert indent.role == IndentRole.register_label

	def test_short_definition_elaboration(self):
		indent = Indent(content="Béquille.")
		classify_indent(indent)
		assert indent.role == IndentRole.elaboration


# --- locution extraction tests ---

class TestExtractLocutions:
	def test_exemple_tag(self):
		from tei_littre.extract_locutions import extract_locution
		indent = Indent(
			content="<exemple>Chat échaudé craint l'eau froide</exemple>, se dit de celui qui a été trompé.",
			role=IndentRole.locution,
		)
		extract_locution(indent)
		assert indent.canonical_form == "Chat échaudé craint l'eau froide"

	def test_comma_split(self):
		from tei_littre.extract_locutions import extract_locution
		indent = Indent(
			content="Garder la maison, rester chez soi.",
			role=IndentRole.locution,
		)
		extract_locution(indent)
		assert indent.canonical_form == "Garder la maison"

	def test_reflexive_reclassified(self):
		from tei_littre.extract_locutions import extract_locution
		indent = Indent(
			content="S'ABAISSER, v. réfl.",
			role=IndentRole.locution,
		)
		extract_locution(indent)
		assert indent.role == IndentRole.voice_transition
		assert indent.canonical_form == ""

	def test_no_comma_skipped(self):
		from tei_littre.extract_locutions import extract_locution
		indent = Indent(
			content="Locution tombée en désuétude.",
			role=IndentRole.locution,
		)
		extract_locution(indent)
		assert indent.canonical_form == ""

	def test_non_locution_ignored(self):
		from tei_littre.extract_locutions import extract_locution
		indent = Indent(
			content="Some content, with comma.",
			role=IndentRole.elaboration,
		)
		extract_locution(indent)
		assert indent.canonical_form == ""


# --- scope resolution tests ---

class TestScopeTransitions:
	def test_intra_variante_grouping(self):
		from tei_littre.scope_transitions import scope_intra_variante, ScopeLog
		nature = Indent(content="Absolument.", role=IndentRole.nature_label)
		follower1 = Indent(content="Some definition.", role=IndentRole.continuation)
		follower2 = Indent(content="Another.", role=IndentRole.elaboration)
		earlier = Indent(content="Fig. Something.", role=IndentRole.figurative)
		var = Variante(content="Main def.", indents=[earlier, nature, follower1, follower2])
		log = ScopeLog()
		scope_intra_variante(var, log)
		assert len(var.indents) == 2
		assert var.indents[0] == earlier
		assert var.indents[1] == nature
		assert len(nature.children) == 2
		assert log.intra_grouped == 2

	def test_intra_stops_at_next_transition(self):
		from tei_littre.scope_transitions import scope_intra_variante, ScopeLog
		t1 = Indent(content="Absolument.", role=IndentRole.nature_label)
		f1 = Indent(content="Def one.", role=IndentRole.continuation)
		t2 = Indent(content="Au pluriel.", role=IndentRole.nature_label)
		f2 = Indent(content="Def two.", role=IndentRole.elaboration)
		var = Variante(content="Main.", indents=[t1, f1, t2, f2])
		log = ScopeLog()
		scope_intra_variante(var, log)
		assert len(var.indents) == 2
		assert len(t1.children) == 1
		assert len(t2.children) == 1

	def test_inter_variante_strong(self):
		from tei_littre.scope_transitions import scope_inter_variante, ScopeLog
		transition = Indent(content="S'ABAISSER, v. réfl.", role=IndentRole.voice_transition)
		v1 = Variante(content="Active sense.", num=1, indents=[transition])
		v2 = Variante(content="Reflexive sense one.", num=2)
		v3 = Variante(content="Reflexive sense two.", num=3)
		entry = Entry(headword="ABAISSER", body_variantes=[v1, v2, v3])
		log = ScopeLog()
		scope_inter_variante(entry, log)
		assert len(entry.body_variantes) == 2
		assert entry.body_variantes[0].num == 1
		assert len(entry.body_variantes[0].indents) == 0
		container = entry.body_variantes[1]
		assert container.transition_type == "strong"
		assert container.transition_form == "S'ABAISSER"
		assert container.transition_pos == "v. réfl."
		assert len(container.sub_variantes) == 2
		assert log.strong_scoped == 2

	def test_inter_variante_medium(self):
		from tei_littre.scope_transitions import scope_inter_variante, ScopeLog
		transition = Indent(content="Activement.", role=IndentRole.voice_transition)
		v1 = Variante(content="Intransitive.", num=1, indents=[transition])
		v2 = Variante(content="Transitive sense.", num=2)
		entry = Entry(headword="BROSSER", body_variantes=[v1, v2])
		log = ScopeLog()
		scope_inter_variante(entry, log)
		container = entry.body_variantes[1]
		assert container.transition_type == "medium"
		assert len(container.sub_variantes) == 1

	def test_inter_variante_dead(self):
		from tei_littre.scope_transitions import scope_inter_variante, ScopeLog
		transition = Indent(content="Au fém.", role=IndentRole.voice_transition)
		v1 = Variante(content="Only sense.", num=1, indents=[transition])
		entry = Entry(headword="TEST", body_variantes=[v1])
		log = ScopeLog()
		scope_inter_variante(entry, log)
		assert len(entry.body_variantes) == 1
		assert entry.body_variantes[0].indents[-1] == transition
		assert log.zero_scope == 1

	def test_strong_variant_emits_valid_xml(self):
		from tei_littre.scope_transitions import scope_inter_variante, ScopeLog
		transition = Indent(content="S'AIMER, v. réfl.", role=IndentRole.voice_transition)
		v1 = Variante(content="To love.", num=1, indents=[transition])
		v2 = Variante(content="Reflexive.", num=2)
		entry = Entry(headword="AIMER", xml_id="aimer", body_variantes=[v1, v2])
		log = ScopeLog()
		scope_inter_variante(entry, log)
		xml_str = emit_entry(entry)
		wrapped = f'<body xmlns="http://www.tei-c.org/ns/1.0">{xml_str}</body>'
		etree.fromstring(wrapped.encode())
		assert 'grammaticalVariant' in xml_str
		assert "S'AIMER" in xml_str

	def test_multi_transition_scoping(self):
		from tei_littre.scope_transitions import scope_inter_variante, ScopeLog
		t1 = Indent(content="Activement.", role=IndentRole.voice_transition)
		t2 = Indent(content="Neutralement.", role=IndentRole.voice_transition)
		v1 = Variante(content="Def one.", num=1, indents=[t1])
		v2 = Variante(content="Active sense.", num=2)
		v3 = Variante(content="Active two.", num=3, indents=[t2])
		v4 = Variante(content="Neutral sense.", num=4)
		entry = Entry(headword="TEST", body_variantes=[v1, v2, v3, v4])
		log = ScopeLog()
		scope_inter_variante(entry, log)
		# v1(stripped), container1([v2]), v3(stripped), container2([v4])
		assert len(entry.body_variantes) == 4
		assert entry.body_variantes[1].transition_type == "medium"
		assert len(entry.body_variantes[1].sub_variantes) == 1
		assert entry.body_variantes[3].transition_type == "medium"
		assert len(entry.body_variantes[3].sub_variantes) == 1


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
