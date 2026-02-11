"""
Phase 2: Resolve 'ID.' author abbreviations to the actual author.

Walks citations in document order within each entry, propagating
the last non-ID. author forward. Purely mechanical.
"""

from tei_littre.model import Entry, Citation, Indent, Variante, Rubrique


def citations_in_order(entry: Entry) -> list[Citation]:
	"""Yield all citations in document order for an entry."""
	result: list[Citation] = []

	for variante in entry.body_variantes:
		_collect_variante(variante, result)

	for rubrique in entry.rubriques:
		_collect_rubrique(rubrique, result)

	return result


def _collect_variante(variante: Variante, out: list[Citation]) -> None:
	out.extend(variante.citations)
	for indent in variante.indents:
		_collect_indent(indent, out)
	for rubrique in variante.rubriques:
		_collect_rubrique(rubrique, out)


def _collect_indent(indent: Indent, out: list[Citation]) -> None:
	out.extend(indent.citations)
	for child in indent.children:
		_collect_indent(child, out)


def _collect_rubrique(rubrique: Rubrique, out: list[Citation]) -> None:
	out.extend(rubrique.citations)
	for indent in rubrique.indents:
		_collect_indent(indent, out)


def resolve_authors(entry: Entry) -> int:
	"""Resolve ID. authors in an entry. Returns count of resolutions."""
	all_citations = citations_in_order(entry)
	last_author = ""
	resolved = 0

	for citation in all_citations:
		if citation.author == "ID." and last_author:
			citation.resolved_author = last_author
			resolved += 1
		elif citation.author and citation.author != "ID.":
			last_author = citation.author
			citation.resolved_author = citation.author
		else:
			citation.resolved_author = citation.author

	return resolved


def resolve_all(entries: list[Entry]) -> None:
	total = 0
	unresolved = 0
	for entry in entries:
		total += resolve_authors(entry)
		for cit in citations_in_order(entry):
			if cit.author == "ID." and not cit.resolved_author:
				unresolved += 1

	print(f"  Resolved {total} ID. citations")
	if unresolved:
		print(f"  Warning: {unresolved} ID. citations had no antecedent")
