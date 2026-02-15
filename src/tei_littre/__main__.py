"""
Main pipeline driver. Chains all phases and produces outputs.

Usage: python -m tei_littre <source_dir> <output_dir>
"""

import sys
from pathlib import Path

from tei_littre.parse import parse_all
from tei_littre.resolve_authors import resolve_all
from tei_littre.classify_indents import classify_all
from tei_littre.extract_locutions import extract_all as extract_locutions
from tei_littre.scope_transitions import scope_all as scope_transitions
from tei_littre.collect_flags import collect_flags
from tei_littre.emit_tei import emit_tei
from tei_littre.emit_sqlite import emit_sqlite
from tei_littre.export_dedup_map import export_dedup_map


def run(source_dir: str, output_dir: str) -> None:
	out = Path(output_dir)
	out.mkdir(parents=True, exist_ok=True)

	print("=" * 60)
	print("Phase 1: Parse")
	print("=" * 60)
	entries = parse_all(source_dir)

	print()
	print("=" * 60)
	print("Phase 2: Resolve authors")
	print("=" * 60)
	resolve_all(entries)

	print()
	print("=" * 60)
	print("Phase 3: Classify indents")
	print("=" * 60)
	counts = classify_all(entries)
	total = sum(counts.values())
	unknown = counts.get("unknown", 0)
	print(f"  Classified {total - unknown}/{total} ({(total-unknown)/total*100:.1f}%)")
	for role, count in sorted(counts.items(), key=lambda x: -x[1]):
		print(f"    {role:20} {count:6}")

	print()
	print("=" * 60)
	print("Phase 4: Extract locutions")
	print("=" * 60)
	extract_locutions(entries)

	print()
	print("=" * 60)
	print("Phase 5: Scope transitions")
	print("=" * 60)
	scope_transitions(entries)

	print()
	print("=" * 60)
	print("Collect review flags")
	print("=" * 60)
	flags = collect_flags(entries)
	by_type = {}
	for f in flags:
		by_type[f.flag_type] = by_type.get(f.flag_type, 0) + 1
	print(f"  {len(flags)} flags total")
	for ft, count in sorted(by_type.items(), key=lambda x: -x[1]):
		print(f"    {ft:25} {count:6}")

	print()
	print("=" * 60)
	print("Phase 7a: Emit TEI")
	print("=" * 60)
	tei_path = str(out / "littre.tei.xml")
	emit_tei(entries, tei_path)

	print()
	print("=" * 60)
	print("Phase 7b: Emit SQLite")
	print("=" * 60)
	sqlite_path = str(out / "littre.db")
	Path(sqlite_path).unlink(missing_ok=True)
	emit_sqlite(entries, flags, sqlite_path)

	print()
	print("=" * 60)
	print("Export dedup collision map")
	print("=" * 60)
	dedup_path = str(out / "dedup_map.json")
	dedup_map = export_dedup_map(sqlite_path)
	import json
	with open(dedup_path, "w") as f:
		json.dump(dedup_map, f, ensure_ascii=False, indent=2)
	print(f"  {len(dedup_map)} collision groups → {dedup_path}")


if __name__ == "__main__":
	if len(sys.argv) != 3:
		print("Usage: python -m tei_littre <source_dir> <output_dir>")
		sys.exit(1)
	run(sys.argv[1], sys.argv[2])