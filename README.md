# tei-littre
A TEI Lex-0 edition of Émile Littré's *Dictionnaire de la langue française* (1872–1877), produced by enriching François Gannaz's [XMLittré](https://bitbucket.org/Mytskine/xmlittre-data) digitization.

The pipeline parses Gannaz's custom XML into a normalized internal model, then emits valid [TEI Lex-0](https://dariah-eric.github.io/lexicalresources/pages/TEILex0/TEILex0.html) XML.

Enrichments over the source:
- **Author resolution**: 41,000+ "ID." (idem) citations resolved to the actual author
- **Indent classification**: 87,000 overloaded `<indent>` blocks classified into semantic roles (figurative senses, domain labels, locutions, cross-references, etc.) at 99.4% coverage
- **Markup normalization**: Original XML tags (`<semantique>`, `<nature>`, `<exemple>`, etc.) mapped to TEI equivalents (`<usg>`, `<gramGrp>`, `<mentioned>`, etc.)
- **Structural cleanup**: Rubrique types normalized, supplement variantes marked, cross-references linked

**Status**: Under development. Check back soon.

## Source data
This project builds on:

> François Gannaz, *XMLittré — Le dictionnaire de la langue française d'Émile Littré en XML*, version 1.3.
> [bitbucket.org/Mytskine/xmlittre-data](https://bitbucket.org/Mytskine/xmlittre-data)
> License: [CC-BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/)

The underlying text is the *Dictionnaire de la langue française* by Émile Littré, published by Hachette in four volumes (1872–1877) with a supplement (1877). The original text is in the public domain.

## License
CC-BY-SA 4.0. See [LICENSE](LICENSE).
