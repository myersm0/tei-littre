# ── Schema ───────────────────────────────────────────────────────

const schema_sql = """
CREATE TABLE entries (
	entry_id TEXT PRIMARY KEY,
	headword TEXT NOT NULL,
	homograph_index INTEGER,
	pronunciation TEXT,
	pos TEXT,
	is_supplement INTEGER DEFAULT 0,
	source_letter TEXT
);

CREATE TABLE senses (
	sense_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL REFERENCES entries(entry_id),
	parent_sense_id INTEGER REFERENCES senses(sense_id),
	num INTEGER,
	indent_id TEXT,
	xml_id TEXT,
	sense_type TEXT NOT NULL DEFAULT 'sense',
	role TEXT,
	content_plain TEXT,
	content_markup TEXT,
	is_supplement INTEGER DEFAULT 0,
	transition_type TEXT,
	transition_form TEXT,
	transition_pos TEXT,
	depth INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE citations (
	citation_id INTEGER PRIMARY KEY AUTOINCREMENT,
	sense_id INTEGER NOT NULL REFERENCES senses(sense_id),
	text_plain TEXT,
	text_markup TEXT,
	author TEXT,
	resolved_author TEXT,
	reference TEXT,
	is_hidden INTEGER DEFAULT 0
);

CREATE TABLE locutions (
	sense_id INTEGER PRIMARY KEY REFERENCES senses(sense_id),
	canonical_form TEXT NOT NULL
);

CREATE TABLE rubriques (
	rubrique_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL REFERENCES entries(entry_id),
	rubrique_type TEXT NOT NULL,
	content_plain TEXT,
	content_markup TEXT
);

CREATE TABLE review_queue (
	review_id INTEGER PRIMARY KEY AUTOINCREMENT,
	entry_id TEXT NOT NULL,
	headword TEXT NOT NULL,
	phase TEXT NOT NULL,
	flag_type TEXT NOT NULL,
	reason TEXT,
	context TEXT,
	resolution TEXT,
	resolved_by TEXT
);

CREATE INDEX idx_senses_entry ON senses(entry_id);
CREATE INDEX idx_senses_parent ON senses(parent_sense_id);
CREATE INDEX idx_senses_role ON senses(role);
CREATE INDEX idx_senses_indent_id ON senses(indent_id);
CREATE INDEX idx_senses_xml_id ON senses(xml_id);
CREATE INDEX idx_citations_sense ON citations(sense_id);
CREATE INDEX idx_citations_author ON citations(resolved_author);
CREATE INDEX idx_locutions_form ON locutions(canonical_form);
CREATE INDEX idx_rubriques_entry ON rubriques(entry_id);
CREATE INDEX idx_review_phase ON review_queue(phase);
CREATE INDEX idx_review_type ON review_queue(flag_type);
CREATE INDEX idx_review_unresolved ON review_queue(resolution) WHERE resolution IS NULL OR resolution = '';
"""

const fts_sql = """
CREATE VIRTUAL TABLE senses_fts USING fts5(
	content_plain,
	content='senses',
	content_rowid='sense_id'
);

INSERT INTO senses_fts(rowid, content_plain)
	SELECT sense_id, content_plain FROM senses WHERE content_plain IS NOT NULL;

CREATE VIRTUAL TABLE citations_fts USING fts5(
	text_plain,
	content='citations',
	content_rowid='citation_id'
);

INSERT INTO citations_fts(rowid, text_plain)
	SELECT citation_id, text_plain FROM citations WHERE text_plain IS NOT NULL;
"""

# ── Sense type mapping ───────────────────────────────────────────

sense_type_for(::Figurative) = "figurative"
sense_type_for(::Locution) = "locution"
sense_type_for(::Proverb) = "proverb"
sense_type_for(::CrossReference) = "cross_reference"
sense_type_for(::DomainLabel) = "domain"
sense_type_for(::RegisterLabel) = "register"
function sense_type_for(::Union{NatureLabel, VoiceTransition}, indent::Indent)
	isempty(indent.children) ? "annotation" : "transition_group"
end
sense_type_for(::IndentRole) = "sense"
sense_type_for(::Nothing) = "sense"

function indent_sense_type(indent::Indent)::String
	role = role_of(indent)
	if role isa NatureLabel || role isa VoiceTransition
		sense_type_for(role, indent)
	else
		sense_type_for(role)
	end
end

function role_name(indent::Indent)::Union{Nothing, String}
	role = role_of(indent)
	role === nothing ? nothing : string(typeof(role))
end

# ── Helpers ──────────────────────────────────────────────────────

maybe(s::String) = isempty(s) ? nothing : s

function lastrowid(db::SQLite.DB)::Int
	SQLite.last_insert_rowid(db)
end

# ── Insertion functions ──────────────────────────────────────────

function insert_citations!(db::SQLite.DB, sense_id::Int, citations::Vector{Citation})
	for cit in citations
		resolved = isempty(cit.resolved_author) ? cit.author : cit.resolved_author
		SQLite.execute(db,
			"INSERT INTO citations (sense_id, text_plain, text_markup, author, resolved_author, reference, is_hidden) VALUES (?, ?, ?, ?, ?, ?, ?)",
			(sense_id, strip_tags(cit.text), cit.text, cit.author, resolved, cit.reference, isempty(cit.hide) ? 0 : 1))
	end
end

function insert_indent!(db::SQLite.DB, entry_id::String, parent_sense_id::Int,
		indent::Indent, depth::Int, indent_id::String, xml_id::String)
	plain = strip_tags(indent.content)
	stype = indent_sense_type(indent)
	SQLite.execute(db,
		"INSERT INTO senses (entry_id, parent_sense_id, indent_id, xml_id, sense_type, role, content_plain, content_markup, depth) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
		(entry_id, parent_sense_id, maybe(indent_id), maybe(xml_id),
		 stype, role_name(indent), plain, indent.content, depth))
	sense_id = lastrowid(db)

	insert_citations!(db, sense_id, indent.citations)

	if role_of(indent) isa Locution && !isempty(indent.canonical_form)
		SQLite.execute(db,
			"INSERT INTO locutions (sense_id, canonical_form) VALUES (?, ?)",
			(sense_id, indent.canonical_form))
	end

	for (i, child) in enumerate(indent.children)
		child_indent_id = isempty(indent_id) ? "" : "$(indent_id).$(i)"
		child_xml_id = isempty(xml_id) ? "" : "$(xml_id).$(i)"
		insert_indent!(db, entry_id, sense_id, child, depth + 1, child_indent_id, child_xml_id)
	end
end

function insert_body_element!(db::SQLite.DB, entry_id::String,
		parent_sense_id::Union{Nothing, Int}, sense::Sense, depth::Int, xml_id::String)
	vnum = sense.num !== nothing ? sense.num : 1
	indent_id_base = "$(entry_id).$(vnum)"
	plain = isempty(sense.content) ? nothing : strip_tags(sense.content)
	markup = isempty(sense.content) ? nothing : sense.content
	SQLite.execute(db,
		"INSERT INTO senses (entry_id, parent_sense_id, num, indent_id, xml_id, sense_type, content_plain, content_markup, is_supplement, depth) VALUES (?, ?, ?, ?, ?, 'sense', ?, ?, ?, ?)",
		(entry_id, parent_sense_id, sense.num, maybe(indent_id_base), maybe(xml_id),
		 plain, markup, sense.is_supplement ? 1 : 0, depth))
	sense_id = lastrowid(db)

	insert_citations!(db, sense_id, sense.citations)

	for (i, indent) in enumerate(sense.indents)
		child_indent_id = "$(indent_id_base).$(i)"
		child_xml_id = isempty(xml_id) ? "" : "$(xml_id).$(i)"
		insert_indent!(db, entry_id, sense_id, indent, depth + 1, child_indent_id, child_xml_id)
	end
end

function insert_body_element!(db::SQLite.DB, entry_id::String,
		parent_sense_id::Union{Nothing, Int}, group::TransitionGroup, depth::Int, xml_id::String)
	plain = strip_tags(group.transition_content)
	stype = group.kind == :strong ? "grammatical_variant" : "usage_group"
	transition_type = string(group.kind)
	SQLite.execute(db,
		"INSERT INTO senses (entry_id, parent_sense_id, xml_id, sense_type, content_plain, content_markup, depth, transition_type, transition_form, transition_pos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
		(entry_id, parent_sense_id, maybe(xml_id),
		 stype, plain, group.transition_content, depth,
		 transition_type, maybe(group.form), maybe(group.pos)))
	container_id = lastrowid(db)

	for (i, sub) in enumerate(group.sub_senses)
		child_xml_id = isempty(xml_id) ? "" : "$(xml_id).$(i)"
		insert_body_element!(db, entry_id, container_id, sub, depth + 1, child_xml_id)
	end
end

function insert_rubriques!(db::SQLite.DB, entry_id::String, rubriques::Vector{Rubrique})
	for rub in rubriques
		parts = String[]
		!isempty(rub.content) && push!(parts, rub.content)
		for indent in rub.indents
			push!(parts, indent.content)
		end
		full_markup = join(parts, " ")
		full_plain = strip_tags(full_markup)
		rubrique_type = string(typeof(rub.kind))
		SQLite.execute(db,
			"INSERT INTO rubriques (entry_id, rubrique_type, content_plain, content_markup) VALUES (?, ?, ?, ?)",
			(entry_id, rubrique_type, full_plain, full_markup))
	end
end

function insert_flags!(db::SQLite.DB, flags::Vector{ReviewFlag})
	for flag in flags
		context_json = JSON3.write(flag.context)
		SQLite.execute(db,
			"INSERT INTO review_queue (entry_id, headword, phase, flag_type, reason, context, resolution, resolved_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
			(flag.entry_id, flag.headword, flag.phase, flag.flag_type,
			 flag.reason, context_json, maybe(flag.resolution), maybe(flag.resolved_by)))
	end
end

# ── Entry point ──────────────────────────────────────────────────

function emit_sqlite(entries::Vector{Entry}, output_path::String;
		flags::Vector{ReviewFlag} = ReviewFlag[])
	isfile(output_path) && rm(output_path)
	db = SQLite.DB(output_path)

	SQLite.execute(db, "PRAGMA synchronous=NORMAL")

	for stmt in split(schema_sql, ';')
		stripped = strip(stmt)
		isempty(stripped) && continue
		SQLite.execute(db, stripped)
	end

	SQLite.execute(db, "BEGIN TRANSACTION")

	for entry in entries
		entry_id = entry.id[]
		SQLite.execute(db,
			"INSERT INTO entries (entry_id, headword, homograph_index, pronunciation, pos, is_supplement, source_letter) VALUES (?, ?, ?, ?, ?, ?, ?)",
			(entry_id, entry.headword, entry.homograph_index,
			 maybe(entry.pronunciation), maybe(entry.pos),
			 entry.is_supplement ? 1 : 0, maybe(entry.source_letter)))

		for (i, el) in enumerate(entry.body)
			xml_id = "$(entry_id)_s$(i)"
			insert_body_element!(db, entry_id, nothing, el, 0, xml_id)
		end

		insert_rubriques!(db, entry_id, entry.rubriques)
	end

	insert_flags!(db, flags)

	SQLite.execute(db, "COMMIT")

	for stmt in split(fts_sql, ';')
		stripped = strip(stmt)
		isempty(stripped) && continue
		SQLite.execute(db, stripped)
	end

	row_counts = Dict{String, Int}()
	for table in ("entries", "senses", "citations", "locutions", "rubriques", "review_queue")
		result = DBInterface.execute(db, "SELECT COUNT(*) FROM $table") |> first
		row_counts[table] = first(result)
	end
	SQLite.close(db)

	@info "Wrote $output_path"
	for (table, count) in sort(collect(row_counts))
		@info "  $(rpad(table, 15)) $(count)"
	end
end
