# ── Configuration ────────────────────────────────────────────────

const low_confidence_threshold = 0.5
const low_confidence_roles = Set{Type}([
	Locution, Figurative, DomainLabel, Proverb,
	CrossReference, RegisterLabel, VoiceTransition, NatureLabel,
])
const large_scope_threshold = 15
const calibration_per_bucket = 5
const calibration_seed = 42

# ── Helpers ──────────────────────────────────────────────────────

function all_senses(entry::Entry)
	result = Sense[]
	for el in entry.body
		if el isa Sense
			push!(result, el)
		elseif el isa TransitionGroup
			for sub in el.sub_senses
				sub isa Sense && push!(result, sub)
			end
		end
	end
	result
end

function indent_neighbors(indents::Vector{Indent}, index::Int)::Dict{String, Any}
	result = Dict{String, Any}()
	index > 1 && (result["prev_indent"] = first(strip_tags(indents[index - 1].content), 100))
	index < length(indents) && (result["next_indent"] = first(strip_tags(indents[index + 1].content), 100))
	result
end

# ── Flag collectors ──────────────────────────────────────────────

function flag_low_confidence!(flags::Vector{ReviewFlag}, entries::Vector{Entry})
	for entry in entries
		for sense in all_senses(entry)
			for (i, indent) in enumerate(sense.indents)
				cls = indent.classification
				cls === nothing && continue
				cls.confidence > low_confidence_threshold && continue
				typeof(cls.role) in low_confidence_roles || continue
				neighbors = indent_neighbors(sense.indents, i)
				push!(flags, ReviewFlag(
					entry_id = entry.id[],
					headword = entry.headword,
					phase = "phase3",
					flag_type = "low_confidence",
					reason = "confidence=$(round(cls.confidence; digits=2)), role=$(typeof(cls.role))",
					context = merge(Dict{String, Any}(
						"sense_num" => sense.num,
						"indent_content" => first(indent.content, 200),
						"role" => string(typeof(cls.role)),
						"confidence" => cls.confidence,
						"method" => string(cls.method),
					), neighbors),
				))
			end
		end
	end
end

function flag_skipped_locutions!(flags::Vector{ReviewFlag}, entries::Vector{Entry})
	for entry in entries
		for sense in all_senses(entry)
			for indent in sense.indents
				role_of(indent) isa Locution || continue
				isempty(indent.canonical_form) || continue
				push!(flags, ReviewFlag(
					entry_id = entry.id[],
					headword = entry.headword,
					phase = "phase4",
					flag_type = "skipped_locution",
					reason = "no canonical form extracted",
					context = Dict{String, Any}(
						"sense_num" => sense.num,
						"indent_content" => first(indent.content, 200),
					),
				))
			end
		end
	end
end

function flag_scope_decisions!(flags::Vector{ReviewFlag}, entries::Vector{Entry})
	for entry in entries
		for el in entry.body
			if el isa TransitionGroup
				num_scoped = length(el.sub_senses)
				flag_type = num_scoped > large_scope_threshold ? "large_scope" : "scope_decision"
				first_content = if !isempty(el.sub_senses) && el.sub_senses[1] isa Sense
					first(strip_tags(el.sub_senses[1].content), 80)
				else
					""
				end
				last_content = if !isempty(el.sub_senses) && el.sub_senses[end] isa Sense
					first(strip_tags(el.sub_senses[end].content), 80)
				else
					""
				end
				push!(flags, ReviewFlag(
					entry_id = entry.id[],
					headword = entry.headword,
					phase = "phase5",
					flag_type = flag_type,
					reason = "$(el.kind) scope, $(num_scoped) senses",
					context = Dict{String, Any}(
						"transition_content" => first(strip_tags(el.transition_content), 100),
						"scope_type" => string(el.kind),
						"transition_form" => el.form,
						"transition_pos" => el.pos,
						"num_scoped" => num_scoped,
						"first_scoped" => first_content,
						"last_scoped" => last_content,
					),
				))

				for sub in el.sub_senses
					sub isa Sense && flag_large_intra!(flags, entry, sub)
				end
			end

			el isa Sense && flag_large_intra!(flags, entry, el)
		end
	end
end

function flag_large_intra!(flags::Vector{ReviewFlag}, entry::Entry, sense::Sense)
	for indent in sense.indents
		r = role_of(indent)
		(r isa NatureLabel || r isa VoiceTransition) || continue
		length(indent.children) > 5 || continue
		push!(flags, ReviewFlag(
			entry_id = entry.id[],
			headword = entry.headword,
			phase = "phase5",
			flag_type = "large_intra_scope",
			reason = "$(typeof(r)) scoped $(length(indent.children)) children",
			context = Dict{String, Any}(
				"sense_num" => sense.num,
				"indent_content" => first(strip_tags(indent.content), 100),
				"num_children" => length(indent.children),
			),
		))
	end
end

function flag_calibration_sample!(flags::Vector{ReviewFlag}, entries::Vector{Entry})
	buckets = Dict{Tuple{String, String}, Vector{Tuple{Entry, Sense, Int, Indent}}}()
	for entry in entries
		for sense in all_senses(entry)
			for (i, indent) in enumerate(sense.indents)
				cls = indent.classification
				cls === nothing && continue
				key = (string(typeof(cls.role)), string(cls.method))
				bucket = get!(buckets, key) do
					Tuple{Entry, Sense, Int, Indent}[]
				end
				push!(bucket, (entry, sense, i, indent))
			end
		end
	end

	rng = MersenneTwister(calibration_seed)
	for (role_method, items) in sort(collect(buckets); by = first)
		role, method = role_method
		sample_size = min(calibration_per_bucket, length(items))
		sample = Random.randperm(rng, length(items))[1:sample_size]
		for idx in sample
			entry, sense, i, indent = items[idx]
			cls = indent.classification
			neighbors = indent_neighbors(sense.indents, i)
			push!(flags, ReviewFlag(
				entry_id = entry.id[],
				headword = entry.headword,
				phase = "calibration",
				flag_type = "calibration_sample",
				reason = "sample from $(role)/$(method) (n=$(length(items)))",
				context = merge(Dict{String, Any}(
					"sense_num" => sense.num,
					"indent_content" => first(indent.content, 200),
					"role" => role,
					"confidence" => cls.confidence,
					"method" => method,
					"bucket_size" => length(items),
				), neighbors),
			))
		end
	end
end

const likely_locution_pattern = r"^(Loc\.\s|Locution)"i

function flag_likely_locutions!(flags::Vector{ReviewFlag}, entries::Vector{Entry})
	for entry in entries
		for sense in all_senses(entry)
			for indent in sense.indents
				role_of(indent) isa Locution && continue
				plain = strip_tags(indent.content)
				occursin(likely_locution_pattern, plain) || continue
				push!(flags, ReviewFlag(
					entry_id = entry.id[],
					headword = entry.headword,
					phase = "phase3",
					flag_type = "likely_locution",
					reason = "starts with Loc./Locution but classified as $(typeof(role_of(indent)))",
					context = Dict{String, Any}(
						"sense_num" => sense.num,
						"indent_content" => first(indent.content, 200),
						"current_role" => string(typeof(role_of(indent))),
					),
				))
			end
		end
	end
end

# ── Entry point ──────────────────────────────────────────────────

function collect_flags(entries::Vector{Entry})::Vector{ReviewFlag}
	flags = ReviewFlag[]
	flag_low_confidence!(flags, entries)
	flag_skipped_locutions!(flags, entries)
	flag_likely_locutions!(flags, entries)
	flag_scope_decisions!(flags, entries)
	flag_calibration_sample!(flags, entries)

	by_type = Dict{String, Int}()
	for f in flags
		by_type[f.flag_type] = get(by_type, f.flag_type, 0) + 1
	end
	@info "$(length(flags)) flags total"
	for (ft, count) in sort(collect(by_type); by = last, rev = true)
		@info "  $(rpad(ft, 25)) $(count)"
	end

	flags
end
