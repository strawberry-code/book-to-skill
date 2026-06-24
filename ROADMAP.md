# Roadmap

This roadmap reflects the **actual** state of the project. `book-to-skill` is already a
mature generator (**v1.6.0**) — this is not a pre-1.0 plan. The version line is sourced
from `scripts/bookextract/__init__.py`; shipped features are recorded in
[`CHANGELOG.md`](CHANGELOG.md), each tagged with its upgrade *migration class*.

Open work is tracked as [GitHub issues](https://github.com/strawberry-code/book-to-skill/issues);
milestones below link to them where they exist.

## v1.6.0 — current

Shipped (see CHANGELOG for the full list and migration classes):

- Single-document → Claude Code skill generation across PDF / EPUB / DOCX / TXT / Markdown /
  reStructuredText / AsciiDoc / HTML / RTF / MOBI/AZW/AZW3.
- Capability gating: study/reference always; **code review**, **stack personalization** and
  **scaffold** for code/buildable books; **figures** for technical extraction.
- Grounded answers — chapter + verbatim quote (page folio for text PDFs), grep-verified.
- Provenance manifest (`.book-to-skill.json`) + deterministic `upgrade` flow + `.source/` archive.
- Diagram/figure capture (#8); printed page folios (#11).
- Strict quality gate (ruff · mypy · lizard · xenon) and Sphinx API docs.

## v1.7.0 — next

Adoption & breadth (this release line):

- **`uv`-first developer workflow** — installable package, `book-extract` console script,
  optional-dependency extras, CI. *(landing now; see CHANGELOG → Unreleased)*
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

- **Multi-book domain libraries** — fuse N related books into one skill with cross-linked
  frameworks (e.g. several DDD books → one "domain modeling" skill).
  ([#6](https://github.com/strawberry-code/book-to-skill/issues/6))
- Cross-document references and a shared glossary across a domain library *(planned)*.

> Items marked *(planned)* are not yet implemented. The dated, shipped record of truth is
> always [`CHANGELOG.md`](CHANGELOG.md).
