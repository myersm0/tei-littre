"""Stanza annotation of dictionary indents for classification.

Extracts text from each <indent> in the Gannaz XML, prepends the
headword, segments with CoreNLP, annotates with Stanza (GSD model),
and outputs CoNLL-U.

Requires CORENLP_HOME to be set. Uses CoreNLP only for sentence
segmentation (tokenize+ssplit); Stanza handles tokenization, MWT,
POS, lemma, and dependency parsing.

Usage:
	CORENLP_HOME=/path/to/corenlp \
	python scripts/annotate.py data/source/d.xml -o data/stanza_d.conllu

	CORENLP_HOME=/path/to/corenlp \
	python scripts/annotate.py data/source/*.xml -o data/stanza_all.conllu \
		--dedup-map data/dedup_map.json
"""

import argparse
import os
import sys
from pathlib import Path

import stanza
from stanza.server import CoreNLPClient
from lxml import etree

from utils import (
	headword_for_prepend,
	load_dedup_map,
	make_indent_id,
)


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
					"variante": variante_num,
					"indent_index": i,
					"has_citations": len(indent.findall("cit")) > 0,
					"sibling_count": len(variante.findall("indent")),
				}


trivial_sentences = frozenset((".", ",", ";", ":", ""))


def segment(text, corenlp_client, props):
	doc = corenlp_client.annotate(text, properties=props)
	sentences = []
	for sent in doc.sentence:
		sent_text = "".join(t.word + t.after for t in sent.token).strip()
		sent_text = " ".join(sent_text.split())
		if sent_text and sent_text not in trivial_sentences:
			sentences.append(sent_text)
	return sentences


def doc_to_conllu(stanza_doc, sent_id):
	if not stanza_doc.sentences:
		return ""
	sentence = stanza_doc.sentences[0]
	lines = []
	lines.append(f"# sent_id = {sent_id}")
	lines.append(f"# text = {sentence.text}")
	for token in sentence.tokens:
		if len(token.words) > 1:
			token_range = f"{token.words[0].id}-{token.words[-1].id}"
			lines.append(f"{token_range}\t{token.text}\t_\t_\t_\t_\t_\t_\t_\t_")
		for word in token.words:
			fields = [
				str(word.id),
				word.text,
				word.lemma or "_",
				word.upos or "_",
				word.xpos or "_",
				word.feats or "_",
				str(word.head),
				word.deprel or "_",
				"_",
				"_",
			]
			lines.append("\t".join(fields))
	lines.append("")
	return "\n".join(lines)


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("xml_files", nargs="+")
	parser.add_argument("-o", "--output", required=True)
	parser.add_argument("--dedup-map", default=None)
	args = parser.parse_args()

	if not os.environ.get("CORENLP_HOME"):
		sys.exit("Error: CORENLP_HOME not set")

	dedup_map = load_dedup_map(args.dedup_map) if args.dedup_map else None

	print("Loading Stanza fr/gsd...", file=sys.stderr)
	stanza.download("fr", package="gsd", processors="tokenize,mwt,pos,lemma,depparse", verbose=False)
	nlp = stanza.Pipeline(
		lang="fr",
		package="gsd",
		processors="tokenize,mwt,pos,lemma,depparse",
		tokenize_no_ssplit=True,
		verbose=False,
	)

	corenlp_props = {
		"pipelineLanguage": "fr",
		"ssplit.newlineIsSentenceBreak": "two",
	}

	output = Path(args.output)
	with output.open("w", encoding="utf-8") as out, \
		CoreNLPClient(
			annotators=["tokenize", "ssplit"],
			properties=corenlp_props,
			be_quiet=True,
		) as corenlp:

		for xml_path in args.xml_files:
			print(f"Processing {xml_path}...", file=sys.stderr)
			indents = list(extract_indents(xml_path, dedup_map))
			print(f"  {len(indents)} indents", file=sys.stderr)

			for idx, item in enumerate(indents):
				if idx % 500 == 0 and idx > 0:
					print(f"  {idx}/{len(indents)}", file=sys.stderr)

				doc_id = item["id"]
				annotated_text = f"{item['headword']}: {item['text']}"

				sentences = segment(annotated_text, corenlp, corenlp_props)

				metadata = [
					f"# newdoc id = {doc_id}",
					f"# headword = {item['headword']}",
					f"# variante = {item['variante']}",
					f"# indent = {item['indent_index']}",
					f"# has_citations = {str(item['has_citations']).lower()}",
					f"# sibling_count = {item['sibling_count']}",
				]
				out.write("\n".join(metadata) + "\n")

				for sent_idx, sent_text in enumerate(sentences):
					if len(sentences) > 1:
						sent_id = f"{doc_id}.s{sent_idx}"
					else:
						sent_id = doc_id
					stanza_doc = nlp(sent_text)
					conllu = doc_to_conllu(stanza_doc, sent_id)
					if conllu:
						out.write(conllu)
						out.write("\n")

	print(f"\nWrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
	main()
