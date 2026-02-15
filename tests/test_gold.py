"""Gold-standard classification tests.

These entries have been manually reviewed and annotated with correct
indent roles. Tests marked xfail are known misclassifications that
should start passing as we improve the heuristics.

Run with: PYTHONPATH=src python -m pytest tests/test_gold.py -v
"""

import pytest
from tei_littre.parse import parse_all
from tei_littre.resolve_authors import resolve_all
from tei_littre.classify_indents import classify_all
from tei_littre.extract_locutions import extract_all
from tei_littre.model import IndentRole


@pytest.fixture(scope="module")
def classified_entries():
	entries = parse_all("data/source")
	resolve_all(entries)
	classify_all(entries)
	extract_all(entries)
	return {e.headword: e for e in entries}


def get_indent(entry, variante_num, indent_index):
	for v in entry.body_variantes:
		if v.num == variante_num:
			return v.indents[indent_index]
	raise ValueError(f"variante {variante_num} not found in {entry.headword}")


def get_indent_by_prefix(entry, variante_num, prefix):
	for v in entry.body_variantes:
		if v.num != variante_num:
			continue
		for ind in v.indents:
			plain = ind.content.replace("<semantique", "").replace("<nature", "")
			if prefix in ind.content:
				return ind
	raise ValueError(f"no indent matching '{prefix}' in {entry.headword} v{variante_num}")


# ======================================================================
# DÉBAT — compact entry, 5 indents, 5 roles
# ======================================================================

class TestDebat:

	def test_fig(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉBAT"], 1, "Fig.")
		assert ind.role == IndentRole.figurative

	def test_debat_de_compte(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉBAT"], 2, "Débat de compte")
		assert ind.role == IndentRole.locution

	def test_terme_de_palais(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉBAT"], 3, "Terme de palais")
		assert ind.role == IndentRole.domain

	def test_au_sing(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉBAT"], 3, "Au sing.")
		assert ind.role == IndentRole.nature_label

	def test_journal_des_debats(self, classified_entries):
		"""Journal title usage — borderline, could be elaboration."""
		ind = get_indent_by_prefix(classified_entries["DÉBAT"], 3, "Ce mot est employé")
		assert ind.role == IndentRole.register_label


# ======================================================================
# DEBOUT — 13 indents, heavy locution content
# ======================================================================

class TestDebout:

	# --- currently correct ---

	def test_piece_de_bois(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 1, "Pièce de bois")
		assert ind.role == IndentRole.locution

	def test_fig_v1(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 1, "Fig.")
		assert ind.role == IndentRole.figurative

	def test_fig_et_familierement(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 2, "Fig. et familièrement")
		assert ind.role == IndentRole.figurative

	def test_blason(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 3, "Terme de blason")
		assert ind.role == IndentRole.domain

	def test_fig_v4(self, classified_entries):
		ind = get_indent(classified_entries["DEBOUT"], 4, 0)
		assert ind.role == IndentRole.figurative

	def test_venerie(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 4, "Terme de vénerie")
		assert ind.role == IndentRole.domain

	def test_aborder_debout_au_corps(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 7, "Aborder un bâtiment")
		assert ind.role == IndentRole.locution

	def test_debout_les_avirons(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 7, "Debout les avirons")
		assert ind.role == IndentRole.locution

	# --- currently misclassified (all should be locution) ---

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_etre_debout(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 1, "Être debout, être encore")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_debout_loc_interj(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 2, "Debout, loc. interj.")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_laisser_debout(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 2, "Laisser quelqu")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_conte_a_dormir_debout(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 5, "Conte à dormir debout")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_etre_debout_au_vent(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DEBOUT"], 7, "Être debout au vent")
		assert ind.role == IndentRole.locution


# ======================================================================
# DÉFAUT — 18 indents, many legal locutions
# ======================================================================

class TestDefaut:

	# --- currently correct ---

	def test_anatomie(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 1, "Terme d'anatomie")
		assert ind.role == IndentRole.domain

	def test_a_defaut_de(self, classified_entries):
		"""Tagged with <nature>loc. prép.</nature>, so nature_label fires."""
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 1, "À défaut de")
		assert ind.role == IndentRole.nature_label

	def test_fig_cote_faible(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 2, "Fig.")
		assert ind.role == IndentRole.figurative

	def test_dans_le_meme_sens(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 2, "Dans le même sens")
		assert ind.role == IndentRole.continuation

	def test_donner_defaut(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Donner défaut")
		assert ind.role == IndentRole.locution

	def test_defaut_conge(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Défaut-congé")
		assert ind.role == IndentRole.locution

	def test_relever_le_defaut(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 4, "Relever le défaut")
		assert ind.role == IndentRole.locution

	def test_fig_etre_en_defaut(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 4, "Fig.")
		assert ind.role == IndentRole.figurative

	def test_animaux_v5(self, classified_entries):
		ind = get_indent(classified_entries["DÉFAUT"], 5, 0)
		assert ind.role == IndentRole.elaboration

	def test_animaux_v6(self, classified_entries):
		ind = get_indent(classified_entries["DÉFAUT"], 6, 0)
		assert ind.role == IndentRole.elaboration

	def test_rhetorique(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 7, "Terme de rhétorique")
		assert ind.role == IndentRole.domain

	# --- currently misclassified (all should be locution) ---

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_defaut_de_la_cuirasse(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 2, "Le défaut de la cuirasse")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_defaut_contre_partie(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Défaut contre partie")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_defaut_contre_avoue(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Défaut contre avoué")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_profit_du_defaut(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Profit du défaut")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as elaboration")
	def test_defaut_profit_joint(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 3, "Défaut profit-joint")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_mettre_en_defaut_trouver(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 4, "Mettre, prendre, trouver")
		assert ind.role == IndentRole.locution

	@pytest.mark.xfail(reason="locution misclassified as continuation")
	def test_mettre_en_defaut(self, classified_entries):
		ind = get_indent_by_prefix(classified_entries["DÉFAUT"], 4, "Mettre en défaut")
		assert ind.role == IndentRole.locution