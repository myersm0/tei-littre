# Phase 5: Resolve the forward scope of grammatical transitions.
#
# Transitions (VoiceTransition, NatureLabel) are labels with implicit
# forward scope. This pass determines that scope and restructures
# the model accordingly.
#
# Scope outcomes:
#   strong → new form + POS → TransitionGroup wrapping following senses
#   medium → usage partition → TransitionGroup wrapping following senses
#   intra  → indent-level grouping within a sense
#   zero   → annotation only (terminal / solitary, no restructuring)

# ── Transition parsing ───────────────────────────────────────────

const strong_transition_pattern = r"^(S'[A-ZÉÈÊÀÂÎÏÔÙÛÜÇ].+),\s+(v\.\s*.+)"

const form_pos_pattern = r"^([A-ZÉÈÊÀÂÎÏÔÙÛÜÇ][A-ZÉÈÊÀÂÎÏÔÙÛÜÇ '\-]+),\s+(v\.\s*(?:n|a|réfl)|s\.\s*[mf]|adj)\b"

function parse_strong_transition(plain::String)::Union{Nothing, Tuple{String, String}}
	m = match(strong_transition_pattern, plain)
	if m !== nothing
		return (strip(m.captures[1]), strip(m.captures[2]))
	end
	m = match(form_pos_pattern, plain)
	if m !== nothing
		return (strip(m.captures[1]), strip(m.captures[2]))
	end
	nothing
end

# ── Scope logging ────────────────────────────────────────────────

@kwdef mutable struct ScopeLog
	strong_scoped::Int = 0
	medium_scoped::Int = 0
	intra_grouped::Int = 0
	zero_scope::Int = 0
	ambiguous::Vector{String} = String[]
end

# ── Intra-sense scoping ─────────────────────────────────────────
# Groups indents following a transition into its children.

function is_transition(indent::Indent)::Bool
	r = role_of(indent)
	r isa NatureLabel || r isa VoiceTransition
end

function scope_intra_sense!(sense::Sense, log::ScopeLog)
	indents = sense.indents
	length(indents) < 2 && return

	new_indents = Indent[]
	i = 1
	while i <= length(indents)
		indent = indents[i]
		if is_transition(indent) && i < length(indents)
			followers = Indent[]
			j = i + 1
			while j <= length(indents)
				is_transition(indents[j]) && break
				push!(followers, indents[j])
				j += 1
			end
			if !isempty(followers)
				append!(indent.children, followers)
				log.intra_grouped += length(followers)
				push!(new_indents, indent)
				i = j
				continue
			end
		end
		push!(new_indents, indent)
		i += 1
	end

	empty!(sense.indents)
	append!(sense.indents, new_indents)
end

# ── Inter-sense scoping ──────────────────────────────────────────
# Scopes transitions at sense boundaries into TransitionGroups.

function scope_inter_sense!(entry::Entry, log::ScopeLog)
	body = entry.body
	isempty(body) && return

	new_body = BodyElement[]
	i = 1

	while i <= length(body)
		el = body[i]

		if !(el isa Sense) || isempty(el.indents) || !is_voice_transition_indent(last(el.indents))
			push!(new_body, el)
			i += 1
			continue
		end

		transition = last(el.indents)

		if !isempty(transition.citations)
			push!(new_body, el)
			i += 1
			continue
		end

		plain = strip_tags(transition.content)
		remaining = body[i + 1:end]

		if isempty(remaining)
			log.zero_scope += 1
			push!(new_body, el)
			i += 1
			continue
		end

		parsed = parse_strong_transition(plain)

		scope_end = length(remaining)
		for (k, future_el) in enumerate(remaining)
			if future_el isa Sense && !isempty(future_el.indents)
				last_indent = last(future_el.indents)
				if is_voice_transition_indent(last_indent) && isempty(last_indent.citations)
					scope_end = k - 1
					break
				end
			end
		end

		if scope_end == 0
			log.zero_scope += 1
			push!(new_body, el)
			i += 1
			continue
		end

		scoped = remaining[1:scope_end]

		# Remove transition indent from the source sense
		pop!(el.indents)
		push!(new_body, el)

		if parsed !== nothing
			group = TransitionGroup(
				kind = :strong,
				form = parsed[1],
				pos = parsed[2],
				transition_content = transition.content,
				sub_senses = BodyElement[s for s in scoped],
			)
			log.strong_scoped += length(scoped)
		else
			group = TransitionGroup(
				kind = :medium,
				transition_content = transition.content,
				sub_senses = BodyElement[s for s in scoped],
			)
			log.medium_scoped += length(scoped)
		end

		if length(scoped) > 15
			push!(log.ambiguous,
				"$(entry.headword): $(first(plain, 50)) scopes $(length(scoped)) senses")
		end

		push!(new_body, group)
		i += 1 + scope_end
	end

	empty!(entry.body)
	append!(entry.body, new_body)
end

function is_voice_transition_indent(indent::Indent)::Bool
	role_of(indent) isa VoiceTransition
end

# ── Entry point ──────────────────────────────────────────────────

function scope_all!(entries::Vector{Entry})
	log = ScopeLog()

	for entry in entries
		scope_inter_sense!(entry, log)
		for el in entry.body
			if el isa Sense
				scope_intra_sense!(el, log)
			elseif el isa TransitionGroup
				for sub in el.sub_senses
					sub isa Sense && scope_intra_sense!(sub, log)
				end
			end
		end
	end

	@info "Strong-scoped senses (nested entry): $(log.strong_scoped)"
	@info "Medium-scoped senses (usage group): $(log.medium_scoped)"
	@info "Intra-sense grouped indents: $(log.intra_grouped)"
	@info "Zero-scope transitions (annotation): $(log.zero_scope)"
	if !isempty(log.ambiguous)
		@warn "Ambiguous ($(length(log.ambiguous))):"
		for msg in log.ambiguous
			@warn "  $msg"
		end
	end

	log
end
