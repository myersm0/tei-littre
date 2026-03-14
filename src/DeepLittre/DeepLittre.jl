module DeepLittre

using TOML
using Unicode
using XML

include("model.jl")
export IndentRole,
	Figurative, DomainLabel, NatureLabel, CrossReference,
	RegisterLabel, Proverb, VoiceTransition, Locution,
	Constructional, Elaboration, Continuation,
	RubriqueKind,
	Historique, Etymologie, Remarque, Synonyme, Proverbes, Supplement,
	ClassificationMethod, Deterministic, Heuristic, LlmAssisted, Manual,
	Classification, SourceLocation,
	Citation, Indent, Rubrique,
	BodyElement, Sense, TransitionGroup,
	Entry, ReviewFlag

include("parse.jl")
export parse_all, parse_file, strip_tags

include("enrich.jl")
export enrich!, resolve_all_authors!, classify_all!, extract_all_locutions!,
	load_verdicts, VerdictDict

include("scope.jl")
export scope_all!

include("emit_tei.jl")
export emit_tei

end
