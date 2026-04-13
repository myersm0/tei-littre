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

function classify_and_scope_fixture(path)
	entry = parse_fixture(path)
	classify_all!([entry])
	scope_all!([entry])
	return entry
end

@testset "scope regression fixtures" begin
	@testset "devancier wrapped au plur stays local" begin
		entry = classify_and_scope_fixture("test/fixtures/real/devancier.xml")

		@test length(entry.body) == 1
		@test entry.body[1] isa Sense

		s1 = entry.body[1]::Sense
		@test length(s1.indents) == 1

		i1 = s1.indents[1]
		@test !isnothing(i1.classification)
		@test i1.classification.role isa NatureLabel
		@test isempty(i1.children)
	end

	@testset "droite body shape remains stable" begin
		entry = classify_and_scope_fixture("test/fixtures/real/droit_2.xml")

		@test length(entry.body) == 4
		@test all(x -> x isa Sense, entry.body)

		s1 = entry.body[1]::Sense
		s2 = entry.body[2]::Sense
		s3 = entry.body[3]::Sense
		s4 = entry.body[4]::Sense

		@test length(s1.indents) == 5
		@test length(s2.indents) == 4
		@test length(s3.indents) == 0
		@test length(s4.indents) == 1

		i1 = s4.indents[1]
		@test !isnothing(i1.classification)
		@test i1.classification.role isa VoiceTransition
	end

	@testset "droite sense 3 remains plain cited sense" begin
		entry = classify_and_scope_fixture("test/fixtures/real/droit_3.xml")

		s3 = entry.body[3]::Sense

		@test s3.num == 3
		@test length(s3.indents) == 22
		@test length(s3.citations) == 10
		@test occursin("Faculté reconnue, naturelle ou légale", s3.content)

		@test !isnothing(s3.indents[1].classification)
		@test !(s3.indents[1].classification.role isa VoiceTransition)
	end

	@testset "f remains a simple non-transition control" begin
		entry = classify_and_scope_fixture("test/fixtures/real/f.xml")

		@test length(entry.body) == 3
		@test all(x -> x isa Sense, entry.body)

		s1 = entry.body[1]::Sense
		s2 = entry.body[2]::Sense
		s3 = entry.body[3]::Sense

		@test length(s1.indents) == 2
		@test length(s2.indents) == 1
		@test length(s3.indents) == 0

		@test !isnothing(s1.indents[1].classification)
		@test !isnothing(s1.indents[2].classification)
		@test !(s1.indents[1].classification.role isa VoiceTransition)
		@test !(s1.indents[2].classification.role isa VoiceTransition)

		@test !isnothing(s2.indents[1].classification)
		@test !(s2.indents[1].classification.role isa VoiceTransition)
	end
end
