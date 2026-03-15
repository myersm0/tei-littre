#!/usr/bin/env python3
"""Look up an indent by ID in the Gannaz XML.

Usage:
    lookup DEFAUT.3.1
    lookup "VUE.31.1"
    lookup DEPÔT.2.3
"""

import sys
import unicodedata
from pathlib import Path
from lxml import etree

source_dir = Path("data/source")


def strip_accents(s):
	return "".join(
		c for c in unicodedata.normalize("NFD", s)
		if unicodedata.category(c) != "Mn"
	)


def find_entry(root, terme_query):
	query_norm = strip_accents(terme_query.upper())
	for entry in root.findall(".//entree"):
		terme = entry.get("terme", "")
		if strip_accents(terme.upper()) == query_norm:
			return entry, terme
	return None, None


def main():
	if len(sys.argv) < 2:
		print("Usage: lookup ENTRY.VARIANTE.INDENT")
		sys.exit(1)

	doc_id = sys.argv[1]
	parts = doc_id.rsplit(".", 2)
	if len(parts) != 3:
		print(f"Expected ENTRY.VARIANTE.INDENT, got: {doc_id}")
		sys.exit(1)

	entry_name, variante_num, indent_num = parts[0], parts[1], int(parts[2])

	first_letter = strip_accents(entry_name[0]).lower()
	xml_path = source_dir / f"{first_letter}.xml"
	if not xml_path.exists():
		print(f"File not found: {xml_path}")
		sys.exit(1)

	tree = etree.parse(str(xml_path))
	entry, actual_terme = find_entry(tree.getroot(), entry_name)
	if entry is None:
		print(f"Entry not found: {entry_name} (in {xml_path})")
		sys.exit(1)

	corps = entry.find("corps")
	if corps is None:
		print(f"No corps in {actual_terme}")
		sys.exit(1)

	variante = None
	for v in corps.findall("variante"):
		if v.get("num", "1") == variante_num:
			variante = v
			break

	if variante is None:
		nums = [v.get("num", "1") for v in corps.findall("variante")]
		print(f"Variante {variante_num} not found in {actual_terme}. Available: {nums}")
		sys.exit(1)

	indents = variante.findall("indent")
	if indent_num < 1 or indent_num > len(indents):
		print(f"Indent {indent_num} out of range for {actual_terme}.{variante_num} (has {len(indents)})")
		sys.exit(1)

	indent = indents[indent_num - 1]
	print(f"# {actual_terme}.{variante_num}.{indent_num}")
	print(etree.tostring(indent, encoding="unicode", pretty_print=True).rstrip())


if __name__ == "__main__":
	main()
