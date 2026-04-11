# ── Resolve authors ──────────────────────────────────────────────
# Walks citations in document order within each entry, propagating
# the last named author forward through "ID." references.

function collect_citations!(out::Vector{Citation}, indent::Indent)
	append!(out, indent.citations)
	for child in indent.children
		collect_citations!(out, child)
	end
end

function collect_citations!(out::Vector{Citation}, rub::Rubrique)
	append!(out, rub.citations)
	for indent in rub.indents
		collect_citations!(out, indent)
	end
end

function citations_in_order(entry::Entry)::Vector{Citation}
	out = Citation[]
	for el in entry.body
		if el isa Sense
			append!(out, el.citations)
			for indent in el.indents
				collect_citations!(out, indent)
			end
			for rub in el.rubriques
				collect_citations!(out, rub)
			end
		end
	end
	for rub in entry.rubriques
		collect_citations!(out, rub)
	end
	out
end

function resolve_authors!(entry::Entry)::Int
	all_citations = citations_in_order(entry)
	last_author = ""
	resolved = 0

	for cit in all_citations
		if cit.author == "ID." && !isempty(last_author)
			cit.resolved_author = last_author
			resolved += 1
		elseif !isempty(cit.author) && cit.author != "ID."
			last_author = cit.author
			cit.resolved_author = cit.author
		else
			cit.resolved_author = cit.author
		end
	end
	resolved
end

function resolve_all_authors!(entries::Vector{Entry})
	total = 0
	unresolved = 0
	for entry in entries
		total += resolve_authors!(entry)
		for cit in citations_in_order(entry)
			if cit.author == "ID." && isempty(cit.resolved_author)
				unresolved += 1
			end
		end
	end
	@info "Resolved $total ID. citations"
	unresolved > 0 && @warn "$unresolved ID. citations had no antecedent"
end

# ── Classify indents ─────────────────────────────────────────────

# ── Verdicts (external classification overrides) ─────────────────
# CSV with columns: file, line, check, heuristic_role, llm_role, llm_confidence
# Keyed on (file, line). When present, overrides heuristic classification.

struct Verdict
	role::IndentRole
	confidence::Float64
	check::String
end

const verdict_key = Tuple{String, Int}
const VerdictDict = Dict{verdict_key, Verdict}

const role_names = Dict{String, IndentRole}(
	"Figurative" => Figurative(),
	"DomainLabel" => DomainLabel(),
	"NatureLabel" => NatureLabel(),
	"CrossReference" => CrossReference(),
	"RegisterLabel" => RegisterLabel(),
	"Proverb" => Proverb(),
	"VoiceTransition" => VoiceTransition(),
	"Locution" => Locution(),
	"Constructional" => Constructional(),
	"Elaboration" => Elaboration(),
	"Continuation" => Continuation(),
)

function load_verdicts(path::String)::VerdictDict
	verdicts = VerdictDict()
	isfile(path) || return verdicts
	lines = readlines(path)
	isempty(lines) && return verdicts
	header = split(first(lines), ',')
	col = Dict(strip(h) => i for (i, h) in enumerate(header))
	for line in lines[2:end]
		isempty(strip(line)) && continue
		fields = split(line, ',')
		file = strip(fields[col["file"]])
		line_num = parse(Int, strip(fields[col["line"]]))
		check_col = get(col, "check", nothing)
		check = check_col !== nothing ? strip(get(fields, check_col, "")) : ""
		role_str = strip(fields[col["llm_role"]])
		confidence = parse(Float64, strip(fields[col["llm_confidence"]]))
		role = get(role_names, role_str, nothing)
		if role === nothing
			@warn "Unknown role in verdicts" role_str file line_num
			continue
		end
		verdicts[(file, line_num)] = Verdict(role, confidence, check)
	end
	@info "Loaded $(length(verdicts)) verdicts from $path"
	verdicts
end

function apply_verdict!(indent::Indent, verdicts::VerdictDict)::Bool
	indent.source === nothing && return false
	key = (indent.source.file, indent.source.line)
	verdict = get(verdicts, key, nothing)
	verdict === nothing && return false
	if !isempty(verdict.check)
		plain = strip_tags(indent.content)
		if !startswith(plain, verdict.check)
			@warn "Verdict check mismatch" key verdict.check actual=first(plain, 30)
			return false
		end
	end
	classify!(indent, verdict.role, LlmAssisted, verdict.confidence)
	true
end

function classify!(indent::Indent, role::IndentRole, method::ClassificationMethod, confidence::Float64)
	indent.classification = Classification(role = role, method = method, confidence = confidence)
end

function role_of(indent::Indent)::Union{Nothing, IndentRole}
	indent.classification === nothing ? nothing : indent.classification.role
end

# ── Tier A: deterministic (tag-based) ────────────────────────────

function classify_deterministic!(indent::Indent)::Bool
	c = indent.content

	if occursin("<semantique type=\"indicateur\">Fig.", c)
		classify!(indent, Figurative(), Deterministic, 1.0)
		return true
	end

	if occursin("<semantique type=\"domaine\">", c)
		classify!(indent, DomainLabel(), Deterministic, 1.0)
		return true
	end

	if occursin("<nature>", c)
		classify!(indent, NatureLabel(), Deterministic, 1.0)
		return true
	end

	if occursin("<exemple>", c)
		classify!(indent, Locution(), Deterministic, 1.0)
		return true
	end

	if occursin("<a ref=", c)
		plain = strip_tags(c)
		if length(plain) < 120
			if occursin(r"^(voy\.|V\.|Voy\.|voyez)"i, plain)
				classify!(indent, CrossReference(), Deterministic, 1.0)
				return true
			end
			if occursin(r",\s*voy\.\s*$", plain)
				classify!(indent, CrossReference(), Deterministic, 0.95)
				return true
			end
		end
	end

	false
end

# ── Tier B: heuristic (text patterns) ────────────────────────────

const register_pattern = r"^(Populaire|Familière|Familièrement|Familier|Vulgaire|Vulgairement|Triviale|Trivialemen|Bas|Ironiquement|Plaisamment|Burlesque|Poétiquement|Par euphémisme|Par exagération|Par ironie|Par dérision|Par extension|Par analogie|Par métaphore|Par plaisanterie|Par antiphrase|Néologisme|Vieux|Vieilli|Inusité|Peu usité|Très peu usité|Hors d'usage|Tombé en désuétude|Rare|Il est familier|Il est vieux|Il est populaire|Il est inusité|Il est hors d'usage|Il n'est plus usité|Il a vieilli|Il vieillit|Ce mot est|Ce mot a vieilli|Ce sens a vieilli|Cet emploi vieillit|Cet emploi a vieilli|Mot vieilli|Mot populaire|Mot bas|Mot inusité|Terme vieux|Terme vieilli|Terme familier|Terme populaire|Terme inusité|Terme bas)"i

const proverb_pattern = r"^(Prov\.|Proverbe|Proverbialement)"i

const voice_transition_pattern = r"^(V\.\s*(n|a|réfl)|Se\s+conjugue|Absolument|Substantivement|Adverbialement|Adjectivement|Intransitivement|Neutralement|Impersonnellement|Activement|Au\s+pluriel|Au\s+féminin|Au\s+singulier|Au\s+masc|Au\s+fém|Avec\s+un\s+nom\s+de)"

const definition_like_pattern = r"^(Se dit|Il se dit|On dit|On appelle|Se disait|Qui se dit|Il s'est dit|Celui qui|Celle qui|Ce qui|Chose qui|Action de|État de|Qualité de|Nom (donné|que l'on donne)|Terme (de|d')|En termes? (de|d'))"i

const cross_ref_heuristic = r"^(Il est|C'est|On dit|Se dit).{0,40}<a ref="

function classify_heuristic!(indent::Indent)::Bool
	c = indent.content
	plain = strip_tags(c)

	if occursin(proverb_pattern, plain)
		classify!(indent, Proverb(), Heuristic, 0.9)
		return true
	end

	if occursin(register_pattern, plain)
		classify!(indent, RegisterLabel(), Heuristic, 0.85)
		return true
	end

	if occursin(voice_transition_pattern, plain)
		classify!(indent, VoiceTransition(), Heuristic, 0.85)
		return true
	end

	if occursin("<a ref=", c) && occursin(cross_ref_heuristic, c)
		classify!(indent, CrossReference(), Heuristic, 0.8)
		return true
	end

	if occursin(definition_like_pattern, plain)
		classify!(indent, Elaboration(), Heuristic, 0.75)
		return true
	end

	if startswith(plain, "Fig.")
		classify!(indent, Figurative(), Heuristic, 0.9)
		return true
	end

	if !isempty(indent.citations)
		classify!(indent, Continuation(), Heuristic, 0.5)
		return true
	end

	if !isempty(plain)
		classify!(indent, Elaboration(), Heuristic, 0.4)
		return true
	end

	false
end

# ── Combined classifier ──────────────────────────────────────────

function classify_indent!(indent::Indent, verdicts::VerdictDict = VerdictDict())
	apply_verdict!(indent, verdicts) ||
		classify_deterministic!(indent) ||
		classify_heuristic!(indent)
	for child in indent.children
		classify_indent!(child, verdicts)
	end
end

function each_indent(f::Function, entry::Entry)
	for el in entry.body
		if el isa Sense
			for indent in el.indents
				_walk_indents(indent, f)
			end
		end
	end
end

function _walk_indents(indent::Indent, f::Function)
	f(indent)
	for child in indent.children
		_walk_indents(child, f)
	end
end

function classify_all!(entries::Vector{Entry}, verdicts::VerdictDict = VerdictDict())
	counts = Dict{String, Int}()
	for entry in entries
		for el in entry.body
			if el isa Sense
				for indent in el.indents
					classify_indent!(indent, verdicts)
				end
			end
		end
		each_indent(entry) do indent
			role = role_of(indent)
			name = role === nothing ? "unknown" : string(typeof(role))
			counts[name] = get(counts, name, 0) + 1
		end
	end

	total = sum(values(counts))
	unknown = get(counts, "unknown", 0)
	@info "Classified $(total - unknown)/$total ($(round((total - unknown) / total * 100; digits=1))%)"
	for (role, count) in sort(collect(counts); by = last, rev = true)
		@info "  $role: $count"
	end
	counts
end

# ── Extract locutions ────────────────────────────────────────────

const exemple_pattern = r"<exemple>(.*?)</exemple>"
const reflexive_pattern = r"^S'[A-ZÉÈÊÀÂÎÏÔÙÛÜÇ].*,\s*v\.\s*réfl"

function extract_locution!(indent::Indent)
	role_of(indent) isa Locution || return :skip

	plain = strip_tags(indent.content)

	if occursin(reflexive_pattern, plain)
		classify!(indent, VoiceTransition(), Heuristic, 0.9)
		return :reclassified
	end

	m = match(exemple_pattern, indent.content)
	if m !== nothing
		indent.canonical_form = strip(m.captures[1])
		return :extracted
	end

	if !occursin(',', plain)
		return :skip
	end

	form = strip(first(split(plain, ','; limit = 2)))
	if length(form) > 60
		return :skip
	end
	indent.canonical_form = form
	:extracted
end

function extract_all_locutions!(entries::Vector{Entry})
	extracted = 0
	reclassified = 0
	skipped = 0

	for entry in entries
		each_indent(entry) do indent
			result = extract_locution!(indent)
			if result == :reclassified
				reclassified += 1
			elseif result == :extracted
				extracted += 1
			elseif result == :skip && role_of(indent) isa Locution
				skipped += 1
			end
		end
	end

	@info "Extracted canonical forms: $extracted"
	@info "Reclassified to voice_transition: $reclassified"
	@info "Skipped (no clear form): $skipped"
end

# ── Combined enrichment entry point ──────────────────────────────

function enrich!(entries::Vector{Entry}; verdicts_path::Union{Nothing, String} = nothing)
	@info "Phase 2: Resolve authors"
	resolve_all_authors!(entries)

	verdicts = verdicts_path !== nothing ? load_verdicts(verdicts_path) : VerdictDict()

	@info "Phase 3: Classify indents"
	classify_all!(entries, verdicts)

	@info "Phase 4: Extract locutions"
	extract_all_locutions!(entries)
end
