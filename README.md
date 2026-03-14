# Deep-Littré
A deeply structured, computationally enriched edition of Émile Littré's _Dictionnaire de la langue française_ (1872–1877), built on François Gannaz's XMLittré digitization. Available as TEI Lex-0 XML and SQLite.

Littré's dictionary is an important document of French lexicography: 78,600 entries with etymological, historical, and literary citation apparatus, covering the language from Old French through the late 19th century. François Gannaz digitized it as custom XML; this project transforms that XML into [TEI Lex-0](https://dariah-eric.github.io/lexicalresources/pages/TEILex0/TEILex0.html), along with an SQLite database for computational use.

The pipeline is not a mechanical format conversion. Gannaz's XML uses a flat `<indent>` element as an overloaded catch-all for sub-senses, figurative uses, domain labels, locutions, register shifts, cross-references, proverbs, and grammatical transitions. The pipeline classifies each indent by semantic role, extracts canonical forms from locutions, resolves scope ambiguities in grammatical transitions, and emits structured TEI that preserves Littré's semantic hierarchy.

> **Status**: This is still a work in progress. The pipeline produces usable data as-is, but classification accuracy is still being refined. Be sure to review the [Known limitations](#known-limitations) section.

## Downloads
Pre-built data products are attached [coming soon] to each [GitHub release](../../releases):

| File | Description | Size (compressed) |
|------|-------------|-------------------|
| `littre.tei.xml.gz` | TEI Lex-0 XML, all 78,600 entries | ~33 MB |
| `littre.db.gz` | SQLite database for computational queries | ~55 MB |

Decompress with `gunzip littre.tei.xml.gz` or equivalent.

## Enrichments over the source
**Structural classification** — 86,942 flat `<indent>` blocks classified into semantic roles: definitions, figurative senses, domain labels (`Terme de marine`, `Terme de musique`), register labels (`familièrement`, `populairement`), locutions, proverbs, cross-references, nature labels (`s. m.`, `adj.`), and voice transitions (`v. réfl.`). 100% coverage.

**Author resolution** — 41,579 "ID." (idem) citations resolved to the actual author by backward scan through the citation chain.

**Locution extraction** — 13,972 canonical forms extracted from locution definitions (e.g., `Avoir envie` from a locution indent under ENVIE).

**Scope resolution** — Grammatical transitions (`Se donner, v. réfl.`, `Substantivement`, `Impersonnellement`) scoped to the correct set of following senses and restructured as nested entries or sense groups.

**Usage label normalization** — Inline `<semantique>` and `<nature>` markup separated from definitions and emitted as proper TEI `<usg>` elements with a controlled type vocabulary: `domain`, `sem`, `gram`, `register`. Label text lowercased (these are editorial labels, not proper nouns).

**Rubrique preservation** — All rubrique types (étymologie, historique, remarque, supplément, synonyme, proverbes) faithfully emitted with complete content, citations, and structured sub-blocks.

**Supplement integration** — 1,178 supplement entries and supplement variantes marked with `source="supplement"` and integrated into the main entry structure.

**Classification overrides** — Support for LLM-assisted reclassification via external verdicts CSV, keyed on source file and line number for traceability.


## TEI structure
Each entry follows this pattern:

```xml
<entry xml:id="envie">
  <form type="lemma">
    <orth>ENVIE</orth>
    <pron>an-vie</pron>
  </form>
  <gramGrp><gram type="pos">s. f.</gram></gramGrp>
  <sense n="1">
    <def>Sentiment de tristesse, d'irritation...</def>
    <cit type="example">
      <quote>L'envie suit la vertu comme l'ombre suit le corps</quote>
      <bibl><author>BOILEAU</author></bibl>
    </cit>
    <sense type="figuré">
      <usg type="sem">fig.</usg>
      <def>Le serpent de l'envie</def>
    </sense>
  </sense>
  <!-- ... numbered senses ... -->
  <note type="historique">
    <p>XIIe s.</p>
    <cit type="example">...</cit>
  </note>
  <etym>
    <p>Provenç. enveia ; espagn. envidia ; ital. invidia ;
    du lat. invidia, de invidere (voy. ENVIER).</p>
  </etym>
</entry>
```

Key conventions:
- `<gramGrp>` appears only at entry level for the headword's part of speech
- `<usg>` carries all usage, domain, register, and grammatical context labels
- `type` attribute values use French where the content is French (`historique`, `figuré`, `supplément`)
- TEI element names and standard vocabulary stay English (part of the TEI standard)
- Author abbreviations preserved as-is in display; resolved forms in `<author>` elements

## SQLite schema
The SQLite database provides a flat, queryable view of the dictionary:

- **entries**: headword, POS, pronunciation, entry_id, source file, supplement flag
- **senses**: definition text, sense number, parent entry, indent role classification, `indent_id` (ASCII-normalized path like `defaut.3.1`), `xml_id` (matching the TEI `xml:id` attribute)
- **citations**: quote text, author (original + resolved), reference, parent sense
- **locutions**: 13,972 canonical forms keyed to sense_id
- **review_queue**: pipeline-flagged items for human review

Example queries:

```sql
-- All citations from Molière
SELECT e.headword, c.text_plain, c.reference
FROM citations c
JOIN senses s ON c.sense_id = s.sense_id
JOIN entries e ON s.entry_id = e.entry_id
WHERE c.resolved_author = 'MOLIÈRE';

-- Entries with figurative senses
SELECT DISTINCT e.headword
FROM senses s JOIN entries e ON s.entry_id = e.entry_id
WHERE s.role = 'Figurative';

-- Look up a locution
SELECT l.canonical_form, s.content_plain
FROM locutions l
JOIN senses s ON l.sense_id = s.sense_id
WHERE l.canonical_form LIKE '%panneau%';
```


## Building from source
### Requirements

- Julia 1.10+
- Dependencies are managed via `Project.toml`; run `julia --project=. -e 'using Pkg; Pkg.instantiate()'` to install

### Running the pipeline
Place the Gannaz XML source files (`a.xml` through `z.xml`, `a_prep.xml`) in `data/source/`, then:

```
julia bin/run_pipeline.jl data/source data/output
```

Output: `data/output/littre.tei.xml` and `data/output/littre.db`.

Optional flags:
```
julia bin/run_pipeline.jl data/source data/output \
  --patches patches/patches.toml \
  --verdicts data/verdicts.csv
```

### Tests
```
julia --project=. test/smoke.jl
julia --project=. test/smoke_enrich.jl
julia --project=. test/smoke_scope.jl
julia --project=. test/smoke_tei.jl
julia --project=. test/smoke_sqlite.jl
```

## Repository structure
```
deep-littre/
├── Project.toml
├── src/
│   ├── DeepLittre.jl           Module root, using/include/export
│   ├── model.jl                Type definitions (traits, structs, enums)
│   ├── parse.jl                Phase 1: Gannaz XML → internal model
│   ├── enrich.jl               Phases 2–4: author resolution, indent
│   │                           classification, locution extraction
│   ├── scope.jl                Phase 5: transition scope resolution
│   ├── flags.jl                Review flag generation
│   ├── emit_tei.jl             Model → TEI Lex-0 XML
│   └── emit_sqlite.jl          Model → SQLite
├── bin/
│   └── run_pipeline.jl         CLI entry point
├── test/
│   ├── smoke*.jl               Smoke tests for each pipeline stage
│   └── fixtures/               Synthetic test data
├── scripts/
│   └── ...                     Experimental post-processing scripts
├── patches/
│   └── patches.toml            Source XML corrections (line-targeted)
├── data/
│   ├── source/                 Gannaz XML files (not tracked)
│   └── output/                 Pipeline outputs (not tracked; see Releases)
├── README.md
└── LICENSE
```


## Design notes

### Type system
Indent roles and rubrique kinds are modeled as trait hierarchies (`abstract type IndentRole end` with concrete singletons like `Figurative`, `DomainLabel`, etc.). This enables Julia's multiple dispatch for the emitters — each role gets its own `emit_indent` method rather than a monolithic match/case.

The `Sense`/`TransitionGroup` split (both subtypes of `BodyElement`) cleanly separates regular senses from grammatical transition containers, avoiding the "one struct with dead fields" antipattern.

### Immutability with targeted mutation
Most types are immutable structs. `Indent` and `Citation` are mutable because enrichment phases modify their `classification`, `canonical_form`, and `resolved_author` fields in place. `Entry.id` is a `Ref{String}` to allow deduplication without reconstructing entire entries.

### Patches
Source corrections are line-targeted string replacements in TOML format, applied in memory during parse. The constraint is that patches never add or remove lines, so source line numbers are invariant — enabling `SourceLocation` (file + line) on every indent as both a debugging aid and a stable key for classification overrides.

### Classification overrides (verdicts)
LLM-assisted reclassification results are loaded from a CSV keyed on `(file, line)`. They take precedence over heuristic classification but are applied during the same pass. An optional `check` column verifies that the content at the specified line matches expectations.


## Known limitations

- **Résumé blocks**: 96 long entries have tables of contents (`<résumé>` in source) currently emitted as placeholders.
- **Large-scope transitions**: 3 entries have grammatical transitions scoping over >15 senses.
- **Mid-text usage labels**: ~730 inline `<usg>` elements remain inside `<def>` where they appear mid-sentence.
- **Locution def deduplication**: Canonical form text is sometimes repeated in the `<def>` element.
- **Locution under-detection**: An estimated ~12,000 locutions are currently misclassified as continuation/elaboration. LLM-assisted reclassification is underway.
- **Source data errors**: Gannaz's XML contains a small number of errors including missing homograph indices, incorrect `terme` attributes, and accent-collision headwords (31 pairs). These are corrected via `patches/patches.toml`.


## Entry and sense IDs
Entry IDs are ASCII-normalized from the headword: accents stripped, special characters replaced with underscores (`DÉGOÛTÉ, ÉE` → `degoute_ee`). Homograph entries in the source XML carry an index via `sens=` attribute (`degrossi_ie.1`, `degrossi.2`).

When multiple entries produce the same normalized ID — either from accent collisions (`DÉGOUT`/`DÉGOÛT` → both `degout`) or missing homograph indices — all occurrences receive a numeric suffix: `degout_1`, `degout_2`.


## Source patches
Corrections to Gannaz's source XML live in `patches/patches.toml` as line-targeted string replacements. Patches are applied in memory during parse, keeping the originals in `data/source/` untouched. The constraint is that patches never add or remove lines, preserving source line numbers as stable identifiers.

Current categories:

- **cit_tail_splits**: 15 cases where transition labels (`Absolument.`, `Substantivement.`) appear as bare text between citations inside a single `<indent>`. Patch splits the indent at the transition boundary on the same line.
- **missing_homograph_index**: Entries like DI- that appear twice without `sens=` attributes to distinguish them.
- **wrong_terme**: Entries where the `terme` attribute doesn't match the actual headword (e.g. `-ESQUE` entered as `ESQUAQUE`).

Additional source errors are expected to surface as the full corpus is processed. Patches can be added incrementally; the pipeline rebuilds deterministically from patched sources.


## Source data
This project builds on:

> François Gannaz, *XMLittré — Le dictionnaire de la langue française d'Émile Littré en XML*, version 1.3.
> [bitbucket.org/Mytskine/xmlittre-data](https://bitbucket.org/Mytskine/xmlittre-data)
> License: [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)

The underlying text is the *Dictionnaire de la langue française* by Émile Littré, published by Hachette in four volumes (1872–1877) with a supplement (1877). The original text is in the public domain.


## License
CC-BY-SA 4.0. See [LICENSE](LICENSE).
