import json
import unicodedata
from pathlib import Path


def normalize_terme(terme):
	nfkd = unicodedata.normalize("NFKD", terme)
	ascii_only = "".join(
		c for c in nfkd if not unicodedata.combining(c)
	)
	result = ascii_only.lower()
	cleaned = []
	for c in result:
		if c.isalnum() or c == "-":
			cleaned.append(c)
		else:
			cleaned.append("_")
	result = "".join(cleaned)
	while "__" in result:
		result = result.replace("__", "_")
	result = result.strip("_")
	return result


def load_dedup_map(path):
	"""Load the dedup collision map.

	Structure: {normalized_slug: [{entry_id, headword, pos, is_supplement}, ...]}
	Returns a lookup: {(headword, is_supplement): entry_id} for colliding entries.
	"""
	raw = json.loads(Path(path).read_text(encoding="utf-8"))
	lookup = {}
	for entries in raw.values():
		for entry in entries:
			key = (entry["headword"], entry["is_supplement"])
			lookup[key] = entry["entry_id"]
	return lookup


def make_entry_slug(terme, sens=None, dedup_map=None, is_supplement=False):
	slug = normalize_terme(terme)
	if dedup_map:
		key = (terme, is_supplement)
		if key in dedup_map:
			slug = dedup_map[key]
	if sens:
		slug = f"{slug}.{sens}"
	return slug


def make_indent_id(terme, variante_num, indent_pos, sens=None, dedup_map=None, is_supplement=False):
	slug = make_entry_slug(terme, sens, dedup_map, is_supplement)
	return f"{slug}.{variante_num}.{indent_pos}"


def headword_for_prepend(terme):
	"""Strip feminine forms for clean headword prepend: 'DÉGOÛTÉ, ÉE' → 'DÉGOÛTÉ'."""
	return terme.split(",")[0].strip()
