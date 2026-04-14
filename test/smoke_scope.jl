using Test
include("DeepLittre.jl")
using .DeepLittre

using .DeepLittre: role_of, !, classify_all!

function parse_fixture(path)
	xml = """
<xmlittre>
$(read(path, String))
</xmlittre>
"""
	tmp = tempname() * ".xml"
	write(tmp, xml)
	try
		entries = parse_file(tmp)
		@test length(entries) == 1
		entries[1]
	finally
		rm(tmp; force = true)
	end
end

@testset "scope synthetic fixtures" begin
	@testset "terminal_substantivement opens medium inter-sense group" begin
		entry = parse_fixture("test/fixtures/synthetic/terminal_substantivement.xml")
		classify_all!([entry])
		log = scope_all!([entry])

		@test length(entry.body) == 3
		@test entry.body[1] isa Sense
		@test entry.body[2] isa TransitionGroup

		group = entry.body[2]
		@test group.kind == :medium
		@test strip_tags(group.transition_content) == "Substantivement."
		@test length(group.sub_senses) == 2
		@test all(x -> x isa Sense, group.sub_senses)
		@test length((entry.body[1]::Sense).indents) == 1
		@test log.medium_scoped == 2
	end

	@testset "terminal_au_pluriel documents current behavior" begin
		entry = parse_fixture("test/fixtures/synthetic/terminal_au_pluriel.xml")
		classify_all!([entry])
		scope_all!([entry])

		@test length(entry.body) == 3
		@test all(x -> x isa Sense, entry.body)

		s1 = entry.body[1]::Sense
		@test length(s1.indents) == 2
		@test role_of(s1.indents[2]) isa NatureLabel
		@test strip_tags(s1.indents[2].content) == "Au plur. En parlant des ancêtres ou des prédécesseurs."
		@test isempty(s1.indents[2].children)
	end

	@testset "nonterminal transition does not open inter-sense scope" begin
		entry = parse_fixture("test/fixtures/synthetic/nonterminal_transition.xml")
		classify_all!([entry])
		scope_all!([entry])

		@test length(entry.body) == 2
		@test all(x -> x isa Sense, entry.body)

		s1 = entry.body[1]::Sense
		@test length(s1.indents) == 1
		@test strip_tags(s1.indents[1].content) == "Substantivement."
		@test length(s1.indents[1].children) == 1
	end

	@testset "transition with citation does not open inter-sense scope" begin
		entry = parse_fixture("test/fixtures/synthetic/transition_with_citation.xml")
		classify_all!([entry])
		scope_all!([entry])

		@test length(entry.body) == 2
		@test all(x -> x isa Sense, entry.body)

		s1 = entry.body[1]::Sense
		@test length(s1.indents) == 1
		@test strip_tags(s1.indents[1].content) == "Substantivement."
		@test length(s1.indents[1].citations) == 1
		@test isempty(s1.indents[1].children)
	end

	@testset "adjacent wrapped labels do not scope" begin
		entry = parse_fixture("test/fixtures/synthetic/adjacent_wrapped_labels.xml")
		classify_all!([entry])
		scope_all!([entry])

		s1 = entry.body[1]::Sense
		s2 = entry.body[2]::Sense

		@test length(entry.body) == 3
		@test entry.body[1] isa Sense
		@test entry.body[2] isa Sense

		@test length(s1.indents) == 1
		@test role_of(s1.indents[1]) isa NatureLabel
		@test isempty(s1.indents[1].children)

		@test length(s2.indents) == 1
		@test role_of(s2.indents[1]) isa NatureLabel
		@test isempty(s2.indents[1].children)
	end

	@testset "sense head pos shift parses as inline content, not indent transition" begin
		entry = parse_fixture("test/fixtures/synthetic/sense_head_pos_shift.xml")

		@test length(entry.body) == 3
		@test all(x -> x isa Sense, entry.body)

		s2 = entry.body[2]::Sense
		s3 = entry.body[3]::Sense

		@test occursin("<nature>S. m.</nature>", s2.content)
		@test occursin("<nature>Loc. adv.</nature>", s3.content)
		@test length(s2.indents) == 2
		@test length(s3.indents) == 1
	end
end
