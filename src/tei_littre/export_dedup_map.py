"""Export dedup collision map from the SQLite database.

Produces a JSON file mapping base_id → list of suffixed entry records,
for use by external scripts (embeddings, CoNLL-U) that need to resolve
accent-collision IDs.

Usage:
	python -m tei_littre.export_dedup_map data/output/littre.db -o data/output/dedup_map.json
"""

import argparse
import json
import re
import sqlite3
import sys


suffix_pattern = re.compile(r"^(.+)_(\d+)$")


def export_dedup_map(db_path: str) -> dict:
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute(
		"SELECT entry_id, headword, pos, is_supplement "
		"FROM entries WHERE entry_id GLOB '*_[0-9]' "
		"ORDER BY entry_id"
	)
	groups: dict[str, list[dict]] = {}
	for entry_id, headword, pos, is_supplement in cur.fetchall():
		m = suffix_pattern.match(entry_id)
		if not m:
			continue
		base = m.group(1)
		groups.setdefault(base, []).append({
			"entry_id": entry_id,
			"headword": headword,
			"pos": pos or "",
			"is_supplement": bool(is_supplement),
		})
	conn.close()
	return groups


def main():
	parser = argparse.ArgumentParser(description="Export dedup collision map")
	parser.add_argument("db", help="Path to littre.db")
	parser.add_argument("-o", "--output", default="-", help="Output JSON path (default: stdout)")
	args = parser.parse_args()

	dedup_map = export_dedup_map(args.db)

	if args.output == "-":
		json.dump(dedup_map, sys.stdout, ensure_ascii=False, indent=2)
		print()
	else:
		with open(args.output, "w") as f:
			json.dump(dedup_map, f, ensure_ascii=False, indent=2)
		print(f"Wrote {len(dedup_map)} collision groups to {args.output}", file=sys.stderr)


if __name__ == "__main__":
	main()