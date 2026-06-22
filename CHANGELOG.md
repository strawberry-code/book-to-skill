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
