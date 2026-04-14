using Test
include("DeepLittre.jl")
using .DeepLittre

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
		return entries[1]
	finally
		rm(tmp; force = true)
	end
end

function classify_fixture(path)
	entry = parse_fixture(path)
	classify_all!([entry])
	return entry
end

@testset "transition classification" begin
	@testset "bare substantivement is a voice transition" begin
		entry = classify_fixture("test/fixtures/synthetic/terminal_substantivement.xml")
		s1 = entry.body[1]::Sense
		i2 = s1.indents[2]

		@test !isnothing(i2.classification)
		@test i2.classification.role isa VoiceTransition
	end

	@testset "wrapped substantivement is currently a nature label" begin
		entry = classify_fixture("test/fixtures/synthetic/wrapped_substantivement.xml")
		s1 = entry.body[1]::Sense
		i1 = s1.indents[1]

		@test !isnothing(i1.classification)
		@test i1.classification.role isa NatureLabel
	end

	@testset "wrapped au plur is currently a nature label" begin
		entry = classify_fixture("test/fixtures/synthetic/terminal_au_pluriel.xml")
		s1 = entry.body[1]::Sense
		i2 = s1.indents[2]

		@test !isnothing(i2.classification)
		@test i2.classification.role isa NatureLabel
	end

	@testset "adjacent wrapped labels both classify as nature labels" begin
		entry = classify_fixture("test/fixtures/synthetic/adjacent_transitions.xml")
		s1 = entry.body[1]::Sense
		s2 = entry.body[2]::Sense

		@test !isnothing(s1.indents[1].classification)
		@test s1.indents[1].classification.role isa VoiceTransition

		@test !isnothing(s2.indents[1].classification)
		@test s2.indents[1].classification.role isa VoiceTransition
	end
end
