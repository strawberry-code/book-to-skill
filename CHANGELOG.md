# Changelog

All notable changes to **book-to-skill** (the generator). Generated skills record
the `generator_version` that built them in their `.book-to-skill.json` manifest;
the `book-to-skill upgrade <skill-dir>` flow reads this file to decide what to
re-apply (see SKILL.md → "Upgrading generated skills").

Format based on [Keep a Changelog](https://keepachangelog.com/); versions follow
[Semantic Versioning](https://semver.org/). The generator version is the single
source of truth in `scripts/bookextract/__init__.py` (`__version__`).

## Migration classes

Every feature/fix entry is tagged with **how an existing skill must be upgraded**
to gain it. The upgrade flow applies entries cheapest-class first.

| Class | Meaning | Upgrade cost | Needs archived `.source/`? |
|-------|---------|--------------|-----------------------------|
| `additive` | new file derived from already-captured skill data | low (often no source) | usually no |
| `transform` | rewrites an existing file, no new data from the book | medium (no LLM-on-source) | no |
| `regenerate` | needs the book re-read (new data extracted) | high (LLM on source) | **yes** |

Entry convention: `- <desc> (#issue) [<class>; steps a,b,c]`. The `steps` list
names the SKILL.md generation steps to re-run for a `regenerate` entry, so upgrade
re-runs only those — not the whole pipeline.

---

## [Unreleased]

<!-- Next release. Entries go here, each tagged with its migration class. -->

### Added
- **Mycelia — OKF knowledge-vault emitter (`MYCELIA.md`).** New default generation recipe that turns a
  book into an atomic, interlinked [OKF v0.1](https://okf.md/spec/) bundle: one note per
  concept/framework/principle/entity/method/anti-pattern, bundle-relative Markdown links, reserved
  `index.md`/`log.md`, immutable `raw/`, `# Citations` provenance back to `references/` source notes, and
  **check-before-create cross-book reconciliation** (a concept seen in multiple books → one canonical note
  with multiple citations). Reuses the existing extractor and Step 3.5 grounding contract unchanged. The
  legacy single-book skill emitter (`SKILL.md`) stays supported. [infra]
- **`book-extract lint <bundle>`** — stdlib OKF-bundle linter: every non-reserved `.md` has a non-empty
  `type`; every bundle-relative link resolves (zero dangling); `index.md` carries no frontmatter (except
  root `okf_version`); `log.md` dates are ISO-8601, newest-first; plus citation coverage (≥ a floor) and
  reciprocal `## Related` backlinks. The deterministic success gate for a generated vault. [infra]
- **Mycelia orchestrated build (P0) — `book-extract build-plan` + `assemble`.** Inverts the generator so
  the LLM emits validated *Note JSON* and the **code** assembles the bundle: deterministic chunking
  (`chunking.py`), normalize-then-match grounding that folds ligatures/whitespace and recovers verbatim
  spans across line breaks (`notes.py`), and an assembler that dedups by slug, inserts reciprocal
  backlinks, computes printed folios, and runs the lint gate (`assemble.py`). Removes the drift of
  hand-emitting Markdown. Hybrid in-session (no new dependency, no separate API billing); the
  hand-emission recipe stays as the small-book fallback. [infra]
- **Deterministic reconciliation (P1) — `reconcile.py`.** The assembler now folds two high-precision,
  dependency-free forms of the *same* concept that slug/alias dedup missed: **acronym ↔ expansion**
  (`bsc` ↔ `binary-symmetric-channel`, a single token equal to the initials of a dashed slug) and
  **singular ↔ plural** (slugs differing only by a trailing `s`, `encoder` ↔ `encoders`). The folded slug
  becomes an alias of the canonical note, so `## Related` links resolve through it; the canonical note's
  identity wins regardless of chunk order. Deliberately conservative — `basis`/`bases` and `code`/`coding`
  do **not** merge; pure-semantic and cross-lingual synonymy stay a roadmap item (would need embeddings).
  [infra]

### Changed
- Description tuning (#2) now covers **all** high-frequency triggers from `cues.md`, not a
  2–4 sample. The generated `SKILL.md` "Proactively recall when…" tail is the only activation
  signal at discovery time (cues.md is not in the activation index), so every common user task
  must be reflected there, phrased as the user would say it (symptom/action, not book jargon),
  related triggers merged. Also aligns the `cues.md` Supporting-Files link to its canonical
  short form. (#2) [transform; re-run the SKILL.md frontmatter generation — no source re-read]

## [1.7.0] — 2026-06-24

Extraction-capability release. The single entry is `[infra]` (generator-only): it does **not**
alter generated skill content, so `book-to-skill upgrade` applies nothing to existing skills —
they remain current. It only lets the extractor handle MOBI/AZW where it previously aborted.

### Added
- **Calibre-free MOBI/AZW/AZW3 extraction.** New `MobiPythonExtractor` strategy uses the
  pure-Python `mobi` package (unpacks to HTML, flattened via the existing stdlib
  `extract_html_content`, no BeautifulSoup needed) as a fallback after Calibre's
  `ebook-convert`. The `ebook` format now offers to `pip install mobi` when `ebook-convert`
  is absent, and the early guard only aborts when **both** backends are missing.
  `extraction_method` records `mobi-python`; like Calibre output it carries no page anchors. [infra]

## [1.6.1] — 2026-06-24

Repository / packaging / docs release. Every entry is `[infra]` (generator-only): it does
**not** alter generated skill content, so `book-to-skill upgrade` applies nothing to existing
skills — they remain current.

### Added
- **`uv`-installable package.** `pyproject.toml` gained a `[project]` table, a `hatchling`
  build backend, and optional-dependency extras (`pdf`, `epub`, `docx`, `html`, `rtf`,
  `docling`, `rich`, `all`, `dev`). `uv sync` now works and a `book-extract` console script
  exposes the extractor/upgrader (`bookextract.cli:main`). The version stays sourced from
  `scripts/bookextract/__init__.py`. The install-free `/book-to-skill` slash command and the
  direct `python3 scripts/extract.py` path are unchanged. [infra]
- **GitHub Actions CI** (`.github/workflows/ci.yml`): `uv sync` + the quality gate
  (pytest · ruff · mypy required; lizard · xenon informational) on Python 3.10–3.12. [infra]
- **Public, copyright-safe demo** under `examples/`: an original CC0 guide
  (`demo-input/mini-python-code-review-guide.md`) and the full skill generated from it
  (`demo-output/python-code-review-skill/` — SKILL.md, chapters, glossary/patterns/cheatsheet/
  cues, a 5-rule `review-rules.md`, provenance manifest, and archived `.source/`). Built via the
  real `book-extract`; every cited quote is grep-verified against `.source/full_text.txt`. (#14) [infra]
- **`ROADMAP.md`** anchored to the real version line and the open issues, and **`RELEASE.md`**
  with a release checklist. [infra]
- README: a "Strawberry Code edition" / "Differences from upstream" section, `uv` Installation &
  Usage, an end-to-end "Example workflow", a "Try the demo" pointer, and a "Copyright and source
  material" safety section. [infra]

### Changed
- `.gitignore` now excludes source material and derived artifacts (`.source/`, `*.pdf`,
  `*.epub`, `*.mobi`, `*.azw3`, `*.djvu`, `generated/`, `.local/`, `private-books/`,
  `private-skills/`) to avoid accidentally committing copyrighted inputs or derived skills;
  `uv.lock` is intentionally tracked, with an exception so the CC0 demo's `.source/` stays tracked. [infra]

## [1.6.0] — 2026-06-22

### Added
- Diagram/figure capture: layout-aware (Docling/technical) extraction now records each
  **captioned** figure — caption + physical page + best-effort kind — into a `figures.json`
  sidecar instead of discarding all non-text content, and the generator emits a `figures.md`
  artifact summarizing each as a described mental model: `### <caption verbatim> [Ch N]` + a
  1–2 line "what this diagram asserts" gloss. Caption is verbatim from the captured data; the
  summary is the model's, never quoted as the book. No image bytes, no ASCII recreation —
  the skill stays text-only. Gated: text-mode/EPUB or no detectable figures → no file, a Scope
  & Limits note instead. Figures come from extraction, so an existing skill gains them by a
  technical re-extract. (#8) [regenerate; steps 8 + re-extract for figures.json]
- Figure capture infrastructure: `DoclingExtractor` walks the document model's `pictures`
  (`caption_text` + provenance page), the chain surfaces them on `ChainResult.figures`, and the
  extractor writes `figures.json` + a `figure_count` in `metadata.json`. [infra]

## [1.5.0] — 2026-06-22

### Added
- Executable scaffolds: buildable technical-book skills emit a `templates/` directory —
  `README.md` (what it scaffolds + a "starting point, not production" banner),
  `structure.md` (the prescribed dir/file layout as an annotated tree, each node `[Ch N]`),
  `checklist.md` (the book's build procedure as an ordered `- [ ]` list, each step `[Ch N]`),
  and optional skeleton dirs with `.gitkeep` markers. Skeleton + checklist only — **no
  runnable starter code** (it rots and can be subtly wrong); every node/step carries a
  chapter citation or is left out. Gated on the book prescribing a concrete buildable
  structure/method (conceptual/narrative books skip it). Derived from the captured chapters
  — needs no source re-read; model-backed (no mechanical transform), so an existing skill
  gains it by regeneration. Manifest records `scaffolded` + `template_count`.
  (#4) [additive; new dir templates/]

## [1.4.0] — 2026-06-22

### Added
- Personalize examples to the user's stack: code/technical skills gain an "Adapting
  examples to your stack" capability in `SKILL.md` — on request ("the Specification
  pattern in TypeScript", "show this in Go") the skill re-renders a cited book example
  in the user's language/framework, preserving intent and keeping the original visible
  and cited (never presenting the translation as the book's text). Gated on the manifest
  `reviewable` flag (a book worth review rules has code examples to re-render); non-code
  books get `personalizable: false` and no change. Injected as a registered mechanical
  transform (no model, no source re-read) anchored before `## Scope & Limits`, and widens
  the `argument-hint`. (#9) [transform; SKILL.md capability + manifest personalizable]

## [1.3.0] — 2026-06-22

### Added
- Page-offset detection: the extractor records `page_offset` in `metadata.json` —
  the front-matter length recovered deterministically from the extracted text by
  anchoring on chapter-start pages that print their own folio (`physical_index −
  folio`, accepted only on a non-negative majority of ≥3 agreeing anchors). `null`
  when undetectable (Docling/EPUB, or no agreement). [infra]

### Changed
- Printed-folio citations: `[Ch N, p.PP]` page numbers are remapped from the physical
  PDF page index (form-feed count, the #3 basis) to the **printed book folio** by
  subtracting the detected `page_offset`; when the offset is undetectable the page is
  labelled `p.PP (pdf)` so it is never mistaken for a printed folio. The remap is a
  registered mechanical transform (no model, no source re-read) keyed on the archived
  `.source/` — the first `transform`-class migration. EPUB/chapter-only citations are
  unaffected. (#11) [transform; remap citations via detected offset]

## [1.2.0] — 2026-06-22

### Added
- Book-as-reviewer: code-checkable technical skills emit `review-rules.md` (per rule:
  id, concrete grep/glob detection heuristic, severity, confidence, chapter citation,
  fix) plus a `review <path>` procedure in SKILL.md that audits a codebase and emits a
  cited conformance report (violation/suggestion, file:line, `[Ch N]`, fix). Rules carry
  only chapter-level citations (the verbatim anti-pattern name, grep-verified — never a
  fabricated page). Non-code books skip the file and mark it unsupported. Derived from
  the already-captured anti-patterns/cues/patterns — needs no source re-read.
  (#1) [additive; new file review-rules.md]

## [1.1.0] — 2026-06-22

### Added
- Proactive activation cues: generated skills emit `cues.md` mapping a trigger
  (task keyword / code shape / file pattern) → framework → chapter, and fold the
  strongest triggers into the SKILL.md `description` so auto-discovery fires while
  the user works, not only on explicit questions. Derived from the already-captured
  frameworks — needs no source re-read. (#2) [additive; new file cues.md]

## [1.0.0] — 2026-06-22

First versioned release. Establishes the provenance + upgrade mechanism, so every
future change can be propagated to already-generated skills selectively.

### Added
- Provenance stamping: `generator_version` + `source_sha256` written into
  `metadata.json` by the extractor, and into each generated skill's
  `.book-to-skill.json` manifest (SKILL.md Step 9.5). [infra]
- Extraction archival: `full_text.txt` + `metadata.json` persisted to
  `<skill>/.source/` (SKILL.md Step 10) so upgrades regenerate without re-extracting. [infra]
- Upgrade flow: `book-to-skill upgrade <skill-dir>` (Mode 4) — manifest diff vs.
  this changelog, class-routed application, selective step re-run. [infra]
- Deterministic upgrade planner: `extract.py upgrade <skill-dir> [--dry-run]`
  parses this changelog, computes the semver delta vs. the skill manifest, verifies
  the archived `.source/`, groups changes by class, applies registered mechanical
  transforms, and bumps the manifest only when nothing model-backed remains. (#10) [infra]
- Provenance backfill: `extract.py upgrade <skill-dir> --backfill --source <doc> [--pin]`
  reconstructs a pre-provenance skill — extracts the original document into `.source/`
  and writes a manifest pinned at a baseline version so a later `upgrade` applies every
  content feature. Enables upgrading skills generated before manifests existed. [infra]
- Batch backfill: `extract.py backfill-batch <skills-dir> <archive-dir> [--apply]`
  fuzzy-matches every pre-provenance skill to its source by title-token overlap and
  backfills the confident matches (dry-run by default; ambiguous/unmatched are reported,
  never guessed). Pure matcher in `batch.py`, unit-tested. [infra]
- Verifiable grounding: every framework/principle/technique/anti-pattern carries
  `[Ch N, p.PP] "verbatim quote"`; chapter ref always, page when derivable;
  Step 8.5 grep-verifies every quote and reports citation coverage. (#3)
  [regenerate; steps 7,8,8.5,9]

<!--
Template for the next release:

## [1.1.0] — YYYY-MM-DD
### Added
- Proactive activation cues: cues.md mapping trigger → chapter/framework. (#2) [additive; steps 8]
- Flashcards export: flashcards.csv from glossary/patterns. (#5) [additive; steps 8]
### Changed
- <file-format reshape> [transform]
-->

[1.0.0]: https://github.com/strawberry-code/book-to-skill/releases/tag/v1.0.0
