# Roadmap

This roadmap reflects the **actual** state of the project. `book-to-skill` is already a
mature generator (**v1.6.1**) — this is not a pre-1.0 plan. The version line is sourced
from `scripts/bookextract/__init__.py`; shipped features are recorded in
[`CHANGELOG.md`](CHANGELOG.md), each tagged with its upgrade *migration class*.

Open work is tracked as [GitHub issues](https://github.com/strawberry-code/book-to-skill/issues);
milestones below link to them where they exist.

## Direction — Mycelia: book → OKF knowledge vault

The strategic default is shifting from **one skill per book** (doesn't scale past a few books —
every skill description is injected into context each session) to an atomic, interlinked
**[OKF](https://okf.md/spec/) knowledge vault** that scales to hundreds of books. The new emitter
is **[`MYCELIA.md`](MYCELIA.md)**; the legacy `SKILL.md` skill flow stays supported.

Landed in this direction:

- **`MYCELIA.md` vault emitter** — atomic notes (concept/framework/principle/entity/method/anti-pattern),
  OKF-native portable bundle, `# Citations` provenance, check-before-create cross-book reconciliation.
- **`book-extract lint`** — stdlib OKF-bundle linter: zero dangling + `type`-required + reserved-file +
  citation-coverage + reciprocal-backlink checks.
- **Orchestrated build (P0)** — `book-extract build-plan` + `assemble`: the LLM emits validated Note JSON,
  the code chunks, grounds (normalize-then-match, ligature/line-break tolerant), dedups, inserts reciprocal
  backlinks, computes folios, and gates with the linter. Removes hand-emission drift. See
  [`docs/mycelia-productization.md`](docs/mycelia-productization.md).
- **Deterministic reconciliation (P1)** — `reconcile.py`: beyond slug/alias dedup, folds **acronym ↔
  expansion** (`bsc` ↔ `binary-symmetric-channel`) and **singular ↔ plural** (`encoder` ↔ `encoders`)
  with zero dependencies. Conservative by design (`basis`/`bases` stay distinct); the folded slug becomes
  an alias so `## Related` resolves through it.

Next for Mycelia (from the productization assessment):

- **Embedding reconciliation (P1+)** — beyond the deterministic acronym/plural folding above:
  cosine-similarity + LLM arbitration for pure-semantic or cross-lingual synonyms that share no string
  ("Deutschland"/"Germany"). Deferred — would break the current zero-dependency stance.
- **Semantic QA pass** — an independent verifier checking each note's body against its cited source.
- **Skill → vault converter** — re-emit already-generated book-skills (`chapters/*.md` + manifest) as OKF bundles.
- **Obsidian vault → OKF converter** — `[[wikilink]]` → bundle-relative links + frontmatter normalization.
- **Contradiction dashboard** — aggregate `contested: true` notes into a `reports/` view.
- **Headless autonomy** — optional `anthropic` SDK / `claude -p` path if the in-session build proves too manual at scale.

## v1.6.1 — current

Shipped (see CHANGELOG for the full list and migration classes):

- Single-document → Claude Code skill generation across PDF / EPUB / DOCX / TXT / Markdown /
  reStructuredText / AsciiDoc / HTML / RTF / MOBI/AZW/AZW3.
- Capability gating: study/reference always; **code review**, **stack personalization** and
  **scaffold** for code/buildable books; **figures** for technical extraction.
- Grounded answers — chapter + verbatim quote (page folio for text PDFs), grep-verified.
- Provenance manifest (`.book-to-skill.json`) + deterministic `upgrade` flow + `.source/` archive.
- Diagram/figure capture (#8); printed page folios (#11).
- **`uv`-first developer workflow** — installable package, `book-extract` console script,
  optional-dependency extras, and GitHub Actions CI.
- **Public, copyright-safe demo** under `examples/` (CC0 input + generated sample skill, #14).
- Strict quality gate (ruff · mypy · lizard · xenon) and Sphinx API docs.

## v1.7.0 — next

Adoption & breadth (this release line):

- **Broader inputs** beyond books — technical papers, internal wikis, video transcripts.
  ([#7](https://github.com/strawberry-code/book-to-skill/issues/7))
- **Propagate `templates/` to existing technical skills** generated before scaffolds existed.
  ([#12](https://github.com/strawberry-code/book-to-skill/issues/12))
- A public, copyright-safe demo input + a published sample skill *(planned)*.
  ([#14](https://github.com/strawberry-code/book-to-skill/issues/14))
- Validation checks for generated skill folders (structure/manifest lint) *(planned)*.
- Pay down the `cli.py` complexity debt so `lizard`/`xenon` can become required gates.
  ([#13](https://github.com/strawberry-code/book-to-skill/issues/13))

## v1.8.0+ — multi-document

- **Multi-book domain libraries** — now realized through the **Mycelia** vault (above): N related
  books converge into one OKF bundle with shared canonical concept notes and cross-book citations,
  rather than one fused skill. ([#6](https://github.com/strawberry-code/book-to-skill/issues/6))
- Cross-document references and a shared glossary across a domain library — native to the vault
  (`# Citations` + `## Related` + reconciliation).

> Items marked *(planned)* are not yet implemented. The dated, shipped record of truth is
> always [`CHANGELOG.md`](CHANGELOG.md).
