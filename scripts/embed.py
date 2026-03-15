"""Embed dictionary indents using Qwen3-embedding via Ollama.

Extracts text from each <indent> in the Gannaz XML, prepends the
headword, and writes one JSON object per line with the doc_id and
embedding vector.

Usage:
	python scripts/embed.py data/source/d.xml -o data/embeddings/d.jsonl
	python scripts/embed.py data/source/*.xml -o data/embeddings/all.jsonl \
		--dedup-map data/dedup_map.json

Requires Ollama running with qwen3-embedding pulled:
	ollama pull qwen3-embedding
"""

import argparse
import json
import sys
from pathlib import Path

import requests
from lxml import etree

from utils import (
	headword_for_prepend,
	load_dedup_map,
	make_indent_id,
)


ollama_url = "http://localhost:11434/api/embed"
model_name = "qwen3-embedding:8b"
default_batch_size = 64


def extract_indent_text(indent):
	parts = []
	if indent.text:
		parts.append(indent.text)
	for child in indent:
		if child.tag != "cit":
			parts.append(etree.tostring(child, method="text", encoding="unicode"))
		if child.tail:
			parts.append(child.tail)
	return " ".join("".join(parts).split()).strip()


def extract_indents(xml_path, dedup_map=None):
	tree = etree.parse(xml_path)
	root = tree.getroot()
	for entry in root.findall(".//entree"):
		terme = entry.get("terme", "")
		sens = entry.get("sens")
		is_supplement = entry.get("supplement") == "1"
		corps = entry.find("corps")
		if corps is None:
			continue
		headword = headword_for_prepend(terme)
		for variante in corps.findall("variante"):
			variante_num = variante.get("num", "1")
			for i, indent in enumerate(variante.findall("indent"), 1):
				text = extract_indent_text(indent)
				if not text:
					continue
				indent_id = make_indent_id(
					terme, variante_num, i,
					sens=sens, dedup_map=dedup_map,
					is_supplement=is_supplement,
				)
				yield {
					"id": indent_id,
					"headword": headword,
					"text": text,
				}


def embed_batch(texts):
	response = requests.post(ollama_url, json={
		"model": model_name,
		"input": texts,
	})
	response.raise_for_status()
	return response.json()["embeddings"]


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("xml_files", nargs="+")
	parser.add_argument("-o", "--output", required=True)
	parser.add_argument("--batch-size", type=int, default=default_batch_size)
	parser.add_argument("--dedup-map", default=None)
	args = parser.parse_args()

	dedup_map = load_dedup_map(args.dedup_map) if args.dedup_map else None

	output = Path(args.output)
	output.parent.mkdir(parents=True, exist_ok=True)

	total = 0
	with output.open("w", encoding="utf-8") as out:
		for xml_path in args.xml_files:
			print(f"Processing {xml_path}...", file=sys.stderr)
			indents = list(extract_indents(xml_path, dedup_map))
			print(f"  {len(indents)} indents", file=sys.stderr)

			batch_items = []
			batch_texts = []

			for item in indents:
				annotated_text = f"{item['headword']}: {item['text']}"

				batch_items.append({"id": item["id"], "text": annotated_text[:200]})
				batch_texts.append(annotated_text)

				if len(batch_texts) >= args.batch_size:
					embeddings = embed_batch(batch_texts)
					for bi, vec in zip(batch_items, embeddings):
						out.write(json.dumps({
							"id": bi["id"],
							"text": bi["text"],
							"embedding": vec,
						}, ensure_ascii=False) + "\n")
					total += len(batch_items)
					print(f"  {total}...", file=sys.stderr)
					batch_items = []
					batch_texts = []

			if batch_texts:
				embeddings = embed_batch(batch_texts)
				for bi, vec in zip(batch_items, embeddings):
					out.write(json.dumps({
						"id": bi["id"],
						"text": bi["text"],
						"embedding": vec,
					}, ensure_ascii=False) + "\n")
				total += len(batch_items)

	print(f"\nWrote {total} embeddings to {args.output}", file=sys.stderr)


if __name__ == "__main__":
	main()
