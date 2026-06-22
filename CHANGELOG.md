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
