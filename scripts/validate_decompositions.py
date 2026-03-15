"""Validate decomposition form/gloss pairs.

Reads JSONL from decompose.py, applies deterministic checks, optionally
runs Sonnet via the Anthropic API for a sanity check, and writes scored output.

Usage:
	python scripts/validate_decompositions.py decompose_fallback_mistral.jsonl
	python scripts/validate_decompositions.py decompose_fallback_mistral.jsonl --llm
	python scripts/validate_decompositions.py decompose_fallback_mistral.jsonl --llm \
		--llm-on REVIEW LIKELY_OK

Requires ANTHROPIC_API_KEY for --llm.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from anthropic import Anthropic

french_articles = frozenset([
	"un", "une", "le", "la", "les", "l'", "des", "du", "de", "d'",
])

llm_prompt = """\
Here is a phrase and definition extracted from a French dictionary \
entry for the headword {headword}:

FORM: {form}
GLOSS: {gloss}

Are the FORM and GLOSS both sensible, standalone phrases?
Answer only "yes" or "no"."""


def headword_prefix(headword, min_length=4):
	head = headword.split(",")[0].strip().lower()
	return head[:max(min_length, len(head) // 2)]


def has_letters(text):
	return bool(re.search(r"[a-zA-ZÀ-ÿ]", text))


def find_boundary_punctuation(content, form, gloss):
	"""Check that punctuation separates form and gloss in the original text.

	Looks for: ...form<whitespace?><punct><whitespace?>gloss...
	Punctuation can be: , ; : .
	"""
	form_start = content.find(form)
	if form_start == -1:
		return False

	form_end = form_start + len(form)
	remaining = content[form_end:]

	match = re.match(r"^\s*([,;:.])\s*", remaining)
	if not match:
		return False

	after_punct = remaining[match.end():]
	gloss_clean = gloss.strip()
	if not gloss_clean:
		return False

	return after_punct.startswith(gloss_clean[:20])


def validate(record):
	form = record.get("form", "")
	gloss = record.get("gloss", "")
	headword = record.get("headword", "")
	content = record.get("content", "")
	head = headword.split(",")[0].strip().lower()
	prefix = headword_prefix(headword)
	form_lower = form.lower().strip()

	checks = {}

	# --- Hard gates ---

	checks["form_has_letters"] = has_letters(form)
	checks["gloss_has_letters"] = has_letters(gloss)

	checks["headword_in_form"] = (
		head in form_lower
		or prefix in form_lower
	)

	reconstruction = form + ", " + gloss
	recon_words = set(reconstruction.lower().split())
	content_words = set(content.lower().split()[:30])
	overlap = len(recon_words & content_words)
	checks["reconstruction_plausible"] = overlap >= min(
		3, len(content.split()) // 2
	)

	# --- Soft checks ---

	checks["not_bare_headword"] = form_lower != head

	checks["form_is_phrase"] = len(form) < len(content) * 0.7

	checks["punctuation_at_boundary"] = find_boundary_punctuation(
		content, form, gloss
	)

	grammar_markers = [
		"se conjugue", "v. n.", "v. a.", "v. réfl.", "veut le",
		"régit", "se met après", "se met avant",
		"se dit aussi absolument",
	]
	checks["gloss_is_definitional"] = not any(
		m in gloss.lower() for m in grammar_markers
	)

	context_prefixes = [
		"en prose", "en droit", "en musique", "en peinture",
		"en jurisprudence", "en botanique", "en somme",
		"en mathématiques", "en physique", "en chimie",
		"en architecture", "en médecine", "en pharmacie",
		"au jeu de", "au jeu du", "aux loteries",
		"chez les", "chez quelques",
		"dans le même sens", "dans le sens",
		"en termes de", "en termes d'",
		"en parlant", "en ce sens", "en mauvaise part",
		"en bonne part", "en recevant",
	]
	starts_with_context = any(
		form_lower.startswith(p) for p in context_prefixes
	)
	checks["form_not_context"] = not starts_with_context or head in form_lower

	commentary_starts = [
		"mot qui", "cette locution", "on dit aussi",
		"on dit dans", "on dit de", "on dit quelquefois",
		"bon mot", "mot très", "loc.", "fig.",
		"cette expression", "cet adjectif",
		"il se dit", "il ne se dit", "on le dit",
		"on le fait", "on trouve aussi",
		"on l'a dit", "avec de et",
	]
	checks["form_not_commentary"] = not any(
		form_lower.startswith(p) for p in commentary_starts
	)

	return checks


hard_gates = [
	"form_has_letters",
	"gloss_has_letters",
	"headword_in_form",
	"reconstruction_plausible",
]


def score(checks):
	for gate in hard_gates:
		if not checks.get(gate):
			return "BAD"

	soft_checks = {k: v for k, v in checks.items() if k not in hard_gates}
	soft_passing = sum(1 for v in soft_checks.values() if v)
	soft_total = len(soft_checks)

	if soft_passing == soft_total:
		return "CLEAN"
	elif soft_passing >= soft_total - 1:
		return "LIKELY_OK"
	else:
		return "REVIEW"


def query_sonnet(client, headword, form, gloss):
	prompt = llm_prompt.format(headword=headword, form=form, gloss=gloss)
	response = client.messages.create(
		model="claude-sonnet-4-6",
		max_tokens=5,
		messages=[{"role": "user", "content": prompt}],
	)
	raw = response.content[0].text.strip().lower()
	tokens_in = response.usage.input_tokens
	tokens_out = response.usage.output_tokens
	is_yes = "yes" in raw and "no" not in raw
	return is_yes, raw, tokens_in, tokens_out


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("input", help="JSONL from decompose.py")
	parser.add_argument("--output", default=None)
	parser.add_argument("--llm", action="store_true", help="Enable Sonnet sanity check")
	parser.add_argument("--llm-on", nargs="+", default=["REVIEW", "LIKELY_OK"],
		help="Which verdicts to send to LLM (default: REVIEW LIKELY_OK)")
	args = parser.parse_args()

	output_path = args.output or args.input.replace(".jsonl", "_scored.jsonl")

	records = []
	with open(args.input) as f:
		for line in f:
			line = line.strip()
			if line:
				records.append(json.loads(line))

	print(f"Loaded {len(records)} records from {args.input}")
	if args.llm:
		print(f"Sonnet sanity check on: {', '.join(args.llm_on)}")
	print()

	client = Anthropic() if args.llm else None
	score_counts = {}
	llm_flips = 0
	total_input_tokens = 0
	total_output_tokens = 0

	with open(output_path, "w", encoding="utf-8") as out:
		for i, record in enumerate(records):
			checks = validate(record)
			verdict = score(checks)

			llm_verdict = None
			if args.llm and verdict in args.llm_on:
				try:
					llm_ok, raw, tok_in, tok_out = query_sonnet(
						client,
						record["headword"],
						record.get("form", ""),
						record.get("gloss", ""),
					)
					total_input_tokens += tok_in
					total_output_tokens += tok_out
					llm_verdict = "yes" if llm_ok else "no"
					if not llm_ok:
						verdict = "LLM_REJECTED"
						llm_flips += 1
					time.sleep(0.02)
				except Exception as exc:
					llm_verdict = f"ERROR:{exc}"

			score_counts[verdict] = score_counts.get(verdict, 0) + 1
			flag = "" if verdict == "CLEAN" else f"  ← {verdict}"
			form_display = record.get("form", "")[:40]
			print(
				f"[{i + 1}/{len(records)}] {record.get('indent_id', '?'):30} "
				f"{verdict:14} {form_display}"
				f"{flag}"
			)

			record["checks"] = checks
			record["verdict"] = verdict
			if llm_verdict is not None:
				record["llm_verdict"] = llm_verdict
			out.write(json.dumps(record, ensure_ascii=False) + "\n")

	print(f"\n{'=' * 60}")
	print(f"Results ({len(records)} items):")
	for verdict, count in sorted(score_counts.items(), key=lambda x: -x[1]):
		pct = 100 * count / len(records) if records else 0
		print(f"  {verdict:15} {count:5} ({pct:.1f}%)")

	if args.llm:
		# Sonnet 4.6: $3/M input, $15/M output
		cost = (total_input_tokens * 3 + total_output_tokens * 15) / 1_000_000
		print(f"\nSonnet tokens: {total_input_tokens} input, {total_output_tokens} output")
		print(f"Estimated cost: ${cost:.4f}")
		print(f"LLM rejected: {llm_flips}")

	failed = [r for r in records if r["verdict"] not in ("CLEAN",)]
	if failed:
		print(f"\nNon-CLEAN items ({len(failed)}):")
		for r in failed[:30]:
			failed_checks = [k for k, v in r.get("checks", {}).items() if not v]
			llm_tag = f" llm={r['llm_verdict']}" if "llm_verdict" in r else ""
			print(
				f"  [{r['verdict']:14}] {r.get('headword', '?'):20} "
				f"form={r.get('form', '?')[:40]}{llm_tag}"
			)
			if failed_checks:
				print(f"           failed: {', '.join(failed_checks)}")
		if len(failed) > 30:
			print(f"  ... and {len(failed) - 30} more")

	print(f"\nWrote {len(records)} scored results to {output_path}")


if __name__ == "__main__":
	main()
