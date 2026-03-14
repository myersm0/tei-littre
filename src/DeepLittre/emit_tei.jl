# ── Markup conversion ────────────────────────────────────────────
# Converts Gannaz inline markup to TEI equivalents.

const markup_substitutions = [
	r"<semantique type=\"domaine\">(.*?)</semantique>"s => s"<usg type=\"domain\">\1</usg>",
	r"<semantique type=\"indicateur\">(.*?)</semantique>"s => s"<usg type=\"sem\">\1</usg>",
	r"<semantique>(.*?)</semantique>"s => s"<usg type=\"sem\">\1</usg>",
	r"<a ref=\"([^\"]*)\">(.*?)</a>"s => s"<xr><ref target=\"#\1\">\2</ref></xr>",
	r"<exemple>(.*?)</exemple>"s => s"<mentioned>\1</mentioned>",
	r"<nature>(.*?)</nature>"s => s"<usg type=\"gram\">\1</usg>",
	r"<i lang=\"la\">(.*?)</i>"s => s"<foreign xml:lang=\"la\">\1</foreign>",
	r"<i>(.*?)</i>"s => s"<mentioned>\1</mentioned>",
]

function markup_to_tei(markup::String)::String
	result = markup
	for (pattern, replacement) in markup_substitutions
		result = replace(result, pattern => replacement)
	end
	lowercase_usg_content(result)
end

function lowercase_usg_content(s::AbstractString)::String
	buf = IOBuffer()
	last_end = 1
	for m in eachmatch(r"(<usg\b[^>]*>)(.*?)(</usg>)"s, s)
		print(buf, s[last_end:prevind(s, m.offset)])
		print(buf, m.captures[1], lowercase(m.captures[2]), m.captures[3])
		last_end = m.offset + ncodeunits(m.match)
	end
	print(buf, s[last_end:end])
	String(take!(buf))
end

function lowercase_text_nodes(s::AbstractString)::String
	join(
		startswith(part, '<') ? part : lowercase(part)
		for part in split_preserving(s, r"<[^>]+>")
	)
end

function split_preserving(s::AbstractString, pattern::Regex)::Vector{String}
	parts = String[]
	last_end = 1
	for m in eachmatch(pattern, s)
		if m.offset > last_end
			push!(parts, s[last_end:prevind(s, m.offset)])
		end
		push!(parts, m.match)
		last_end = m.offset + ncodeunits(m.match)
	end
	if last_end <= ncodeunits(s)
		push!(parts, s[last_end:end])
	end
	parts
end

function strip_usg_tags(s::AbstractString)::String
	replace(s, r"<usg\b[^>]*>(.*?)</usg>"s => s"\1")
end

# ── Label splitting ──────────────────────────────────────────────

function split_label(tei_content::AbstractString)::Tuple{String, String}
	m = match(r"^<gramGrp><gram\b[^>]*>(.*?)</gram></gramGrp>\s*"s, tei_content)
	if m !== nothing
		label = lowercase(strip_usg_tags(strip(m.captures[1])))
		remaining = replace(tei_content[m.offset + ncodeunits(m.match):end], r"^[,;:\s]+" => "")
		return (label, strip(remaining))
	end
	m = match(r"^<usg\b[^>]*>(.*?)</usg>\s*"s, tei_content)
	if m !== nothing
		label = lowercase_text_nodes(strip_usg_tags(strip(m.captures[1])))
		remaining = replace(tei_content[m.offset + ncodeunits(m.match):end], r"^[,;:\s]+" => "")
		return (label, strip(remaining))
	end
	m = match(r"^Fig\.\s*", tei_content)
	if m !== nothing
		remaining = replace(tei_content[m.offset + ncodeunits(m.match):end], r"^[,;:\s]+" => "")
		return ("fig.", strip(remaining))
	end
	(lowercase_text_nodes(strip_usg_tags(tei_content)), "")
end

function split_def_usg(tei_content::AbstractString)::Tuple{Vector{String}, String}
	usg_elements = String[]
	remaining = tei_content
	while true
		m = match(r"^(<usg\b[^>]*>.*?</usg>)[,;:\s]*"s, remaining)
		m === nothing && break
		push!(usg_elements, lowercase_text_nodes(m.captures[1]))
		remaining = strip(remaining[m.offset + ncodeunits(m.match):end])
	end
	(usg_elements, remaining)
end

# ── XML helpers ──────────────────────────────────────────────────

function id_attr(sense_id::String)::String
	isempty(sense_id) ? "" : " xml:id=\"$(escape_xml(sense_id))\""
end

pad(level::Int) = "  " ^ level

# ── Citation emission ────────────────────────────────────────────

function emit_citation(io::IO, cit::Citation, level::Int)
	p = pad(level)
	author = isempty(cit.resolved_author) ? cit.author : cit.resolved_author
	text = markup_to_tei(cit.text)
	hidden = isempty(cit.hide) ? "" : " ana=\"hidden\""

	println(io, "$(p)<cit type=\"example\"$(hidden)>")
	println(io, "$(p)  <quote>$(text)</quote>")
	if !isempty(author) || !isempty(cit.reference)
		println(io, "$(p)  <bibl>")
		!isempty(author) && println(io, "$(p)    <author>$(escape_xml(author))</author>")
		!isempty(cit.reference) && println(io, "$(p)    <biblScope>$(escape_xml(cit.reference))</biblScope>")
		println(io, "$(p)  </bibl>")
	end
	println(io, "$(p)</cit>")
end

function emit_citations(io::IO, citations::Vector{Citation}, level::Int)
	for cit in citations
		emit_citation(io, cit, level)
	end
end

# ── Indent emission (dispatched on IndentRole) ───────────────────

function emit_indent(io::IO, indent::Indent, level::Int, sense_id::String = "")
	role = role_of(indent)
	if role === nothing
		emit_indent(io, indent, Elaboration(), level, sense_id)
	else
		emit_indent(io, indent, role, level, sense_id)
	end
end

function emit_children(io::IO, children::Vector{Indent}, level::Int, parent_id::String)
	for (i, child) in enumerate(children)
		child_id = isempty(parent_id) ? "" : "$(parent_id).$(i)"
		emit_indent(io, child, level, child_id)
	end
end

function emit_label_sense(io::IO, label::String, usg_type::String, def_text::String,
		citations::Vector{Citation}, children::Vector{Indent},
		level::Int; sense_id::String = "", extra_attrs::String = "")
	p = pad(level)
	label = strip_usg_tags(label)
	println(io, "$(p)<sense$(id_attr(sense_id))$(extra_attrs)>")
	println(io, "$(p)  <usg type=\"$(usg_type)\">$(label)</usg>")
	if !isempty(def_text)
		usg_els, clean_def = split_def_usg(def_text)
		for el in usg_els
			println(io, "$(p)  $(el)")
		end
		!isempty(clean_def) && println(io, "$(p)  <def>$(clean_def)</def>")
	end
	emit_citations(io, citations, level + 1)
	emit_children(io, children, level + 1, sense_id)
	println(io, "$(p)</sense>")
end

function emit_default_sense(io::IO, indent::Indent, level::Int, sense_id::String)
	p = pad(level)
	content = markup_to_tei(indent.content)
	usg_els, clean_def = split_def_usg(content)
	println(io, "$(p)<sense$(id_attr(sense_id))>")
	for el in usg_els
		println(io, "$(p)  $(el)")
	end
	!isempty(clean_def) && println(io, "$(p)  <def>$(clean_def)</def>")
	emit_citations(io, indent.citations, level + 1)
	emit_children(io, indent.children, level + 1, sense_id)
	println(io, "$(p)</sense>")
end

# ── Role-specific dispatch methods ───────────────────────────────

function emit_indent(io::IO, indent::Indent, ::Figurative, level::Int, sense_id::String)
	content = markup_to_tei(indent.content)
	label, def_text = split_label(content)
	emit_label_sense(io, label, "sem", def_text,
		indent.citations, indent.children, level;
		sense_id, extra_attrs = " type=\"figuré\"")
end

function emit_indent(io::IO, indent::Indent, ::DomainLabel, level::Int, sense_id::String)
	content = markup_to_tei(indent.content)
	label, def_text = split_label(content)
	if !isempty(label) && !isempty(def_text)
		emit_label_sense(io, label, "domain", def_text,
			indent.citations, indent.children, level; sense_id)
	else
		emit_default_sense(io, indent, level, sense_id)
	end
end

function emit_indent(io::IO, indent::Indent, ::RegisterLabel, level::Int, sense_id::String)
	content = markup_to_tei(indent.content)
	label, def_text = split_label(content)
	emit_label_sense(io, label, "register", def_text,
		indent.citations, indent.children, level; sense_id)
end

function emit_indent(io::IO, indent::Indent, ::Locution, level::Int, sense_id::String)
	p = pad(level)
	content = markup_to_tei(indent.content)
	println(io, "$(p)<re type=\"locution\"$(id_attr(sense_id))>")
	if !isempty(indent.canonical_form)
		println(io, "$(p)  <form><orth>$(escape_xml(indent.canonical_form))</orth></form>")
	end
	println(io, "$(p)  <def>$(content)</def>")
	emit_citations(io, indent.citations, level + 1)
	println(io, "$(p)</re>")
end

function emit_indent(io::IO, indent::Indent, ::Proverb, level::Int, sense_id::String)
	p = pad(level)
	content = markup_to_tei(indent.content)
	println(io, "$(p)<re type=\"proverbe\"$(id_attr(sense_id))>")
	println(io, "$(p)  <def>$(content)</def>")
	emit_citations(io, indent.citations, level + 1)
	println(io, "$(p)</re>")
end

function emit_indent(io::IO, indent::Indent, ::CrossReference, level::Int, sense_id::String)
	p = pad(level)
	content = markup_to_tei(indent.content)
	println(io, "$(p)<note type=\"xref\"$(id_attr(sense_id))>$(content)</note>")
end

function emit_indent(io::IO, indent::Indent, role::Union{NatureLabel, VoiceTransition}, level::Int, sense_id::String)
	content = markup_to_tei(indent.content)
	label, def_text = split_label(content)
	if !isempty(indent.children) || !isempty(def_text) || !isempty(indent.citations)
		emit_label_sense(io, label, "gram", def_text,
			indent.citations, indent.children, level; sense_id)
	else
		println(io, "$(pad(level))<usg type=\"gram\">$(label)</usg>")
	end
end

function emit_indent(io::IO, indent::Indent, ::Union{Elaboration, Continuation, Constructional}, level::Int, sense_id::String)
	emit_default_sense(io, indent, level, sense_id)
end

# ── Body element emission ────────────────────────────────────────

function emit_body_element(io::IO, sense::Sense, level::Int, sense_id::String)
	p = pad(level)
	attrs = id_attr(sense_id)
	sense.num !== nothing && (attrs *= " n=\"$(sense.num)\"")
	sense.is_supplement && (attrs *= " source=\"supplement\"")

	println(io, "$(p)<sense$(attrs)>")

	if !isempty(sense.content)
		content = markup_to_tei(sense.content)
		usg_els, clean_def = split_def_usg(content)
		for el in usg_els
			println(io, "$(p)  $(el)")
		end
		!isempty(clean_def) && println(io, "$(p)  <def>$(clean_def)</def>")
	end

	emit_citations(io, sense.citations, level + 1)

	for (i, indent) in enumerate(sense.indents)
		child_id = isempty(sense_id) ? "" : "$(sense_id).$(i)"
		emit_indent(io, indent, level + 1, child_id)
	end

	for rub in sense.rubriques
		emit_rubrique(io, rub, level + 1)
	end

	println(io, "$(p)</sense>")
end

function emit_body_element(io::IO, group::TransitionGroup, level::Int, sense_id::String)
	p = pad(level)
	if group.kind == :strong
		println(io, "$(p)<entry type=\"grammaticalVariant\">")
		println(io, "$(p)  <form><orth>$(escape_xml(group.form))</orth></form>")
		println(io, "$(p)  <gramGrp><gram type=\"pos\">$(escape_xml(group.pos))</gram></gramGrp>")
	else
		label = lowercase_text_nodes(markup_to_tei(group.transition_content))
		println(io, "$(p)<sense$(id_attr(sense_id))>")
		println(io, "$(p)  <usg type=\"gram\">$(label)</usg>")
	end

	for (i, sub) in enumerate(group.sub_senses)
		sub_id = isempty(sense_id) ? "" : "$(sense_id).$(i)"
		emit_body_element(io, sub, level + 1, sub_id)
	end

	if group.kind == :strong
		println(io, "$(p)</entry>")
	else
		println(io, "$(p)</sense>")
	end
end

# ── Rubrique emission (dispatched on RubriqueKind) ───────────────

function emit_rubrique_body(io::IO, rub::Rubrique, level::Int)
	p = pad(level)
	!isempty(rub.content) && println(io, "$(p)  <p>$(markup_to_tei(rub.content))</p>")
	emit_citations(io, rub.citations, level + 1)
	for indent in rub.indents
		println(io, "$(p)  <p>$(markup_to_tei(indent.content))</p>")
		emit_citations(io, indent.citations, level + 1)
	end
end

const rubrique_wrappers = Dict{Type, Tuple{String, String}}(
	Historique => ("<note type=\"historique\">", "</note>"),
	Remarque => ("<note type=\"remarque\">", "</note>"),
	Supplement => ("<note type=\"supplément\">", "</note>"),
	Etymologie => ("<etym>", "</etym>"),
	Synonyme => ("<re type=\"synonyme\">", "</re>"),
	Proverbes => ("<re type=\"proverbes\">", "</re>"),
)

function emit_rubrique(io::IO, rub::Rubrique, level::Int)
	wrapper = get(rubrique_wrappers, typeof(rub.kind), nothing)
	wrapper === nothing && return
	p = pad(level)
	println(io, "$(p)$(wrapper[1])")
	emit_rubrique_body(io, rub, level)
	println(io, "$(p)$(wrapper[2])")
end

# ── Entry emission ───────────────────────────────────────────────

function emit_entry(io::IO, entry::Entry, level::Int)
	p = pad(level)
	xml_id = escape_xml(entry.id[])
	attrs = "xml:id=\"$(xml_id)\""
	entry.is_supplement && (attrs *= " source=\"supplement\"")

	println(io, "$(p)<entry $(attrs)>")

	println(io, "$(p)  <form type=\"lemma\">")
	println(io, "$(p)    <orth>$(escape_xml(entry.headword))</orth>")
	!isempty(entry.pronunciation) && println(io, "$(p)    <pron>$(escape_xml(entry.pronunciation))</pron>")
	println(io, "$(p)  </form>")

	!isempty(entry.pos) && println(io, "$(p)  <gramGrp><gram type=\"pos\">$(escape_xml(entry.pos))</gram></gramGrp>")

	for (i, el) in enumerate(entry.body)
		sense_id = "$(xml_id)_s$(i)"
		emit_body_element(io, el, level + 1, sense_id)
	end

	for rub in entry.rubriques
		emit_rubrique(io, rub, level + 1)
	end

	println(io, "$(p)</entry>")
end

# ── Top-level ────────────────────────────────────────────────────

const tei_header = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:id="littre">
<teiHeader>
<fileDesc>
<titleStmt>
<title>Dictionnaire de la langue française — Émile Littré</title>
<title type="sub">TEI Lex-0 edition</title>
<author>Émile Littré</author>
<editor role="digital">François Gannaz</editor>
<editor role="enrichment">deep-littre pipeline</editor>
</titleStmt>
<publicationStmt>
<publisher>deep-littre project</publisher>
<availability status="restricted">
<licence target="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</licence>
</availability>
</publicationStmt>
<sourceDesc>
<bibl>Littré, Émile. <title>Dictionnaire de la langue française</title>. Paris: Hachette, 1872–1877.</bibl>
<bibl>Digital source: François Gannaz, XMLittré v1.3
<ref target="https://bitbucket.org/Mytskine/xmlittre-data">bitbucket.org/Mytskine/xmlittre-data</ref>
</bibl>
</sourceDesc>
</fileDesc>
</teiHeader>
<text>
<body>
"""

const tei_footer = """</body>
</text>
</TEI>
"""

function emit_tei(entries::Vector{Entry}, output_path::String)
	open(output_path, "w") do io
		print(io, tei_header)
		for entry in entries
			emit_entry(io, entry, 1)
		end
		print(io, tei_footer)
	end
	@info "Wrote $(length(entries)) entries to $output_path"
end
