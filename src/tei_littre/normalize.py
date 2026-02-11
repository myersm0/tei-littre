"""
Phase 0: Mechanical normalization of Gannaz XML files.

Produces cleaned copies ready for parsing. All changes are
lossless and reversible.
"""

import re
import sys
from pathlib import Path


def normalize(text: str) -> str:
	text = text.replace('nom="PROVERBE"', 'nom="PROVERBES"')
	text = text.replace('nom="REMARQUES"', 'nom="REMARQUE"')
	text = re.sub(
		r'<span\s+lang="la">(.*?)</span>',
		r'<i lang="la">\1</i>',
		text,
		flags=re.DOTALL,
	)
	return text


def normalize_file(source: Path, dest: Path) -> None:
	text = source.read_text(encoding="utf-8")
	normalized = normalize(text)
	dest.write_text(normalized, encoding="utf-8")
	changes = 0
	if text != normalized:
		changes = sum(
			a != b for a, b in zip(text, normalized)
		)
	print(f"  {source.name} -> {dest.name} ({changes} chars changed)")


def main(source_dir: str, dest_dir: str) -> None:
	src = Path(source_dir)
	dst = Path(dest_dir)
	dst.mkdir(parents=True, exist_ok=True)

	xml_files = sorted(src.glob("*.xml"))
	if not xml_files:
		print(f"No XML files found in {src}")
		sys.exit(1)

	print(f"Normalizing {len(xml_files)} files from {src} -> {dst}")
	for f in xml_files:
		normalize_file(f, dst / f.name)
	print("Done.")


if __name__ == "__main__":
	if len(sys.argv) != 3:
		print("Usage: python normalize.py <source_dir> <dest_dir>")
		sys.exit(1)
	main(sys.argv[1], sys.argv[2])
