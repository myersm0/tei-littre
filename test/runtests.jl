# This test file exercises the full pipeline on a one letter (e.xml).
# It verifies end-to-end behavior (parse → enrich → scope → emit),
# but does not exhaustively test edge cases.
#
# Detailed structural and scoping edge cases are tested separately
# in the synthetic and regression fixture tests.

using Test
using DeepLittre

const data_dir = joinpath(@__DIR__, "fixtures")
const fixture_xml = joinpath(data_dir, "real", "e.xml")

function parse_fixture()
	parse_file(fixture_xml)
end

function enriched_fixture()
	entries = parse_fixture()
	enrich!(entries)
	entries
end

function scoped_fixture()
	entries = enriched_fixture()
	scope_all!(entries)
	entries
end

@testset "DeepLittre" begin

@testset "ID generation" begin
	@test DeepLittre.make_id("ENVIE") == "envie"
	@test DeepLittre.make_id("DÉGOÛTÉ, ÉE") == "degoute_ee"
	@test DeepLittre.make_id("À") == "a"
	@test DeepLittre.make_id("-ESQUE") == "esque"
	@test DeepLittre.make_id("1ER") == "e_1er"
	@test DeepLittre.make_id("DI-", 1) == "di.1"
	@test DeepLittre.make_id("DI-", 2) == "di.2"
end

@testset "ID deduplication" begin
	entries = parse_fixture()
	ids = [e.id[] for e in entries]
	@test length(ids) == length(unique(ids))
end

@testset "Normalization" begin
	text = """<xmlittre><rubrique nom="PROVERBE">x</rubrique><rubrique nom="REMARQUES">y</rubrique></xmlittre>"""
	normalized = DeepLittre.normalize_source(text)
	@test occursin("nom=\"PROVERBES\"", normalized)
	@test occursin("nom=\"REMARQUE\"", normalized)
	@test !occursin("nom=\"PROVERBE\"", normalized)
	@test !occursin("nom=\"REMARQUES\"", normalized)
end

@testset "Patch application" begin
	text = "line1\nline2 old text here\nline3"
	patches = [DeepLittre.Patch("test.xml", 2, "old text", "new text")]
	result = DeepLittre.apply_patches(text, patches)
	@test occursin("new text", result)
	@test !occursin("old text", result)
	@test count('\n', result) == count('\n', text)
end

@testset "Patch failure" begin
	text = "line1\nline2\nline3"
	patches = [DeepLittre.Patch("test.xml", 2, "nonexistent", "replacement")]
	@test_throws ErrorException DeepLittre.apply_patches(text, patches)
end

@testset "Parse" begin
	entries = parse_fixture()
	@test length(entries) == 2

	envie = first(e for e in entries if e.headword == "ENVIE")
	@test envie.pronunciation == "an-vie"
	@test envie.pos == "s. f."
	@test length(envie.body) == 2
	@test length(envie.rubriques) == 2

	sense1 = envie.body[1]::Sense
	@test sense1.num == 1
	@test length(sense1.citations) == 1
	@test sense1.citations[1].author == "BOILEAU"
	@test length(sense1.indents) == 2

	sense2 = envie.body[2]::Sense
	@test sense2.num == 2
	@test length(sense2.indents) == 2
end

@testset "Source locations" begin
	entries = parse_fixture()
	envie = first(e for e in entries if e.headword == "ENVIE")
	sense1 = envie.body[1]::Sense
	for indent in sense1.indents
		@test indent.source !== nothing
		@test indent.source.file == "e.xml"
		@test indent.source.line > 0
	end
end

@testset "Rubrique parsing" begin
	entries = parse_fixture()
	envie = first(e for e in entries if e.headword == "ENVIE")
	@test length(envie.rubriques) == 2
	@test envie.rubriques[1].kind isa Historique
	@test envie.rubriques[2].kind isa Etymologie
end

@testset "Author resolution" begin
	entries = enriched_fixture()
	envie = first(e for e in entries if e.headword == "ENVIE")
	sense2 = envie.body[2]::Sense

	sev_cit = sense2.citations[1]
	@test sev_cit.author == "SÉVIGNÉ"
	@test sev_cit.resolved_author == "SÉVIGNÉ"

	id_cit = sense2.indents[1].citations[1]
	@test id_cit.author == "ID."
	@test id_cit.resolved_author == "SÉVIGNÉ"
end

@testset "Classification" begin
	entries = enriched_fixture()
	envie = first(e for e in entries if e.headword == "ENVIE")
	sense1 = envie.body[1]::Sense

	@test DeepLittre.role_of(sense1.indents[1]) isa Figurative
	@test sense1.indents[1].classification.method == Deterministic
	@test sense1.indents[1].classification.confidence == 1.0

	@test DeepLittre.role_of(sense1.indents[2]) isa DomainLabel
	@test sense1.indents[2].classification.method == Deterministic

	sense2 = envie.body[2]::Sense
	@test DeepLittre.role_of(sense2.indents[1]) isa Locution
	@test DeepLittre.role_of(sense2.indents[2]) isa RegisterLabel
end

@testset "Locution extraction" begin
	entries = enriched_fixture()
	envie = first(e for e in entries if e.headword == "ENVIE")
	sense2 = envie.body[2]::Sense
	locution_indent = sense2.indents[1]
	@test DeepLittre.role_of(locution_indent) isa Locution
	@test locution_indent.canonical_form == "Avoir envie"
end

@testset "Scope transitions" begin
	entries = scoped_fixture()
	envier = first(e for e in entries if e.headword == "ENVIER")

	@test length(envier.body) == 3

	@test envier.body[1] isa Sense
	@test (envier.body[1]::Sense).num == 1

	@test envier.body[2] isa Sense
	@test (envier.body[2]::Sense).num == 2
	sense2 = envier.body[2]::Sense
	@test isempty(sense2.indents)

	@test envier.body[3] isa TransitionGroup
	group = envier.body[3]::TransitionGroup
	@test group.kind == :medium
	@test length(group.sub_senses) == 2
	@test (group.sub_senses[1]::Sense).num == 3
	@test (group.sub_senses[2]::Sense).num == 4
end

@testset "Review flags" begin
	entries = scoped_fixture()
	flags = collect_flags(entries)
	@test flags isa Vector{ReviewFlag}
	types = Set(f.flag_type for f in flags)
	@test "calibration_sample" in types
end

@testset "TEI emission" begin
	entries = scoped_fixture()
	buf = IOBuffer()
	DeepLittre.emit_entry(buf, first(e for e in entries if e.headword == "ENVIE"), 0)
	tei = String(take!(buf))

	@test occursin("<entry xml:id=\"envie\">", tei)
	@test occursin("<orth>ENVIE</orth>", tei)
	@test occursin("<pron>an-vie</pron>", tei)
	@test occursin("<gram type=\"pos\">s. f.</gram>", tei)
	@test occursin("type=\"figuré\"", tei)
	@test occursin("<usg type=\"domain\">", tei)
	@test occursin("<re type=\"locution\"", tei)
	@test occursin("<orth>Avoir envie</orth>", tei)
	@test occursin("<note type=\"historique\">", tei)
	@test occursin("<etym>", tei)
	@test occursin("<author>BOILEAU</author>", tei)
end

@testset "TEI transition group" begin
	entries = scoped_fixture()
	buf = IOBuffer()
	envier = first(e for e in entries if e.headword == "ENVIER")
	DeepLittre.emit_entry(buf, envier, 0)
	tei = String(take!(buf))

	@test occursin("<usg type=\"gram\">", tei)
	@test count("<sense", tei) >= 4
end

@testset "SQLite emission" begin
	entries = scoped_fixture()
	flags = collect_flags(entries)
	output = tempname() * ".db"
	try
		emit_sqlite(entries, output; flags)
		db = DeepLittre.SQLite.DB(output)

		row = first(DeepLittre.DBInterface.execute(db, "SELECT COUNT(*) as n FROM entries"))
		@test row.n == 2

		row = first(DeepLittre.DBInterface.execute(db, "SELECT COUNT(*) as n FROM senses"))
		@test row.n > 0

		row = first(DeepLittre.DBInterface.execute(db, "SELECT COUNT(*) as n FROM citations"))
		@test row.n > 0

		row = first(DeepLittre.DBInterface.execute(db, "SELECT COUNT(*) as n FROM locutions"))
		@test row.n >= 1

		row = first(DeepLittre.DBInterface.execute(db, "SELECT COUNT(*) as n FROM rubriques"))
		@test row.n == 2

		envie = first(DeepLittre.DBInterface.execute(db, "SELECT * FROM entries WHERE entry_id = 'envie'"))
		@test envie.headword == "ENVIE"
		@test envie.pos == "s. f."

		loc = first(DeepLittre.DBInterface.execute(db, "SELECT canonical_form FROM locutions"))
		@test loc.canonical_form == "Avoir envie"

		DeepLittre.SQLite.close(db)
	finally
		rm(output; force = true)
	end
end

end
