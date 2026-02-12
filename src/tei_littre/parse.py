"""
Phase 1: Parse normalized Gannaz XML into the internal data model.

Reads each letter file and produces a list of Entry objects.
The parse is faithful to the source structure — no interpretation
or classification happens here.
"""

import sys
import re
import unicodedata
from pathlib import Path
from lxml import etree
from xml.sax.saxutils import escape as xml_escape

from tei_littre.model import (
	Entry, Variante, Citation, Indent, Rubrique,
	RubriqueType, Markup,
)

STRUCTURAL_TAGS = {"cit", "indent", "rubrique", "variante"}

RUBRIQUE_MAP = {
	"HISTORIQUE": RubriqueType.historique,
	"ÉTYMOLOGIE": RubriqueType.etymologie,
	"REMARQUE": RubriqueType.remarque,
	"REMARQUES": RubriqueType.remarque,
	"SYNONYME": RubriqueType.synonyme,
	"PROVERBES": RubriqueType.proverbes,
	"PROVERBE": RubriqueType.proverbes,
	"SUPPLÉMENT AU DICTIONNAIRE": RubriqueType.supplement,
}


def serialize_inline(element: etree._Element) -> str:
	"""Serialize an inline element (not structural) back to XML string."""
	return etree.tostring(element, encoding="unicode", with_tail=False)


def extract_content(
	element: etree._Element,
) -> tuple[Markup, list[Citation], list[Indent], list[Rubrique], list[Variante]]:
	"""
	Walk an element's children and separate structural children
	from inline content. Returns (content_markup, citations, indents,
	rubriques, variantes).

	Inline elements (<semantique>, <i>, <a>, <exemple>, <nature>)
	are serialized back into the content string.
	Structural elements (<cit>, <indent>, <rubrique>, <variante>)
	are parsed into their respective model objects.
	"""
	content_parts: list[str] = []
	citations: list[Citation] = []
	indents: list[Indent] = []
	rubriques: list[Rubrique] = []
	variantes: list[Variante] = []

	if element.text:
		content_parts.append(xml_escape(element.text))

	for child in element:
		tag = child.tag
		if tag == "cit":
			citations.append(parse_citation(child))
		elif tag == "indent":
			indents.append(parse_indent(child))
		elif tag == "rubrique":
			result = parse_rubrique(child)
			if isinstance(result, tuple):
				rub, _ = result
			else:
				rub = result
			rubriques.append(rub)
		elif tag == "variante":
			variantes.append(parse_variante(child))
		else:
			content_parts.append(serialize_inline(child))

		if child.tail:
			content_parts.append(xml_escape(child.tail))

	content = " ".join("".join(content_parts).split())
	return content, citations, indents, rubriques, variantes


def parse_citation(element: etree._Element) -> Citation:
	author = element.get("aut", "")
	reference = element.get("ref", "")
	hide = element.get("hide", "")
	text_parts: list[str] = []
	if element.text:
		text_parts.append(xml_escape(element.text))
	for child in element:
		text_parts.append(serialize_inline(child))
		if child.tail:
			text_parts.append(xml_escape(child.tail))
	text = "".join(text_parts).strip()
	return Citation(text=text, author=author, reference=reference, hide=hide)


def parse_indent(element: etree._Element) -> Indent:
	content, citations, children, rubriques, _ = extract_content(element)
	return Indent(
		content=content,
		citations=citations,
		children=children,
	)


def parse_variante(element: etree._Element) -> Variante:
	num_str = element.get("num", "")
	num: int | None = None
	if num_str:
		try:
			num = int(num_str)
		except ValueError:
			num = None
	is_resume = element.get("option", "") == "résumé"
	content, citations, indents, rubriques, _ = extract_content(element)
	return Variante(
		content=content,
		num=num,
		is_resume=is_resume,
		citations=citations,
		indents=indents,
		rubriques=rubriques,
	)


def parse_rubrique(element: etree._Element) -> Rubrique:
	nom = element.get("nom", "")
	rtype = RUBRIQUE_MAP.get(nom)
	if rtype is None:
		print(f"  Warning: unknown rubrique type '{nom}'", file=sys.stderr)
		rtype = RubriqueType.remarque

	content, citations, indents, _, variantes = extract_content(element)

	if variantes:
		for v in variantes:
			v.is_supplement = True

	rubrique = Rubrique(
		type=rtype,
		content=content,
		citations=citations,
		indents=indents,
	)
	return rubrique, variantes


def make_xml_id(headword: str, homograph_index: int | None = None) -> str:
	nfkd = unicodedata.normalize("NFKD", headword.lower())
	ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
	cleaned = re.sub(r"[^a-z0-9]", "_", ascii_only)
	cleaned = re.sub(r"_+", "_", cleaned).strip("_")
	if not cleaned or not cleaned[0].isalpha():
		cleaned = "e_" + cleaned
	if homograph_index is not None:
		cleaned = f"{cleaned}.{homograph_index}"
	return cleaned


def parse_entry(element: etree._Element, letter: str) -> Entry:
	headword = element.get("terme", "")
	sens_str = element.get("sens", "")
	homograph_index = int(sens_str) if sens_str else None
	is_supplement = element.get("supplement", "") == "1"

	pronunciation = ""
	pos = ""
	entete = element.find("entete")
	if entete is not None:
		pron_el = entete.find("prononciation")
		if pron_el is not None and pron_el.text:
			pronunciation = pron_el.text.strip()
		nature_el = entete.find("nature")
		if nature_el is not None and nature_el.text:
			pos = nature_el.text.strip()

	body_variantes: list[Variante] = []
	supplement_variantes: list[Variante] = []
	rubriques: list[Rubrique] = []
	resume_text = ""

	corps = element.find("corps")
	if corps is not None:
		for child in corps:
			if child.tag == "variante":
				body_variantes.append(parse_variante(child))
			elif child.tag == "rubrique":
				result = parse_rubrique(child)
				if isinstance(result, tuple):
					rub, sup_vars = result
					rubriques.append(rub)
					supplement_variantes.extend(sup_vars)
				else:
					rubriques.append(result)

	resume_el = element.find("résumé")
	if resume_el is not None:
		resume_text = etree.tostring(resume_el, encoding="unicode")

	for child in element:
		if child.tag == "rubrique":
			result = parse_rubrique(child)
			if isinstance(result, tuple):
				rub, sup_vars = result
				rubriques.append(rub)
				supplement_variantes.extend(sup_vars)
			else:
				rubriques.append(result)

	all_variantes = body_variantes + supplement_variantes

	xml_id = make_xml_id(headword, homograph_index)

	return Entry(
		headword=headword,
		xml_id=xml_id,
		homograph_index=homograph_index,
		is_supplement=is_supplement,
		pronunciation=pronunciation,
		pos=pos,
		body_variantes=all_variantes,
		rubriques=rubriques,
		resume_text=resume_text,
		source_letter=letter,
	)


def parse_file(path: Path) -> list[Entry]:
	letter = path.stem
	tree = etree.parse(str(path))
	root = tree.getroot()
	entries = []
	for element in root.iter("entree"):
		entries.append(parse_entry(element, letter))
	return entries


def parse_all(source_dir: str) -> list[Entry]:
	src = Path(source_dir)
	xml_files = sorted(src.glob("*.xml"))
	letter_names = {chr(c) for c in range(ord("a"), ord("z") + 1)}
	letter_names.add("a_prep")
	xml_files = [f for f in xml_files if f.stem in letter_names]
	if not xml_files:
		print(f"No XML files found in {src}", file=sys.stderr)
		sys.exit(1)

	all_entries: list[Entry] = []
	for f in xml_files:
		entries = parse_file(f)
		print(f"  {f.name}: {len(entries)} entries")
		all_entries.extend(entries)

	print(f"Total: {len(all_entries)} entries")
	return all_entries


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print("Usage: python parse.py <source_dir>")
		sys.exit(1)
	entries = parse_all(sys.argv[1])
	sample = next(e for e in entries if e.headword == "MAISON")
	print(f"\nSample: {sample.headword}")
	print(f"  POS: {sample.pos}")
	print(f"  Pronunciation: {sample.pronunciation}")
	print(f"  Variantes: {len(sample.body_variantes)}")
	print(f"  Rubriques: {[r.type.value for r in sample.rubriques]}")
	print(f"  Résumé: {sample.resume_text[:80]}..." if sample.resume_text else "  Résumé: (none)")
	if sample.body_variantes:
		v1 = sample.body_variantes[0]
		print(f"  Variante 1 content: {v1.content[:100]}...")
		print(f"  Variante 1 citations: {len(v1.citations)}")
		print(f"  Variante 1 indents: {len(v1.indents)}")
