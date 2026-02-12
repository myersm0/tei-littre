"""
Phase 7a: Emit TEI Lex-0 XML from the enriched internal model.
"""

import re
from functools import reduce
from xml.sax.saxutils import escape
from tei_littre.model import (
	Entry, Variante, Citation, Indent, Rubrique,
	RubriqueType, IndentRole, Markup,
)

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"

HEADER_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="littre">
<teiHeader>
<fileDesc>
<titleStmt>
<title>Dictionnaire de la langue française — Émile Littré</title>
<title type="sub">TEI Lex-0 edition</title>
<author>Émile Littré</author>
<editor role="digital">François Gannaz</editor>
<editor role="enrichment">tei-littre pipeline</editor>
</titleStmt>
<publicationStmt>
<publisher>tei-littre project</publisher>
<availability status="restricted">
<licence target="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</licence>
</availability>
</publicationStmt>
<sourceDesc>
<bibl>Littré, Émile. <title>Dictionnaire de la langue française</title>. Paris: Hachette, 1872–1877.</bibl>
<bibl>Digital source: François Gannaz, XMLittré v1.3
<ref target="https://bitbucket.org/Mytskine/xmlittre-data">bitbucket.org/Mytskine/xmlittre-data</ref>
</bibl>
</sourceDesc>
</fileDesc>
</teiHeader>
<text>
<body>
"""

FOOTER = """</body>
</text>
</TEI>
"""

markup_substitutions = [
	(r'<semantique type="domaine">(.*?)</semantique>', r'<usg type="domain">\1</usg>'),
	(r'<semantique type="indicateur">(.*?)</semantique>', r'<usg type="hint">\1</usg>'),
	(r'<semantique>(.*?)</semantique>', r'<usg>\1</usg>'),
	(r'<a ref="([^"]*)">(.*?)</a>', r'<xr><ref target="#\1">\2</ref></xr>'),
	(r'<exemple>(.*?)</exemple>', r'<mentioned>\1</mentioned>'),
	(r'<nature>(.*?)</nature>', r'<gramGrp><gram type="pos">\1</gram></gramGrp>'),
	(r'<i lang="la">(.*?)</i>', r'<foreign xml:lang="la">\1</foreign>'),
	(r"<i>(.*?)</i>", r"<mentioned>\1</mentioned>"),
]

compiled_substitutions = [(re.compile(p), r) for p, r in markup_substitutions]


def strip_tags(markup: str) -> str:
	return re.sub(r"<[^>]+>", "", markup).strip()


def markup_to_tei(markup: Markup) -> str:
	return reduce(lambda text, sub: sub[0].sub(sub[1], text), compiled_substitutions, markup)


def emit_citation(citation: Citation, indent_level: int = 0) -> str:
	pad = "  " * indent_level
	author = citation.resolved_author or citation.author
	text = markup_to_tei(citation.text)
	hidden = ' ana="hidden"' if citation.hide else ""

	lines = [f'{pad}<cit type="example"{hidden}>']
	lines.append(f"{pad}  <quote>{text}</quote>")

	if author or citation.reference:
		lines.append(f"{pad}  <bibl>")
		if author:
			lines.append(f"{pad}    <author>{escape(author)}</author>")
		if citation.reference:
			lines.append(f"{pad}    <biblScope>{escape(citation.reference)}</biblScope>")
		lines.append(f"{pad}  </bibl>")

	lines.append(f"{pad}</cit>")
	return "\n".join(lines)


def _emit_citations(citations: list[Citation], indent_level: int) -> list[str]:
	return [emit_citation(cit, indent_level) for cit in citations]


def emit_indent(indent: Indent, indent_level: int = 0) -> str:
	pad = "  " * indent_level
	content = markup_to_tei(indent.content)

	match indent.role:
		case IndentRole.figurative:
			lines = [f'{pad}<sense type="figuré">']
			lines.append(f"{pad}  <def>{content}</def>")
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			for child in indent.children:
				lines.append(emit_indent(child, indent_level + 1))
			lines.append(f"{pad}</sense>")
			return "\n".join(lines)

		case IndentRole.domain:
			lines = [f"{pad}<sense>"]
			lines.append(f"{pad}  <def>{content}</def>")
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			for child in indent.children:
				lines.append(emit_indent(child, indent_level + 1))
			lines.append(f"{pad}</sense>")
			return "\n".join(lines)

		case IndentRole.register_label:
			lines = [f"{pad}<sense>"]
			lines.append(f'{pad}  <usg type="register">{content}</usg>')
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			for child in indent.children:
				lines.append(emit_indent(child, indent_level + 1))
			lines.append(f"{pad}</sense>")
			return "\n".join(lines)

		case IndentRole.locution:
			lines = [f'{pad}<re type="locution">']
			if indent.canonical_form:
				lines.append(f"{pad}  <form><orth>{escape(indent.canonical_form)}</orth></form>")
			lines.append(f"{pad}  <def>{content}</def>")
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			lines.append(f"{pad}</re>")
			return "\n".join(lines)

		case IndentRole.proverb:
			lines = [f'{pad}<re type="proverbe">']
			lines.append(f"{pad}  <def>{content}</def>")
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			lines.append(f"{pad}</re>")
			return "\n".join(lines)

		case IndentRole.cross_reference:
			return f'{pad}<note type="xref">{content}</note>'

		case IndentRole.nature_label:
			if indent.children:
				lines = [f"{pad}<sense>"]
				lines.append(f'{pad}  <usg type="gram">{content}</usg>')
				lines.extend(_emit_citations(indent.citations, indent_level + 1))
				for child in indent.children:
					lines.append(emit_indent(child, indent_level + 1))
				lines.append(f"{pad}</sense>")
				return "\n".join(lines)
			return f'{pad}<usg type="gram">{content}</usg>'

		case IndentRole.voice_transition:
			if indent.children:
				lines = [f"{pad}<sense>"]
				lines.append(f'{pad}  <usg type="gram">{content}</usg>')
				lines.extend(_emit_citations(indent.citations, indent_level + 1))
				for child in indent.children:
					lines.append(emit_indent(child, indent_level + 1))
				lines.append(f"{pad}</sense>")
				return "\n".join(lines)
			return f'{pad}<usg type="gram">{content}</usg>'

		case _:
			lines = [f"{pad}<sense>"]
			lines.append(f"{pad}  <def>{content}</def>")
			lines.extend(_emit_citations(indent.citations, indent_level + 1))
			for child in indent.children:
				lines.append(emit_indent(child, indent_level + 1))
			lines.append(f"{pad}</sense>")
			return "\n".join(lines)


def emit_variante(variante: Variante, indent_level: int = 0) -> str:
	pad = "  " * indent_level

	if variante.transition_type == "strong":
		return _emit_strong_variant(variante, pad, indent_level)
	if variante.transition_type == "medium":
		return _emit_medium_variant(variante, pad, indent_level)

	attrs = ""
	if variante.num is not None:
		attrs += f' n="{variante.num}"'
	if variante.is_supplement:
		attrs += ' source="supplement"'

	lines = [f"{pad}<sense{attrs}>"]

	if variante.content:
		content = markup_to_tei(variante.content)
		lines.append(f"{pad}  <def>{content}</def>")

	lines.extend(_emit_citations(variante.citations, indent_level + 1))

	for indent in variante.indents:
		lines.append(emit_indent(indent, indent_level + 1))

	for rubrique in variante.rubriques:
		emitted = emit_rubrique(rubrique, indent_level + 1)
		if emitted:
			lines.append(emitted)

	lines.append(f"{pad}</sense>")
	return "\n".join(lines)


def _emit_strong_variant(variante: Variante, pad: str, indent_level: int) -> str:
	lines = [f'{pad}<entry type="grammaticalVariant">']
	lines.append(f"{pad}  <form><orth>{escape(variante.transition_form)}</orth></form>")
	lines.append(f'{pad}  <gramGrp><gram type="pos">{escape(variante.transition_pos)}</gram></gramGrp>')
	for sub in variante.sub_variantes:
		lines.append(emit_variante(sub, indent_level + 1))
	lines.append(f"{pad}</entry>")
	return "\n".join(lines)


def _emit_medium_variant(variante: Variante, pad: str, indent_level: int) -> str:
	content = markup_to_tei(variante.transition_content)
	lines = [f"{pad}<sense>"]
	lines.append(f'{pad}  <usg type="gram">{content}</usg>')
	for sub in variante.sub_variantes:
		lines.append(emit_variante(sub, indent_level + 1))
	lines.append(f"{pad}</sense>")
	return "\n".join(lines)


def _emit_rubrique_body(pad: str, rubrique: Rubrique, indent_level: int) -> list[str]:
	lines: list[str] = []
	if rubrique.content:
		lines.append(f"{pad}  <p>{markup_to_tei(rubrique.content)}</p>")
	lines.extend(_emit_citations(rubrique.citations, indent_level + 1))
	for indent in rubrique.indents:
		lines.append(f"{pad}  <p>{markup_to_tei(indent.content)}</p>")
		lines.extend(_emit_citations(indent.citations, indent_level + 1))
	return lines


def emit_rubrique(rubrique: Rubrique, indent_level: int = 0) -> str:
	pad = "  " * indent_level

	match rubrique.type:
		case RubriqueType.etymologie:
			lines = [f"{pad}<etym>"]
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</etym>")
			return "\n".join(lines)

		case RubriqueType.historique:
			lines = [f'{pad}<note type="historique">']
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</note>")
			return "\n".join(lines)

		case RubriqueType.remarque:
			lines = [f'{pad}<note type="remarque">']
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</note>")
			return "\n".join(lines)

		case RubriqueType.synonyme:
			lines = [f'{pad}<re type="synonyme">']
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</re>")
			return "\n".join(lines)

		case RubriqueType.proverbes:
			lines = [f'{pad}<re type="proverbes">']
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</re>")
			return "\n".join(lines)

		case RubriqueType.supplement:
			lines = [f'{pad}<note type="supplément">']
			lines.extend(_emit_rubrique_body(pad, rubrique, indent_level))
			lines.append(f"{pad}</note>")
			return "\n".join(lines)

		case _:
			return ""


def emit_entry(entry: Entry, indent_level: int = 0) -> str:
	pad = "  " * indent_level
	xml_id = escape(entry.xml_id)
	attrs = f'xml:id="{xml_id}"'
	if entry.is_supplement:
		attrs += ' source="supplement"'

	lines = [f"{pad}<entry {attrs}>"]

	lines.append(f'{pad}  <form type="lemma">')
	lines.append(f"{pad}    <orth>{escape(entry.headword)}</orth>")
	if entry.pronunciation:
		lines.append(f"{pad}    <pron>{escape(entry.pronunciation)}</pron>")
	lines.append(f"{pad}  </form>")

	if entry.pos:
		lines.append(f'{pad}  <gramGrp><gram type="pos">{escape(entry.pos)}</gram></gramGrp>')

	if entry.resume_text:
		lines.append(f'{pad}  <note type="résumé">[see source]</note>')

	for variante in entry.body_variantes:
		lines.append(emit_variante(variante, indent_level + 1))

	for rubrique in entry.rubriques:
		emitted = emit_rubrique(rubrique, indent_level + 1)
		if emitted:
			lines.append(emitted)

	lines.append(f"{pad}</entry>")
	return "\n".join(lines)


def emit_tei(entries: list[Entry], output_path: str) -> None:
	seen_ids: dict[str, int] = {}
	with open(output_path, "w", encoding="utf-8") as f:
		f.write(HEADER_TEMPLATE)
		for entry in entries:
			base_id = entry.xml_id
			if base_id in seen_ids:
				seen_ids[base_id] += 1
				entry.xml_id = f"{base_id}_{seen_ids[base_id]}"
			else:
				seen_ids[base_id] = 1
			f.write(emit_entry(entry, indent_level=1))
			f.write("\n")
		f.write(FOOTER)
	print(f"  Wrote {len(entries)} entries to {output_path}")
