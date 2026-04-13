# Pipeline behavior

This document specifies the observable behavior of each pipeline phase.

Entry point: `run_pipeline.jl` calls `parse_all` → `enrich!` → `scope_all!` → `collect_flags` → `emit_tei` / `emit_sqlite`.

## Phase 1: Parse

**Input**: A directory of Gannaz XML files (`a.xml`–`z.xml`, `a_prep.xml`), and optionally a patches TOML file.

**Output**: `Vector{Entry}` with all structural information extracted but no enrichment applied. Every `Indent` has a `SourceLocation`; all `classification` fields are `nothing`; all `resolved_author` fields are empty; all `canonical_form` fields are empty.

### 1a. Patches

Patches are loaded from a TOML file as an array of `{file, line, old, new}` records. For each file, applicable patches are filtered by filename and applied in order to the raw text before XML parsing. Each patch does a single `replace(...; count=1)` on the specified line. If the `old` string is not found on that line, the pipeline errors.

**Invariant**: patches never add or remove lines. Source line numbers are stable across patched and unpatched text.

### 1b. Source normalization

Applied to raw text after patches, before XML parsing:

1. Add `xml:space="preserve"` to the root `<xmlittre` tag.
2. Normalize rubrique names: `PROVERBE` → `PROVERBES`, `REMARQUES` → `REMARQUE`.
3. Convert `<span lang="la">...</span>` to `<i lang="la">...</i>`.

### 1c. Indent line tracking

XML.jl does not expose source line numbers. The pipeline pre-scans the raw text for `<indent` opening tags and records their line numbers in document order. During DOM traversal, each `parse_indent` call consumes the next line number from this queue. The scan and the DOM parse both visit indents in document order, so the two stay in sync.

### 1d. Content extraction

`extract_content` walks an element's children and separates them into:

- **Inline content**: text nodes and non-structural element children, serialized back to markup via `XML.write`. Joined and whitespace-collapsed into a single string.
- **Structural children**: `<cit>` → `Citation`, `<indent>` → `Indent` (recursive), `<rubrique>` → `Rubrique`, `<variante>` → `Sense`.

The structural tag set is `{cit, indent, rubrique, variante}`. Everything else (e.g. `<semantique>`, `<nature>`, `<exemple>`, `<a>`, `<i>`) is treated as inline markup and preserved in the content string.

### 1e. Citation parsing

Each `<cit>` element produces a `Citation` with:

- `text`: full inner content (text + inline markup), stripped of leading/trailing whitespace.
- `author`: from the `aut` attribute (empty string if absent).
- `reference`: from the `ref` attribute.
- `hide`: from the `hide` attribute.

### 1f. Entry parsing

For each `<entree>` element:

- `headword` from the `terme` attribute.
- `homograph_index` from the `sens` attribute (parsed as `Int`, or `nothing` if absent).
- `is_supplement` is true when `supplement="1"`.
- `pronunciation` and `pos` extracted from `<entete>/<prononciation>` and `<entete>/<nature>` respectively, using only the leading text content (not nested elements).
- Body senses: all `<variante>` children of `<corps>`, in document order.
- Rubriques inside `<corps>`: each `<rubrique>` yields a `Rubrique` plus zero or more supplement `Sense`s (from `<variante>` children of the rubrique).
- Rubriques at entry level (direct children of `<entree>`): same treatment as corps rubriques.
- `resume_text`: raw XML serialization of the `<résumé>` element, if present.
- Supplement senses (from rubriques) are appended to the body after regular senses, with `is_supplement=true`.

### 1g. Sense parsing

Each `<variante>` element produces a `Sense` with:

- `num` from the `num` attribute (parsed as `Int`, or `nothing`).
- `is_resume` is true when `option="résumé"`.
- Content, citations, indents, and rubriques via `extract_content`.

### 1h. Rubrique parsing

Each `<rubrique>` element produces a `Rubrique` with:

- `kind` looked up from the `nom` attribute. Known values: `HISTORIQUE`, `ÉTYMOLOGIE`, `REMARQUE`/`REMARQUES`, `SYNONYME`, `PROVERBES`/`PROVERBE`, `SUPPLÉMENT AU DICTIONNAIRE`. Unknown values log a warning and default to `Remarque`.
- Content, citations, and indents via `extract_content`.

Any `<variante>` children inside the rubrique are returned separately as supplement senses.

### 1i. ID generation

`make_id(headword, homograph_index)`:

1. NFKD-normalize, lowercase.
2. Strip all non-ASCII characters.
3. Replace all non-alphanumeric characters with `_`.
4. Collapse consecutive `_` to one.
5. Strip leading and trailing `_`.
6. If empty or doesn't start with a letter, prepend `e_`.
7. If `homograph_index` is not nothing, append `.N`.

Examples: `DÉGOÛTÉ, ÉE` → `degoute_ee`. `À` → `a`. `-ESQUE` → `e_esque`.

### 1j. ID deduplication

Deduplication runs twice: once per file (on `parse_file` return), and once globally (on `parse_all` return).

For any ID that appears more than once, all occurrences receive a `_N` suffix in encounter order: `degout_1`, `degout_2`, etc. Entries with unique IDs are left unchanged.

Deduplication mutates `entry.id` (a `Ref{String}`) in place.


## Phase 2: Author resolution

**Input/output**: mutates `Citation.resolved_author` in place across all entries.

For each entry, citations are collected in document order by walking: body elements (senses only) → sense citations → sense indents (recursive) → sense rubriques → then entry-level rubriques.

A running `last_author` variable (initially empty) tracks the most recent named author:

- If `author == "ID."` and `last_author` is non-empty: `resolved_author = last_author`.
- If `author` is non-empty and not `"ID."`: update `last_author`, set `resolved_author = author`.
- Otherwise: `resolved_author = author` (preserving whatever it was, including empty).

Author resolution is scoped to each entry independently. The `last_author` resets at entry boundaries.

**Edge case**: an `"ID."` citation with no preceding named author in the same entry gets `resolved_author = ""`.


## Phase 3: Indent classification

**Input/output**: mutates `Indent.classification` in place. After this phase, every indent has a non-null classification.

Classification is recursive: after classifying a parent indent, all of its children are classified.

Three tiers are tried in order. The first to succeed wins.

### Tier 0: Verdicts (external overrides)

Loaded from a CSV keyed on `(file, line)`. Columns: `file`, `line`, `check` (optional), `heuristic_role`, `llm_role`, `llm_confidence`. The `llm_role` and `llm_confidence` columns are used; `heuristic_role` is informational.

If a verdict exists for the indent's source location:

- If a `check` value is present and the indent's plain-text content does not start with it, the verdict is rejected with a warning.
- Otherwise, the indent is classified with the verdict's role, method `LlmAssisted`, and the verdict's confidence.

### Tier 1: Deterministic (tag-based)

Operates on the raw markup content string (not stripped of tags):

| Condition | Role | Confidence |
|-----------|------|------------|
| Contains `<semantique type="indicateur">Fig.` | Figurative | 1.0 |
| Contains `<semantique type="domaine">` | DomainLabel | 1.0 |
| Contains `<nature>` | NatureLabel | 1.0 |
| Contains `<exemple>` | Locution | 1.0 |
| Contains `<a ref=`, plain text < 120 chars, starts with `voy.`/`V.`/`Voy.`/`voyez` (case-insensitive) | CrossReference | 1.0 |
| Contains `<a ref=`, plain text < 120 chars, ends with `, voy.` | CrossReference | 0.95 |

The checks are tried in this order; first match wins.

**Important**: the presence of `<nature>` takes precedence over any heuristic interpretation of the inner text. For example, `<nature>Substantivement.</nature>` is always classified as NatureLabel (deterministic, confidence 1.0), even though the plain text `Substantivement.` would otherwise match the VoiceTransition heuristic.

### Tier 2: Heuristic (text patterns)

Operates on both the raw content and the plain-text (stripped) content:

| Condition (on plain text unless noted) | Role | Confidence |
|----------------------------------------|------|------------|
| Starts with proverb marker (`Prov.`, `Proverbe`, `Proverbialement`) | Proverb | 0.9 |
| Starts with register label (large pattern: `Populaire`, `Familièrement`, `Vulgairement`, `Par extension`, `Néologisme`, `Vieux`, etc.) | RegisterLabel | 0.85 |
| Starts with voice/grammatical transition (`V. n`, `V. a`, `V. réfl`, `Se conjugue`, `Absolument`, `Substantivement`, `Au pluriel`, etc.) | VoiceTransition | 0.85 |

These heuristic patterns are only reached if no deterministic rule fired. In particular, text wrapped in `<nature>` will have already been classified as NatureLabel by the deterministic tier, so it never reaches these patterns.
| Contains `<a ref=` (raw) and matches cross-ref heuristic (`Il est`/`C'est`/`On dit`/`Se dit` + short gap + `<a ref=`) | CrossReference | 0.8 |
| Starts with definition-like phrase (`Se dit`, `Terme de`, `Celui qui`, `Action de`, `Nom donné`, etc.) | Elaboration | 0.75 |
| Starts with `Fig.` | Figurative | 0.9 |
| Has at least one citation | Continuation | 0.5 |
| Non-empty plain text (fallback) | Elaboration | 0.4 |

Tried in this order; first match wins.


## Phase 4: Locution extraction

**Input/output**: mutates `Indent.canonical_form` and may reclassify some indents.

Only processes indents currently classified as `Locution`. For each:

1. **Reflexive reclassification**: if plain text matches `^S'[A-Z...]..., v. réfl`, reclassify to `VoiceTransition` (Heuristic, 0.9). No canonical form extracted.

2. **Exemple extraction**: if the raw content contains `<exemple>...</exemple>`, the inner text becomes the canonical form.

3. **Comma splitting**: if the plain text contains a comma, take the text before the first comma (stripped). If this exceeds 60 characters, skip.

4. **Fallback**: if none of the above produce a form, the indent keeps `canonical_form=""`. This will be flagged in the review queue.


## Phase 5: Scope resolution

**Input/output**: mutates `Entry.body` (replacing/reordering `BodyElement`s) and `Sense.indents` (reparenting indents under transitions).

Scope resolution produces three possible outcomes for a transition indent:

- **Inter-sense scope**: a terminal VoiceTransition indent opens a `TransitionGroup` over subsequent senses in the entry body. Handled in pass 1 (5a).
- **Intra-sense scope**: a NatureLabel or VoiceTransition indent absorbs subsequent sibling indents within the same sense as its children. Handled in pass 2 (5b).
- **No scope**: the transition indent remains a leaf node (e.g. terminal with nothing following, or already absorbed by another transition). No restructuring.

Note: inter-sense scoping considers only VoiceTransition, whereas intra-sense scoping considers both NatureLabel and VoiceTransition. This asymmetry is intentional: NatureLabel transitions (e.g. `<nature>Substantivement.</nature>`) partition usage within a sense but do not open new top-level entry structure.

### 5a. Inter-sense scoping

Processes each entry's body sequentially, looking for senses that carry a terminal transition. A terminal transition is an indent that is:

1. The final indent in the sense's indent list.
2. Classified as VoiceTransition.
3. Has no citations attached.

All three conditions must hold. When found:

1. **Scope boundary**: scan forward through subsequent body elements. The scope ends just before the next sense that also has a trailing `VoiceTransition` (with no citations), or at end of body.

2. **Zero-scope**: if there are no subsequent elements, or the scope boundary falls at 0 (the immediately following element is itself a transition carrier), the transition is left in place as an annotation.

3. **Strong vs medium**: the transition's plain text is tested against two patterns:
   - `^S'[A-Z...]..., v. réfl/etc.` → strong, with extracted form and POS.
   - `^[UPPERCASE FORM], v. n|a|réfl|s. m|f|adj` → strong, with extracted form and POS.
   - Everything else → medium.

4. **Restructuring**: the transition indent is removed from the source sense. A `TransitionGroup` is created wrapping the scoped body elements. Both the (now shorter) source sense and the new group are emitted to the new body.

5. **Large-scope warning**: if a group scopes more than 15 senses, it is logged as ambiguous.

Inter-sense scoping examines only the last indent of each sense. A VoiceTransition indent that appears at a non-terminal position within a sense (e.g. `Substantivement, ...` followed by further indents) is never considered for inter-sense scoping; it is handled exclusively by intra-sense scoping in pass 2.

### 5b. Intra-sense scoping

After inter-sense scoping, each sense (including those inside `TransitionGroup`s) has its indents processed:

Within a sense's indent list, any `NatureLabel` or `VoiceTransition` indent that is not the last in the list absorbs all following non-transition indents as children, up to the next transition or end of list.


## TEI emission

The TEI emitter serializes the enriched, scope-resolved model to TEI Lex-0 XML. Key behaviors:

### Markup conversion

Gannaz inline markup is converted to TEI equivalents via regex substitution:

| Source | TEI |
|--------|-----|
| `<semantique type="domaine">` | `<usg type="domain">` |
| `<semantique type="indicateur">` | `<usg type="sem">` |
| `<semantique>` | `<usg type="sem">` |
| `<a ref="X">Y</a>` | `<xr><ref target="#X">Y</ref></xr>` |
| `<exemple>` | `<mentioned>` |
| `<nature>` | `<usg type="gram">` |
| `<i lang="la">` | `<foreign xml:lang="la">` |
| `<i>` | `<mentioned>` |

All `<usg>` text content is lowercased (tag attributes and tag names are preserved).

### Label splitting

For role-dispatched indent types that carry a label (Figurative, DomainLabel, RegisterLabel, NatureLabel, VoiceTransition), the TEI content is split into a label portion and a definition portion. The split tries, in order:

1. Leading `<gramGrp><gram>...</gram></gramGrp>` → label is the gram content.
2. Leading `<usg>...</usg>` → label is the usg content.
3. Leading `Fig.` → label is `fig.`.
4. Fallback: the entire content is the label, definition is empty.

### Sense IDs

TEI `xml:id` attributes are generated hierarchically: `{entry_id}_s{body_index}` for top-level senses, with `.{child_index}` appended at each nesting level.

### Role dispatch

Each `IndentRole` has a dedicated `emit_indent` method:

- **Figurative**: `<sense type="figuré">` with `<usg type="sem">` label.
- **DomainLabel**: `<sense>` with `<usg type="domain">` label; falls back to default sense if label/def split fails.
- **RegisterLabel**: `<sense>` with `<usg type="register">` label.
- **Locution**: `<re type="locution">` with optional `<form><orth>` for canonical form.
- **Proverb**: `<re type="proverbe">`.
- **CrossReference**: `<note type="xref">`.
- **NatureLabel / VoiceTransition**: if the indent has children, citations, or definition text, emits `<sense>` with `<usg type="gram">` label. Otherwise emits a bare `<usg type="gram">` element. After intra-sense scoping, transition indents that absorbed followers always have children and therefore always emit as `<sense>` elements.
- **Elaboration / Continuation / Constructional**: default `<sense>` with any leading `<usg>` elements extracted.

### TransitionGroup dispatch

- **Strong** (`:strong`): `<entry type="grammaticalVariant">` with `<form><orth>` and `<gramGrp>`.
- **Medium** (`:medium`): `<sense>` with `<usg type="gram">` label.

### Rubrique dispatch

Each `RubriqueKind` maps to an XML wrapper:

| Kind | Opening tag |
|------|------------|
| Historique | `<note type="historique">` |
| Remarque | `<note type="remarque">` |
| Supplement | `<note type="supplément">` |
| Etymologie | `<etym>` |
| Synonyme | `<re type="synonyme">` |
| Proverbes | `<re type="proverbes">` |

Rubrique body: the main content as `<p>`, then each indent's content as a `<p>`, with citations after each.


## SQLite emission

### Schema

Six tables: `entries`, `senses`, `citations`, `locutions`, `rubriques`, `review_queue`. See `docs/schema.md` for column-level documentation.

### Sense insertion

Body elements map to `senses` rows:

- `Sense` → `sense_type='sense'`, with `num`, `is_supplement`, and `indent_id` derived as `{entry_id}.{num || 1}`.
- `TransitionGroup` → `sense_type='grammatical_variant'` (strong) or `'usage_group'` (medium), with `transition_type`, `transition_form`, `transition_pos`.
- `Indent` → `sense_type` derived from role (e.g. `'figurative'`, `'locution'`, `'domain'`, `'cross_reference'`, `'annotation'` for childless NatureLabel/VoiceTransition, `'transition_group'` for those with children, `'sense'` for Elaboration/Continuation/Constructional and fallback).

All insertions are recursive: each indent's children produce child rows with `parent_sense_id` pointing to the parent's auto-incremented `sense_id`, and `depth` incremented. After scope resolution, the indent hierarchy (including intra-sense grouping) is reflected in the `parent_sense_id` and `depth` columns.

### Locutions

An indent classified as `Locution` with a non-empty `canonical_form` produces a row in `locutions` keyed on `sense_id`.

### FTS

Full-text search tables (`senses_fts`, `citations_fts`) are populated after the main transaction commits, using `fts5` content-sync from the base tables.

### Review queue

All `ReviewFlag`s are inserted with `context` serialized as JSON.


## Flag collection

Flags are generated post-scope-resolution and record items for human review.

### Flag types

- **low_confidence**: indents with `confidence ≤ 0.5` in a semantic role (Figurative, DomainLabel, Locution, Proverb, CrossReference, RegisterLabel, VoiceTransition, NatureLabel). Includes neighboring indent context.
- **skipped_locution**: indents classified as Locution but with empty `canonical_form`.
- **likely_locution**: indents *not* classified as Locution but whose plain text starts with `Loc.` or `Locution`.
- **scope_decision**: every `TransitionGroup` in the body (both strong and medium), recording scope type, count, and boundary content.
- **large_scope**: subset of scope_decision where scoped senses > 15.
- **large_intra_scope**: intra-sense transitions with > 5 children.
- **calibration_sample**: stratified random sample of 5 indents per (role, method) bucket, seeded deterministically (`seed=42`).
