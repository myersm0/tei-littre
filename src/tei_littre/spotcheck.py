#!/usr/bin/env python3
"""Side-by-side TUI spot-checker for XMLittré source vs TEI Lex-0."""

import argparse
import json
import re
import unicodedata
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Rule
from textual.containers import Horizontal, ScrollableContainer
from textual.binding import Binding

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


# ── Index & extraction ──────────────────────────────────────────────

SOURCE_ENTRY_RE = re.compile(rb'<entree\s+terme="([^"]+)"(?:\s+sens="(\d+)")?')
TEI_ENTRY_RE = re.compile(rb'<entry\s+xml:id="([^"]+)"')
TEI_OPEN_RE = re.compile(rb"<entry[\s>]")
TEI_CLOSE = b"</entry>"
SOURCE_CLOSE = b"</entree>"


def normalize_key(s):
	s = s.upper()
	return "".join(
		c for c in unicodedata.normalize("NFD", s)
		if unicodedata.category(c) != "Mn"
	)


INDEX_VERSION = 3


def build_index(source_dir, tei_file):
	source_dir = Path(source_dir)
	tei_file = Path(tei_file)
	index = {"version": INDEX_VERSION, "source": {}, "tei": {}}
	for xml_file in sorted(source_dir.glob("*.xml")):
		fname = xml_file.name
		with open(xml_file, "rb") as f:
			offset = 0
			for line in f:
				m = SOURCE_ENTRY_RE.search(line)
				if m:
					terme = m.group(1).decode("utf-8")
					sens = m.group(2).decode("utf-8") if m.group(2) else None
					key = normalize_key(terme)
					index["source"].setdefault(key, []).append({
						"file": fname, "offset": offset, "sens": sens,
					})
				offset += len(line)
	with open(tei_file, "rb") as f:
		offset = 0
		for line in f:
			m = TEI_ENTRY_RE.search(line)
			if m:
				entry_id = m.group(1).decode("utf-8")
				base = normalize_key(entry_id.split(".")[0])
				index["tei"].setdefault(base, []).append({
					"offset": offset, "id": entry_id,
				})
			offset += len(line)
	return index


def load_or_build_index(source_dir, tei_file, index_path, force=False):
	index_path = Path(index_path)
	if not force and index_path.exists():
		with open(index_path) as f:
			index = json.load(f)
		if index.get("version") == INDEX_VERSION:
			return index
	import sys
	print("Building index...", file=sys.stderr, end=" ", flush=True)
	index = build_index(source_dir, tei_file)
	index_path.parent.mkdir(parents=True, exist_ok=True)
	with open(index_path, "w") as f:
		json.dump(index, f)
	print("done.", file=sys.stderr)
	return index


def extract_source_entry(filepath, offset):
	with open(filepath, "rb") as f:
		f.seek(offset)
		chunks = []
		for line in f:
			chunks.append(line)
			if SOURCE_CLOSE in line:
				break
	return b"".join(chunks).decode("utf-8", errors="replace")


def extract_tei_entry(filepath, offset):
	with open(filepath, "rb") as f:
		f.seek(offset)
		depth = 0
		chunks = []
		for line in f:
			depth += len(TEI_OPEN_RE.findall(line))
			depth -= line.count(TEI_CLOSE)
			chunks.append(line)
			if depth <= 0:
				break
	return b"".join(chunks).decode("utf-8", errors="replace")


# ── Section splitting ───────────────────────────────────────────────

RUBRIQUE_MAP = {
	"HISTORIQUE": "historique",
	"ÉTYMOLOGIE": "étymologie",
	"SUPPLÉMENT AU DICTIONNAIRE": "supplément",
	"REMARQUE": "remarque",
	"REMARQUES": "remarque",
	"SYNONYME": "synonyme",
	"PROVERBE": "proverbes",
	"PROVERBES": "proverbes",
}

LABEL_STYLES = {
	"header": ("", "bright_white"),
	"historique": ("HISTORIQUE", "yellow"),
	"étymologie": ("ÉTYMOLOGIE", "green"),
	"supplément": ("SUPPLÉMENT", "magenta"),
	"remarque": ("REMARQUE", "bright_yellow"),
	"synonyme": ("SYNONYME", "cyan"),
	"proverbes": ("PROVERBES", "bright_magenta"),
}


def section_display_name(label):
	if label.startswith("sense-"):
		return f"§{label.split('-', 1)[1]}"
	info = LABEL_STYLES.get(label)
	if info and info[0]:
		return info[0]
	return label.upper()


def section_border_style(label):
	if label.startswith("sense-"):
		return "cyan"
	return LABEL_STYLES.get(label, ("", "white"))[1]


def split_source_sections(xml_text):
	sections = []
	current_label = "header"
	current_lines = []
	in_rubrique = False

	for line in xml_text.splitlines(keepends=True):
		stripped = line.strip()

		if stripped.startswith("<rubrique "):
			if current_lines:
				sections.append((current_label, "".join(current_lines)))
			m = re.search(r'nom="([^"]+)"', stripped)
			rub_name = m.group(1) if m else "unknown"
			current_label = RUBRIQUE_MAP.get(rub_name, rub_name.lower())
			current_lines = [line]
			in_rubrique = True
			continue

		if stripped == "</rubrique>":
			current_lines.append(line)
			sections.append((current_label, "".join(current_lines)))
			current_label = "_gap"
			current_lines = []
			in_rubrique = False
			continue

		if not in_rubrique:
			m = re.match(r"<variante\s+num=\"([^\"]+)\"", stripped)
			if m:
				if current_lines:
					sections.append((current_label, "".join(current_lines)))
				current_label = f"sense-{m.group(1)}"
				current_lines = [line]
				continue

			if stripped == "<variante>" or stripped.startswith("<variante>"):
				if current_lines:
					sections.append((current_label, "".join(current_lines)))
				current_label = "sense"
				current_lines = [line]
				continue

		current_lines.append(line)

	if current_lines and current_label != "_gap":
		sections.append((current_label, "".join(current_lines)))

	return [(l, t) for l, t in sections if l != "_gap"]


def split_tei_sections(xml_text):
	lines = xml_text.splitlines(keepends=True)

	body_indent = None
	for line in lines:
		m = re.match(r"^(\s+)<(form|gramGrp|sense|note|etym|re)\b", line)
		if m:
			body_indent = len(m.group(1))
			break

	if body_indent is None:
		return [("full", xml_text)]

	indent_prefix = " " * body_indent
	deeper_prefix = " " * (body_indent + 1)

	sections = []
	current_label = "header"
	current_lines = []

	for line in lines:
		at_body_level = line.startswith(indent_prefix) and not line.startswith(deeper_prefix)

		if at_body_level:
			stripped = line.strip()
			if stripped.startswith("</"):
				current_lines.append(line)
				continue

			new_label = None

			m = re.match(r'<sense\s+n="(\d+)"', stripped)
			if m:
				new_label = f"sense-{m.group(1)}"

			if not new_label:
				m = re.match(r'<note\s+type="([^"]+)"', stripped)
				if m:
					new_label = m.group(1)

			if not new_label and (stripped.startswith("<etym>") or stripped.startswith("<etym ")):
				new_label = "étymologie"

			if not new_label:
				m = re.match(r'<re\s+type="([^"]+)"', stripped)
				if m:
					new_label = m.group(1)

			if new_label:
				if current_lines:
					sections.append((current_label, "".join(current_lines)))
				current_label = new_label
				current_lines = [line]
				continue

		current_lines.append(line)

	if current_lines:
		sections.append((current_label, "".join(current_lines)))

	return sections


def align_sections(source_secs, tei_secs):
	seen = set()
	ordered_labels = []
	for label, _ in source_secs + tei_secs:
		if label not in seen:
			seen.add(label)
			ordered_labels.append(label)

	source_map = {}
	for label, text in source_secs:
		source_map.setdefault(label, []).append(text)
	tei_map = {}
	for label, text in tei_secs:
		tei_map.setdefault(label, []).append(text)

	aligned = []
	for label in ordered_labels:
		s = "\n".join(source_map.get(label, []))
		t = "\n".join(tei_map.get(label, []))
		aligned.append((label, s, t))
	return aligned


# ── Lookup logic ────────────────────────────────────────────────────

def resolve_entries(headword, index, source_dir, tei_file):
	key = normalize_key(headword)
	specific = None
	if "." in key:
		key, specific = key.rsplit(".", 1)

	source_hits = index["source"].get(key, [])
	tei_hits = index["tei"].get(key, [])

	if specific:
		source_hits = [h for h in source_hits if h["sens"] == specific]
		tei_hits = [h for h in tei_hits if h["id"].endswith(f".{specific}")]

	pairs = []
	max_len = max(len(source_hits), len(tei_hits), 1)
	for i in range(max_len):
		s_text = ""
		s_label = ""
		if i < len(source_hits):
			hit = source_hits[i]
			path = str(Path(source_dir) / hit["file"])
			s_text = extract_source_entry(path, hit["offset"])
			s_label = key + (f".{hit['sens']}" if hit["sens"] else "")

		t_text = ""
		t_label = ""
		if i < len(tei_hits):
			hit = tei_hits[i]
			t_text = extract_tei_entry(tei_file, hit["offset"])
			t_label = hit["id"]

		pairs.append((s_label or t_label, s_text, t_text))

	return pairs


# ── Textual app ─────────────────────────────────────────────────────

class SensePanel(Static):
	DEFAULT_CSS = """
	SensePanel {
		width: 1fr;
		height: auto;
	}
	"""

	def __init__(self, xml_text, title="", border_style="white", **kwargs):
		super().__init__(**kwargs)
		self._xml = xml_text
		self._title = title
		self._border = border_style

	def render(self):
		if not self._xml.strip():
			return Panel(
				Text("—", style="dim"),
				title=self._title,
				border_style="dim",
			)
		syntax = Syntax(
			self._xml.rstrip(),
			"xml",
			theme="ansi_dark",
			word_wrap=True,
			padding=(0, 1),
		)
		return Panel(syntax, title=self._title, border_style=self._border)


class SpotCheckApp(App):
	CSS = """
	#body {
		overflow-y: auto;
	}
	.sense-row {
		height: auto;
	}
	.section-rule {
		margin: 0 1;
		color: $surface-lighten-3;
	}
	"""

	BINDINGS = [
		Binding("q", "quit", "Quit"),
		Binding("j", "scroll_down", "Down", show=False),
		Binding("k", "scroll_up", "Up", show=False),
		Binding("g", "scroll_home", "Top", show=False),
		Binding("G", "scroll_end", "Bottom", show=False),
		Binding("d", "half_page_down", "½ Page Down", show=False),
		Binding("u", "half_page_up", "½ Page Up", show=False),
		Binding("space", "page_down", "Page Down"),
		Binding("b", "page_up", "Page Up"),
	]

	def __init__(self, headword, pairs, **kwargs):
		self.headword = headword
		self.pairs = pairs
		super().__init__(**kwargs)

	def compose(self) -> ComposeResult:
		yield Header()
		with ScrollableContainer(id="body"):
			for entry_label, source_xml, tei_xml in self.pairs:
				source_secs = split_source_sections(source_xml) if source_xml else []
				tei_secs = split_tei_sections(tei_xml) if tei_xml else []
				aligned = align_sections(source_secs, tei_secs)

				for label, s_text, t_text in aligned:
					disp = section_display_name(label)
					style = section_border_style(label)
					with Horizontal(classes="sense-row"):
						yield SensePanel(
							s_text,
							title=f"SOURCE {disp}",
							border_style=style,
						)
						yield SensePanel(
							t_text,
							title=f"TEI {disp}",
							border_style=style,
						)
		yield Footer()

	def on_mount(self):
		self.title = f"spotcheck: {self.headword}"

	def action_scroll_down(self):
		self.query_one("#body").scroll_down(animate=False)

	def action_scroll_up(self):
		self.query_one("#body").scroll_up(animate=False)

	def action_scroll_home(self):
		self.query_one("#body").scroll_home(animate=False)

	def action_scroll_end(self):
		self.query_one("#body").scroll_end(animate=False)

	def action_half_page_down(self):
		body = self.query_one("#body")
		body.scroll_to(y=body.scroll_y + body.size.height // 2, animate=False)

	def action_half_page_up(self):
		body = self.query_one("#body")
		body.scroll_to(y=max(0, body.scroll_y - body.size.height // 2), animate=False)

	def action_page_down(self):
		body = self.query_one("#body")
		body.scroll_to(y=body.scroll_y + body.size.height, animate=False)

	def action_page_up(self):
		body = self.query_one("#body")
		body.scroll_to(y=max(0, body.scroll_y - body.size.height), animate=False)


# ── CLI ─────────────────────────────────────────────────────────────

def main():
	parser = argparse.ArgumentParser(
		description="Side-by-side spot-checker for XMLittré source vs TEI Lex-0"
	)
	parser.add_argument("headword", help="Headword to look up (e.g. DEMEURE, da.2)")
	parser.add_argument("--source-dir", default="data/source")
	parser.add_argument("--tei-file", default="data/littre.tei.xml")
	parser.add_argument("--index", default=".spotcheck_index.json")
	parser.add_argument("--reindex", action="store_true")
	args = parser.parse_args()

	index = load_or_build_index(
		args.source_dir, args.tei_file, args.index, force=args.reindex
	)
	pairs = resolve_entries(args.headword, index, args.source_dir, args.tei_file)
	if not pairs:
		import sys
		print(f"Not found: {args.headword}", file=sys.stderr)
		sys.exit(1)

	app = SpotCheckApp(args.headword, pairs)
	app.run()


if __name__ == "__main__":
	main()
