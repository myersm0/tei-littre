using Test
using DeepLittre

const fixture_path = joinpath(@__DIR__, "fixtures", "real", "e.xml")

matches_any(patterns, text) = any(p -> occursin(p, text), patterns)

function enriched_corpus()
	entries = parse_file(fixture_path)
	enrich!(entries)
	entries
end

function walk_indents(f, entry::Entry)
	for el in entry.body
		el isa Sense || continue
		for indent in el.indents
			recurse(indent, f)
		end
	end
end

function recurse(indent::Indent, f)
	f(indent)
	for child in indent.children
		recurse(child, f)
	end
end

const pattern_cases = [
	(
		name = "proverb_patterns",
		patterns = DeepLittre.proverb_patterns,
		must_match = [
			"Prov. Qui dort dîne",
			"Proverbe attribué à",
			"Proverbialement, on dit",
		],
		must_not_match = [
			"Prov sans point",
			"Provençal de naissance",
			"Provoquer la colère",
		],
	),
	(
		name = "voice_transition_patterns",
		patterns = DeepLittre.voice_transition_patterns,
		must_match = [
			"V. n. Aller à pied.",
			"V. a. Battre quelqu'un.",
			"V. réfl. Se laver.",
			"Se conjugue avec avoir.",
			"Absolument, dans ce sens.",
			"Substantivement, ce mot prend",
			"Impersonnellement, il pleut",
		],
		must_not_match = [
			"Au pluriel, ce mot prend un s",
			"Au féminin, on dit",
			"Avec un nom de personne, le verbe",
		],
	),
	(
		name = "voice_transition_label_only_patterns",
		patterns = DeepLittre.voice_transition_label_only_patterns,
		must_match = [
			"Au pluriel.",
			"Au pluriel",
			"Au féminin.",
			"Au singulier",
			"Au masc.",
			"Au fém.",
			"Avec un nom de personne.",
			"Avec un nom de chose.",
		],
		must_not_match = [
			"Au pluriel, ce mot prend un s",
			"Aujourd'hui rare",
			"Avec ardeur",
			"Avec un nom de personne, le verbe se construit",
		],
	),
	(
		name = "register_patterns",
		patterns = DeepLittre.register_patterns,
		must_match = [
			"Populaire, dans ce sens",
			"Populairement, on dit",
			"Familièrement, en parlant",
			"Vulgairement, dans le langage",
			"Ironiquement, en parlant",
			"Par extension, le sens s'élargit",
			"Par analogie de forme",
			"Par antiphrase",
			"Néologisme rare",
			"Très peu usité",
			"Peu usité dans ce sens",
			"Hors d'usage",
			"Tombé en désuétude",
			"Il est familier de dire",
			"Il a vieilli",
			"Il vieillit",
			"Ce mot est de l'argot",
			"Ce mot a vieilli",
			"Cet emploi a vieilli",
			"Mot vieilli",
			"Terme populaire",
		],
		must_not_match = [
			"Vieux marin de la Méditerranée",
			"Familière à tous les marins",
			"Par exemple, on dit",
			"Il est temps de partir",
		],
	),
	(
		name = "register_label_only_patterns",
		patterns = DeepLittre.register_label_only_patterns,
		must_match = [
			"Vieux.",
			"Vieux",
			"Vieillie",
			"Familière",
			"Familier",
			"Bas.",
			"Basse",
			"Vulgaire",
			"Triviale",
			"Inusité",
		],
		must_not_match = [
			"Vieux marin",
			"Familière à tous",
			"Bas de laine",
			"Vulgairement, on dit",
		],
	),
	(
		name = "figurative_patterns",
		patterns = DeepLittre.figurative_patterns,
		must_match = [
			"Fig. Le serpent de l'envie",
			"Fig. en ce sens",
		],
		must_not_match = [
			"Fig.",
			"Figure de style",
			"Figaro",
		],
	),
	(
		name = "cross_ref_leading_patterns",
		patterns = DeepLittre.cross_ref_leading_patterns,
		must_match = [
			"voy. CAPTURE",
			"Voy. ABATTRE",
			"Voyez sous CAPTURE",
		],
		must_not_match = [
			"voyou de quartier",
			"vapeur d'eau",
			"voyage en train",
		],
	),
	(
		name = "cross_ref_trailing_patterns",
		patterns = DeepLittre.cross_ref_trailing_patterns,
		must_match = [
			"machine à coudre, voy.",
			"ce sens, voy. ",
		],
		must_not_match = [
			"voy. au début",
			"machine voy.",
		],
	),
]

const heuristic_role_patterns = [
	(Proverb, [DeepLittre.proverb_patterns]),
	(RegisterLabel, [DeepLittre.register_patterns, DeepLittre.register_label_only_patterns]),
	(VoiceTransition, [DeepLittre.voice_transition_patterns, DeepLittre.voice_transition_label_only_patterns]),
	(Figurative, [DeepLittre.figurative_patterns]),
]

@testset "rule certainty" begin

	@testset "constructed examples" begin
		for case in pattern_cases
			@testset "$(case.name)" begin
				for s in case.must_match
					@test matches_any(case.patterns, s)
				end
				for s in case.must_not_match
					@test !matches_any(case.patterns, s)
				end
			end
		end
	end

	@testset "corpus self-consistency" begin
		entries = enriched_corpus()
		for entry in entries
			walk_indents(entry) do indent
				cls = indent.classification
				cls === nothing && return
				cls.method == Heuristic || return
				cls.role isa Unclassified && return

				role_type = typeof(cls.role)
				idx = findfirst(rp -> rp[1] === role_type, heuristic_role_patterns)
				idx === nothing && return

				plain = DeepLittre.strip_tags(indent.content)
				@test any(matches_any(ps, plain) for ps in heuristic_role_patterns[idx][2])
			end
		end
	end

	@testset "corpus pattern overlap" begin
		entries = enriched_corpus()
		overlaps = String[]

		for entry in entries
			walk_indents(entry) do indent
				cls = indent.classification
				cls === nothing && return
				cls.method == Heuristic || return
				cls.role isa Unclassified && return

				plain = DeepLittre.strip_tags(indent.content)
				role_type = typeof(cls.role)

				for (other_role, pattern_sets) in heuristic_role_patterns
					other_role === role_type && continue
					for patterns in pattern_sets
						matches_any(patterns, plain) || continue
						push!(overlaps, "$(role_type) classified, but $(other_role) pattern matches: $(first(plain, 80))")
					end
				end
			end
		end

		isempty(overlaps) || @show overlaps
		@test isempty(overlaps)
	end

end
