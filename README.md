# TEI-Littre
A TEI Lex-0 edition of Émile Littré's *Dictionnaire de la langue française* (1872–1877), produced by enriching François Gannaz's [XMLittré](https://bitbucket.org/Mytskine/xmlittre-data) digitization.

Littré's dictionary is an important document of French lexicography: 78,600 entries with etymological, historical, and literary citation apparatus, covering the language from Old French through the late 19th century. François Gannaz digitized it as custom XML; this project transforms that XML into [TEI Lex-0](https://dariah-eric.github.io/lexicalresources/pages/TEILex0/TEILex0.html) — the interchange format used by the digital humanities community for dictionary encoding — along with an SQLite database for computational use.

The pipeline is not a mechanical format conversion. Gannaz's XML uses a flat `<indent>` element as an overloaded catch-all for sub-senses, figurative uses, domain labels, locutions, register shifts, cross-references, proverbs, and grammatical transitions. The pipeline classifies each indent by semantic role, extracts canonical forms from locutions, resolves scope ambiguities in grammatical transitions, and emits structured TEI that preserves Littré's semantic hierarchy.

## Downloads
Pre-built data products are attached [coming soon] to each [GitHub release](../../releases):

| File | Description | Size (compressed) |
|------|-------------|-------------------|
| `littre.tei.xml.gz` | TEI Lex-0 XML, all 78,600 entries | ~33 MB |
| `littre.db.gz` | SQLite database for computational queries | ~55 MB |

Decompress with `gunzip littre.tei.xml.gz` or equivalent.

**Status**: Still under development. Check back soon.


## Enrichments over the source
**Structural classification** — 86,942 flat `<indent>` blocks classified into semantic roles: definitions, figurative senses, domain labels (`Terme de marine`, `Terme de musique`), register labels (`familièrement`, `populairement`), locutions, proverbs, cross-references, nature labels (`s. m.`, `adj.`), and voice transitions (`v. réfl.`). 100% coverage.

**Author resolution** — 41,579 "ID." (idem) citations resolved to the actual author by backward scan through the citation chain.

**Locution extraction** — 13,972 canonical forms extracted from locution definitions (e.g., `Avoir envie` from a locution indent under ENVIE).

**Scope resolution** — Grammatical transitions (`Se donner, v. réfl.`, `Substantivement`, `Impersonnellement`) scoped to the correct set of following senses and restructured as nested entries or sense groups.

**Usage label normalization** — Inline `<semantique>` and `<nature>` markup separated from definitions and emitted as proper TEI `<usg>` elements with a controlled type vocabulary: `domain`, `sem`, `gram`, `register`. Label text lowercased (these are editorial labels, not proper nouns).

**Rubrique preservation** — All rubrique types (étymologie, historique, remarque, supplément, synonyme, proverbes) faithfully emitted with complete content, citations, and structured sub-blocks.

**Supplement integration** — 1,178 supplement entries and supplement variantes marked with `source="supplement"` and integrated into the main entry structure.


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

- **entries**: headword, POS, pronunciation, xml_id, source file, supplement flag
- **senses**: definition text, sense number, parent entry, indent role classification
- **citations**: quote text, author (original + resolved), reference, parent sense
- **review_queue**: pipeline-flagged items for human review (387 items across 5 categories)

Example queries:

```sql
-- All citations from Molière
SELECT e.headword, c.text, c.reference
FROM citations c
JOIN senses s ON c.sense_id = s.id
JOIN entries e ON s.entry_id = e.id
WHERE c.resolved_author = 'MOLIÈRE';

-- Entries with figurative senses
SELECT DISTINCT e.headword
FROM senses s JOIN entries e ON s.entry_id = e.id
WHERE s.role = 'figurative';
```


## Building from source
### Requirements

- Python 3.11+
- [lxml](https://lxml.de/) (`pip install lxml`)

### Running the pipeline
Place the Gannaz XML source files (`a.xml` through `z.xml`, `a_prep.xml`) in `data/source/`, then:

```
PYTHONPATH=src python -m tei_littre data/source data
```

Output: `data/littre.tei.xml` and `data/littre.db`.


### Spot-checker
A side-by-side TUI for comparing source XML against TEI output:

```
pip install textual rich
PYTHONPATH=src python -m tei_littre.spotcheck ENVIE
```

Requires [Textual](https://textual.textualize.io/). Navigate with `j`/`k`, `space`/`b`, `d`/`u`. Sections are color-coded by rubrique type.


### Tests
```
PYTHONPATH=src python -m pytest tests/
```


## Repository structure
```
tei-littre/
├── src/tei_littre/
│   ├── model.py               Dataclass definitions
│   ├── normalize.py            Phase 0: mechanical XML normalization
│   ├── parse.py                Phase 1: Gannaz XML → internal model
│   ├── resolve_authors.py      Phase 2: ID. citation resolution
│   ├── classify_indents.py     Phase 3: indent semantic classification
│   ├── extract_locutions.py    Phase 4: locution form extraction
│   ├── scope_transitions.py    Phase 5: transition scope resolution
│   ├── collect_flags.py        Review flag generation
│   ├── emit_tei.py             Phase 7a: model → TEI Lex-0 XML
│   ├── emit_sqlite.py          Phase 7b: model → SQLite
│   ├── spotcheck.py            Side-by-side TUI spot-checker
│   └── __main__.py             Pipeline orchestrator
├── tests/                      Test suite
├── data/
│   ├── source/                 Gannaz XML files (not tracked)
│   ├── littre.tei.xml          TEI output (not tracked; see Releases)
│   └── littre.db               SQLite output (not tracked; see Releases)
├── LICENSE                     CC-BY-SA 4.0
└── README.md
```


## Known limitations

- **Résumé blocks**: 96 long entries have tables of contents (`<résumé>` in source) currently emitted as placeholders.
- **Sense-level xml:id**: Not yet implemented. Needed for resolving Littré's internal cross-references ("voy. PIED, n° 1").
- **Large-scope transitions**: 8 entries (DONNER, FAIRE, etc.) have grammatical transitions that scope over >15 senses. Manually reviewed but may need refinement.
- **Mid-text usage labels**: ~730 inline `<usg>` elements remain inside `<def>` where they appear mid-sentence (reflexive verb patterns like "Se damner, `<usg>v. réfl.</usg>` Attirer sur soi..."). These are structurally correct for their context.
- **Locution def deduplication**: Canonical form text is sometimes repeated in the `<def>` element.


## Source data

This project builds on:

> François Gannaz, *XMLittré — Le dictionnaire de la langue française d'Émile Littré en XML*, version 1.3.
> [bitbucket.org/Mytskine/xmlittre-data](https://bitbucket.org/Mytskine/xmlittre-data)
> License: [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)

The underlying text is the *Dictionnaire de la langue française* by Émile Littré, published by Hachette in four volumes (1872–1877) with a supplement (1877). The original text is in the public domain.


## License

CC-BY-SA 4.0. See [LICENSE](LICENSE).
