#!/usr/bin/env julia
using ArgParse
using DeepLittre

function parse_args_pipeline()
	settings = ArgParseSettings(
		prog = "run_pipeline",
		description = "Deep-Littré pipeline: parse → enrich → scope → emit",
	)

	project_root = joinpath(@__DIR__, "..")
	default_patches = joinpath(project_root, "patches", "patches.toml")

	@add_arg_table! settings begin
		"source_dir"
			help = "directory containing Gannaz XML source files (a.xml–z.xml)"
			required = true
		"output_dir"
			help = "directory for output files (littre.tei.xml, littre.db)"
			required = true
		"--patches"
			help = "path to patches.toml (default: patches/patches.toml if it exists)"
			arg_type = String
			default = isfile(default_patches) ? default_patches : nothing
		"--verdicts"
			help = "path to verdicts CSV (LLM classification overrides)"
			arg_type = String
			default = nothing
	end

	parse_args(settings)
end

function main()
	args = parse_args_pipeline()

	source_dir = args["source_dir"]
	output_dir = args["output_dir"]
	mkpath(output_dir)

	patches_path = args["patches"]
	patches_path !== nothing && @info "Using patches: $patches_path"

	@info "Phase 1: Parse"
	entries = parse_all(source_dir; patches_path)

	@info "Phases 2–4: Enrich"
	enrich!(entries; verdicts_path = args["verdicts"])

	@info "Phase 5: Scope transitions"
	scope_all!(entries)

	@info "Collect review flags"
	flags = collect_flags(entries)

	tei_path = joinpath(output_dir, "littre.tei.xml")
	@info "Emit TEI → $tei_path"
	emit_tei(entries, tei_path)

	sqlite_path = joinpath(output_dir, "littre.db")
	@info "Emit SQLite → $sqlite_path"
	emit_sqlite(entries, sqlite_path; flags)

	@info "Done."
end

main()
