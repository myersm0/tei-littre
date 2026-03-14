# ── Shared utilities ─────────────────────────────────────────────

function strip_tags(markup::String)::String
	strip(replace(markup, r"<[^>]+>" => ""))
end

function escape_xml(text::String)::String
	text = replace(text, '&' => "&amp;")
	text = replace(text, '<' => "&lt;")
	text = replace(text, '>' => "&gt;")
	text
end

# ── Normalization ────────────────────────────────────────────────

function normalize_source(text::String)::String
	text = replace(text, "<xmlittre" => "<xmlittre xml:space=\"preserve\""; count = 1)
	text = replace(text, "nom=\"PROVERBE\"" => "nom=\"PROVERBES\"")
	text = replace(text, "nom=\"REMARQUES\"" => "nom=\"REMARQUE\"")
	text = replace(text, r"<span\s+lang=\"la\">(.*?)</span>"s => s"<i lang=\"la\">\1</i>")
	text
end

# ── Patches (line-targeted string replacements) ─────────────────

struct Patch
	file::String
	line::Int
	old::String
	new::String
end

function load_patches(patches_path::String)::Vector{Patch}
	isfile(patches_path) || return Patch[]
	data = TOML.parsefile(patches_path)
	[Patch(p["file"], p["line"], p["old"], p["new"]) for p in get(data, "patches", [])]
end

function apply_patches(text::String, patches::Vector{Patch})::String
	isempty(patches) && return text
	lines = split(text, '\n')
	for patch in patches
		line = lines[patch.line]
		if !occursin(patch.old, line)
			error("Patch failed at line $(patch.line): expected '$(patch.old)' not found")
		end
		lines[patch.line] = replace(line, patch.old => patch.new; count = 1)
	end
	join(lines, '\n')
end

# ── Source line tracking ─────────────────────────────────────────
# XML.jl doesn't expose line numbers, so we pre-scan the raw text
# for <indent opening tags and record their line numbers. Since both
# the text scan and the DOM parse visit indents in document order,
# we consume the queue in sync during parsing.

function scan_indent_lines(text::String)::Vector{Int}
	line_numbers = Int[]
	for (line_number, line) in enumerate(eachsplit(text, '\n'))
		for _ in eachmatch(r"<indent[\s>]", line)
			push!(line_numbers, line_number)
		end
	end
	line_numbers
end

# ── ID generation ────────────────────────────────────────────────

function make_id(headword::String, homograph_index::Union{Nothing, Int} = nothing)::String
	nfkd = Unicode.normalize(lowercase(headword), :NFKD)
	ascii_only = filter(isascii, nfkd)
	cleaned = replace(ascii_only, r"[^a-z0-9]" => "_")
	cleaned = replace(cleaned, r"_+" => "_")
	cleaned = strip(cleaned, '_')
	if isempty(cleaned) || !isletter(first(cleaned))
		cleaned = "e_" * cleaned
	end
	if homograph_index !== nothing
		cleaned = "$(cleaned).$(homograph_index)"
	end
	cleaned
end

# ── XML helpers ──────────────────────────────────────────────────

const structural_tags = Set(["cit", "indent", "rubrique", "variante"])

function attr(node::XML.Node, key::String, default::String = "")::String
	attrs = XML.attributes(node)
	attrs === nothing ? default : get(attrs, key, default)
end

function text_content(node::XML.Node)::String
	buf = IOBuffer()
	for child in XML.children(node)
		XML.nodetype(child) == XML.Text || break
		print(buf, XML.value(child))
	end
	String(take!(buf))
end

function find_child(node::XML.Node, name::String)::Union{Nothing, XML.Node}
	for child in XML.children(node)
		XML.nodetype(child) == XML.Element && XML.tag(child) == name && return child
	end
	nothing
end

function iter_descendants(node::XML.Node, name::String)::Vector{XML.Node}
	results = XML.Node[]
	_collect_descendants!(results, node, name)
	results
end

function _collect_descendants!(results, node, name)
	for child in XML.children(node)
		if XML.nodetype(child) == XML.Element
			XML.tag(child) == name && push!(results, child)
			_collect_descendants!(results, child, name)
		end
	end
end

function element_children(node::XML.Node)
	[c for c in XML.children(node) if XML.nodetype(c) == XML.Element]
end

# ── Rubrique kind lookup ────────────────────────────────────────

const rubrique_lookup = Dict{String, RubriqueKind}(
	"HISTORIQUE" => Historique(),
	"ÉTYMOLOGIE" => Etymologie(),
	"REMARQUE" => Remarque(),
	"REMARQUES" => Remarque(),
	"SYNONYME" => Synonyme(),
	"PROVERBES" => Proverbes(),
	"PROVERBE" => Proverbes(),
	"SUPPLÉMENT AU DICTIONNAIRE" => Supplement(),
)

const valid_letters = Set{String}(
	vcat([string(c) for c in 'a':'z'], ["a_prep"])
)

# ── Content extraction ───────────────────────────────────────────
# Walks an element's children, separating structural children
# (cit, indent, rubrique, variante) from inline markup content.

struct ParseContext
	source_file::String
	indent_lines::Vector{Int}
	indent_index::Ref{Int}
end

function next_indent_line!(ctx::ParseContext)::Int
	i = ctx.indent_index[]
	ctx.indent_index[] = i + 1
	i <= length(ctx.indent_lines) ? ctx.indent_lines[i] : 0
end

function extract_content(node::XML.Node, ctx::ParseContext)
	content_parts = String[]
	citations = Citation[]
	indents = Indent[]
	rubriques = Rubrique[]
	senses = Sense[]

	for child in XML.children(node)
		nt = XML.nodetype(child)
		if nt == XML.Text
			push!(content_parts, escape_xml(XML.value(child)))
		elseif nt == XML.Element
			name = XML.tag(child)
			if name == "cit"
				push!(citations, parse_citation(child))
			elseif name == "indent"
				push!(indents, parse_indent(child, ctx))
			elseif name == "rubrique"
				rubrique, _ = parse_rubrique(child, ctx)
				push!(rubriques, rubrique)
			elseif name == "variante"
				push!(senses, parse_sense(child, ctx))
			else
				push!(content_parts, XML.write(child))
			end
		end
	end

	content = join(split(join(content_parts)), " ")
	(content, citations, indents, rubriques, senses)
end

# ── Core parsers ─────────────────────────────────────────────────

function parse_citation(node::XML.Node)::Citation
	text_parts = String[]
	for child in XML.children(node)
		nt = XML.nodetype(child)
		if nt == XML.Text
			push!(text_parts, escape_xml(XML.value(child)))
		elseif nt == XML.Element
			push!(text_parts, XML.write(child))
		end
	end

	Citation(
		text = strip(join(text_parts)),
		author = attr(node, "aut"),
		reference = attr(node, "ref"),
		hide = attr(node, "hide"),
	)
end

function parse_indent(node::XML.Node, ctx::ParseContext)::Indent
	line = next_indent_line!(ctx)
	content, citations, children, _, _ = extract_content(node, ctx)
	Indent(
		content = content,
		citations = citations,
		children = children,
		source = SourceLocation(file = ctx.source_file, line = line),
	)
end

function parse_sense(node::XML.Node, ctx::ParseContext)::Sense
	num_str = attr(node, "num")
	num = isempty(num_str) ? nothing : tryparse(Int, num_str)
	is_resume = attr(node, "option") == "résumé"

	content, citations, indents, rubriques, _ = extract_content(node, ctx)

	Sense(
		content = content,
		num = num,
		is_resume = is_resume,
		citations = citations,
		indents = indents,
		rubriques = rubriques,
	)
end

function parse_rubrique(node::XML.Node, ctx::ParseContext)::Tuple{Rubrique, Vector{Sense}}
	nom = attr(node, "nom")
	kind = get(rubrique_lookup, nom) do
		@warn "Unknown rubrique type" nom
		Remarque()
	end

	content, citations, indents, _, senses = extract_content(node, ctx)

	rubrique = Rubrique(
		kind = kind,
		content = content,
		citations = citations,
		indents = indents,
	)
	(rubrique, [Sense(s; is_supplement = true) for s in senses])
end

function parse_entry(node::XML.Node, letter::String, ctx::ParseContext)::Entry
	headword = attr(node, "terme")
	sens_str = attr(node, "sens")
	homograph_index = isempty(sens_str) ? nothing : parse(Int, sens_str)
	is_supplement = attr(node, "supplement") == "1"

	pronunciation = ""
	pos = ""
	entete = find_child(node, "entete")
	if entete !== nothing
		pron_el = find_child(entete, "prononciation")
		if pron_el !== nothing
			pronunciation = strip(text_content(pron_el))
		end
		nature_el = find_child(entete, "nature")
		if nature_el !== nothing
			pos = strip(text_content(nature_el))
		end
	end

	body_senses = Sense[]
	supplement_senses = Sense[]
	rubriques = Rubrique[]

	corps = find_child(node, "corps")
	if corps !== nothing
		for child in element_children(corps)
			name = XML.tag(child)
			if name == "variante"
				push!(body_senses, parse_sense(child, ctx))
			elseif name == "rubrique"
				rubrique, sups = parse_rubrique(child, ctx)
				push!(rubriques, rubrique)
				append!(supplement_senses, sups)
			end
		end
	end

	resume_text = ""
	resume_el = find_child(node, "résumé")
	if resume_el !== nothing
		resume_text = XML.write(resume_el)
	end

	for child in element_children(node)
		if XML.tag(child) == "rubrique"
			rubrique, sups = parse_rubrique(child, ctx)
			push!(rubriques, rubrique)
			append!(supplement_senses, sups)
		end
	end

	all_body = BodyElement[s for s in vcat(body_senses, supplement_senses)]

	Entry(
		headword = headword,
		id = Ref(make_id(headword, homograph_index)),
		homograph_index = homograph_index,
		is_supplement = is_supplement,
		pronunciation = pronunciation,
		pos = pos,
		body = all_body,
		rubriques = rubriques,
		resume_text = resume_text,
		source_letter = letter,
	)
end

# ── File-level parsing ───────────────────────────────────────────

function parse_file(path::String, patches::Vector{Patch} = Patch[])::Vector{Entry}
	source_file = basename(path)
	letter = first(splitext(source_file))
	file_patches = filter(p -> p.file == source_file, patches)

	text = read(path, String)
	text = apply_patches(text, file_patches)
	text = normalize_source(text)

	indent_lines = scan_indent_lines(text)
	ctx = ParseContext(source_file, indent_lines, Ref(1))

	doc = XML.parse(XML.Node, text)
	root_node = doc[end]
	entries = [parse_entry(el, letter, ctx) for el in iter_descendants(root_node, "entree")]
	deduplicate_ids!(entries)
end

function parse_all(source_dir::String; patches_path::Union{Nothing, String} = nothing)::Vector{Entry}
	patches = patches_path !== nothing ? load_patches(patches_path) : Patch[]

	xml_files = sort([
		joinpath(source_dir, f)
		for f in readdir(source_dir)
		if endswith(f, ".xml") && first(splitext(f)) in valid_letters
	])

	isempty(xml_files) && error("No XML files found in $source_dir")

	all_entries = Entry[]
	for path in xml_files
		entries = parse_file(path, patches)
		@info "$(basename(path)): $(length(entries)) entries"
		append!(all_entries, entries)
	end

	deduplicate_ids!(all_entries; verbose = true)
end

function deduplicate_ids!(entries::Vector{Entry}; verbose::Bool = false)
	counts = Dict{String, Int}()
	for entry in entries
		counts[entry.id[]] = get(counts, entry.id[], 0) + 1
	end

	seen = Dict{String, Int}()
	for entry in entries
		if counts[entry.id[]] > 1
			n = seen[entry.id[]] = get(seen, entry.id[], 0) + 1
			entry.id[] = "$(entry.id[])_$(n)"
		end
	end

	verbose && @info "Total: $(length(entries)) entries"
	entries
end
