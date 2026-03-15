"""Find indent elements where a citation's tail text contains a transition label.

These are cases where Littré's text has a mid-indent usage shift
(e.g. "Absolument.") encoded as bare text between citations, which
the parser concatenates into the definition content.

Fix: split the indent at the transition boundary so the label starts
a new <indent> element with its trailing citations.

Usage:
    PYTHONPATH=src python scripts/find_cit_tail_transitions.py data/source/
"""

import re
import sys
from pathlib import Path
from lxml import etree

transition_re = re.compile(
	r"^(Absolument|Substantivement|Familièrement|Neutralement|Activement|"
	r"Figurément|Fig\.|Par extension|Par exagération|Populairement|Poétiquement|"
	r"Impersonnellement|Au pluriel|Au singulier|Au féminin|Au masculin|"
	r"Proverbialement|V\.\s*(n|a|réfl)|S'\w+,\s*v\.\s*réfl)\b"
)

source_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/source")
total = 0

for xml_path in sorted(source_dir.glob("*.xml")):
	tree = etree.parse(str(xml_path))
	for indent in tree.iter("indent"):
		children = list(indent)
		for i, child in enumerate(children):
			if child.tag != "cit" or not child.tail:
				continue
			tail = child.tail.strip()
			if not tail or not transition_re.match(tail):
				continue

			entry = indent
			while entry is not None and entry.tag != "entree":
				entry = entry.getparent()
			headword = entry.get("terme", "?") if entry is not None else "?"

			var = indent
			while var is not None and var.tag != "variante":
				var = var.getparent()
			vnum = var.get("num", "?") if var is not None else "?"

			cit_author = child.get("aut", "?")
			cit_count_before = i + 1
			cit_count_after = sum(1 for c in children[i + 1:] if c.tag == "cit")
			def_start = (indent.text or "").strip()[:60]

			total += 1
			print(f"{total:2}. {xml_path.name} | {headword} v{vnum}")
			print(f"    transition: \"{tail}\"")
			print(f"    after cit by: {cit_author}")
			print(f"    cits before/after split: {cit_count_before} / {cit_count_after}")
			print(f"    def starts: \"{def_start}\"")
			print()

print(f"Total: {total}")
