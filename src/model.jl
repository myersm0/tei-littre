# ── Indent roles (trait hierarchy, dispatched on in emitters) ─────

abstract type IndentRole end

struct Figurative <: IndentRole end
struct DomainLabel <: IndentRole end
struct NatureLabel <: IndentRole end
struct CrossReference <: IndentRole end
struct RegisterLabel <: IndentRole end
struct Proverb <: IndentRole end
struct VoiceTransition <: IndentRole end
struct Locution <: IndentRole end
struct Unclassified <: IndentRole end


# ── Rubrique kinds (trait hierarchy, dispatched on in emitters) ───

abstract type RubriqueKind end

struct Historique <: RubriqueKind end
struct Etymologie <: RubriqueKind end
struct Remarque <: RubriqueKind end
struct Synonyme <: RubriqueKind end
struct Proverbes <: RubriqueKind end
struct Supplement <: RubriqueKind end


# ── Classification metadata ──────────────────────────────────────

@enum ClassificationMethod begin
	Deterministic
	Heuristic
	LlmAssisted
	Manual
end

@kwdef struct Classification
	role::IndentRole
	method::ClassificationMethod
end


# ── Citation ─────────────────────────────────────────────────────

@kwdef mutable struct Citation
	text::String
	author::String = ""
	reference::String = ""
	hide::String = ""
	resolved_author::String = ""
end


# ── Source traceability ───────────────────────────────────────────

@kwdef struct SourceLocation
	file::String
	line::Int
end


# ── Indent ───────────────────────────────────────────────────────

@kwdef mutable struct Indent
	content::String
	citations::Vector{Citation} = Citation[]
	children::Vector{Indent} = Indent[]
	classification::Union{Nothing, Classification} = nothing
	canonical_form::String = ""
	source::Union{Nothing, SourceLocation} = nothing
end


# ── Rubrique ─────────────────────────────────────────────────────

@kwdef struct Rubrique
	kind::RubriqueKind
	content::String
	citations::Vector{Citation} = Citation[]
	indents::Vector{Indent} = Indent[]
end


# ── Sense and TransitionGroup ────────────────────────────────────

abstract type BodyElement end

@kwdef struct Sense <: BodyElement
	content::String = ""
	num::Union{Nothing, Int} = nothing
	is_resume::Bool = false
	is_supplement::Bool = false
	citations::Vector{Citation} = Citation[]
	indents::Vector{Indent} = Indent[]
	rubriques::Vector{Rubrique} = Rubrique[]
	source::Union{Nothing, SourceLocation} = nothing
end

Sense(source::Sense; is_supplement::Bool) = Sense(
	content = source.content,
	num = source.num,
	is_resume = source.is_resume,
	is_supplement = is_supplement,
	citations = source.citations,
	indents = source.indents,
	rubriques = source.rubriques,
	source = source.source,
)

@kwdef struct TransitionGroup <: BodyElement
	kind::Symbol
	form::String = ""
	pos::String = ""
	transition_content::String = ""
	sub_senses::Vector{BodyElement} = BodyElement[]
end


# ── Entry ────────────────────────────────────────────────────────

@kwdef struct Entry
	headword::String
	id::Ref{String}
	homograph_index::Union{Nothing, Int} = nothing
	is_supplement::Bool = false
	pronunciation::String = ""
	pos::String = ""
	body::Vector{BodyElement} = BodyElement[]
	rubriques::Vector{Rubrique} = Rubrique[]
	resume_text::String = ""
	source_letter::String = ""
end


# ── Review ───────────────────────────────────────────────────────

@kwdef struct ReviewFlag
	entry_id::String
	headword::String
	phase::String
	flag_type::String
	reason::String
	context::Dict{String, Any} = Dict{String, Any}()
	resolution::String = ""
	resolved_by::String = ""
end
