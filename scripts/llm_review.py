"""Binary role classification of continuation/elaboration items using Opus.

Usage:
	ANTHROPIC_API_KEY=sk-... python scripts/llm_binary_review.py data/littre.db
	ANTHROPIC_API_KEY=sk-... python scripts/llm_binary_review.py data/littre.db --role locution --limit 100
	ANTHROPIC_API_KEY=sk-... python scripts/llm_binary_review.py data/littre.db --dry-run --limit 5
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from anthropic import Anthropic

role_prompts = {
	"locution": """\
You are classifying items from a 19th-century French dictionary.

Decide: is this item a LOCUTION or a CONTINUATION?

A locution defines a fixed phrase. It has the structure: form, then a comma, then a \
definitional gloss. The form is typically a short phrase containing the headword \
(which may appear inflected). Examples:
- DÉFAUT: "Donner défaut, donner acte de la non-comparution."
- DÉFAUT: "Le défaut de la cuirasse, l'intervalle entre les deux pièces d'une cuirasse."
- DEBOUT: "Conte à dormir debout, récit ennuyeux ; promesses en l'air."
- OPINION: "Les opinions relâchées, opinions de ceux qui ont peu de sévérité en morale."
- DÉFAUT: "Mettre en défaut, rendre inutile, déjouer."
- DÉSERT: "Prêcher dans le désert, parler sans être écouté."

A continuation is anything else: an additional sense, an elaboration, a commentary, \
a domain label, or any item that does not define a fixed phrase.

Respond with ONLY "locution" or "continuation".""",

	"domain": """\
You are classifying items from a 19th-century French dictionary.

Decide: is this item a DOMAIN LABEL (a technical field marker)?

A domain label introduces a technical field, e.g.:
- DÉFAUT: "Terme de rhétorique. Les défauts du style, vices opposés aux qualités..."
- DEBOUT: "Terme de marine. Avoir vent debout..."
- "En botanique." / "En médecine."

NOT a domain label:
- A register/style note ("Familièrement.", "Par extension.")
- A locution (fixed phrase + definition)
- A definition that merely mentions a field in passing

Respond with ONLY "yes" or "no".""",

	"register_label": """\
You are classifying items from a 19th-century French dictionary.

Decide: is this item a REGISTER LABEL (a style or usage marker)?

A register label marks style, register, or semantic shift:
- "Familièrement." / "Populairement." / "Figurément."
- "Par extension." / "Par dénigrement." / "Par analogie."
- "Vieux." / "Inusité." / "Absolument."

NOT a register label:
- A domain label ("Terme de marine.")
- A locution (fixed phrase + definition)
- Content that merely uses familiar language

Respond with ONLY "yes" or "no".""",
}


def build_prompt(row: dict) -> str:
	lines = [f"Entry: {row['headword']}"]
	if row["parent_def"]:
		parent = row["parent_def"][:200]
		lines.append(f"Parent sense (n={row['parent_num']}): {parent}")
	lines.append(f"Item text: {row['content_plain']}")
	if row["siblings"]:
		lines.append("Sibling items:")
		for sib in row["siblings"]:
			marker = ">>>" if sib["is_current"] else "   "
			lines.append(f"  {marker} [{sib['role']}] {sib['content'][:120]}")
	return "\n".join(lines)


def fetch_items(db_path: str, limit: int) -> list[dict]:
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cur = conn.cursor()

	cur.execute("""
		SELECT s.sense_id, e.headword, s.content_plain, s.role,
			p.content_plain as parent_def, p.num as parent_num,
			s.parent_sense_id
		FROM senses s
		JOIN entries e ON s.entry_id = e.entry_id
		LEFT JOIN senses p ON s.parent_sense_id = p.sense_id
		WHERE s.role IN ('continuation', 'elaboration')
		ORDER BY (s.sense_id * 2654435761) % 4294967296
		LIMIT ?
	""", (limit,))

	items = []
	for row in cur.fetchall():
		item = dict(row)
		cur.execute("""
			SELECT sense_id, content_plain, role
			FROM senses
			WHERE parent_sense_id = ?
			ORDER BY sense_id
		""", (row["parent_sense_id"],))
		siblings = []
		for sib in cur.fetchall():
			siblings.append({
				"content": sib[1] or "",
				"role": sib[2] or "",
				"is_current": sib[0] == row["sense_id"],
			})
		item["siblings"] = siblings
		items.append(item)

	conn.close()
	return items


def review_batch(
	items: list[dict],
	role: str,
	dry_run: bool = False,
) -> list[dict]:
	system = role_prompts[role]
	client = Anthropic()
	results = []
	total_input_tokens = 0
	total_output_tokens = 0

	for i, item in enumerate(items):
		prompt = build_prompt(item)

		if dry_run:
			print(f"\n{'=' * 60}")
			print(f"[{i + 1}/{len(items)}] {item['headword']} (current: {item['role']})")
			print(prompt)
			results.append({**item, "is_target": None, "prompt": prompt})
			continue

		try:
			response = client.messages.create(
				model="claude-opus-4-5",
				max_tokens=5,
				system=system,
				messages=[{"role": "user", "content": prompt}],
			)
			total_input_tokens += response.usage.input_tokens
			total_output_tokens += response.usage.output_tokens
			answer = response.content[0].text.strip().lower()
			is_target = answer.startswith("loc")
			tag = f"← {role.upper()}" if is_target else ""
			print(
				f"[{i + 1}/{len(items)}] {item['headword']:20} "
				f"pipeline={item['role']:15} opus={answer:4} {tag}"
			)

			results.append({
				"sense_id": item["sense_id"],
				"headword": item["headword"],
				"content": item["content_plain"][:200],
				"pipeline_role": item["role"],
				"opus_answer": answer,
				"is_target": is_target,
			})

			time.sleep(0.05)

		except Exception as exc:
			print(f"[{i + 1}] ERROR {item['headword']}: {exc}", file=sys.stderr)
			results.append({
				"sense_id": item["sense_id"],
				"headword": item["headword"],
				"pipeline_role": item["role"],
				"opus_answer": f"ERROR:{exc}",
				"is_target": None,
			})

	if not dry_run:
		# Opus 4.5 pricing: $5/M input, $25/M output
		cost = (total_input_tokens * 5 + total_output_tokens * 25) / 1_000_000
		print(f"\nTokens: {total_input_tokens} input, {total_output_tokens} output")
		print(f"Estimated cost: ${cost:.4f}")

	return results


def print_summary(results: list[dict], role: str) -> None:
	valid = [r for r in results if r.get("is_target") is not None]
	positives = sum(1 for r in valid if r["is_target"])
	negatives = len(valid) - positives
	print(f"\n{'=' * 60}")
	print(f"Role: {role}")
	print(f"Total: {len(valid)}  Positive: {positives}  Negative: {negatives}")
	if valid:
		rate = 100 * positives / len(valid)
		print(f"Positive rate: {rate:.1f}%")

	if positives:
		print(f"\nReclassified as {role}:")
		by_pipeline = {}
		for r in valid:
			if r["is_target"]:
				by_pipeline.setdefault(r["pipeline_role"], []).append(r)
		for pipeline_role, items in sorted(by_pipeline.items()):
			print(f"  from {pipeline_role}: {len(items)}")
			for item in items[:5]:
				content = item.get("content", "")[:80]
				print(f"    {item['headword']:20} {content}")
			if len(items) > 5:
				print(f"    ... and {len(items) - 5} more")


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("db_path", nargs="?", default="data/littre.db")
	parser.add_argument("--role", default="locution", choices=role_prompts.keys())
	parser.add_argument("--limit", type=int, default=100)
	parser.add_argument("--dry-run", action="store_true")
	parser.add_argument("--output", default=None)
	args = parser.parse_args()

	output_path = args.output or f"llm_opus_{args.role}.json"

	print(f"Binary review: is it a {args.role}?")
	print(f"Fetching {args.limit} items from {args.db_path}...")
	items = fetch_items(args.db_path, args.limit)
	print(f"Got {len(items)} items\n")

	results = review_batch(items, args.role, dry_run=args.dry_run)

	if not args.dry_run:
		print_summary(results, args.role)
		Path(output_path).write_text(
			json.dumps(results, indent=2, ensure_ascii=False)
		)
		print(f"\nResults written to {output_path}")


if __name__ == "__main__":
	main()
