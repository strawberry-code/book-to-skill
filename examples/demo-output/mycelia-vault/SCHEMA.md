---
type: Schema
title: Vault Schema
description: Editorial conventions for this OKF vault — note types, frontmatter, linking, provenance, dedup.
timestamp: 2026-06-28T00:00:00Z
---

# Vault Schema

OKF v0.1 bundle. One concept per file; the file path is the concept's identity.

## Note types (frontmatter `type`)
Concept · Framework · Principle · Entity · Method · AntiPattern · Source · MOC

## Frontmatter
- **Required (OKF):** `type`.
- **Recommended (OKF):** `title`, `description`, `tags`, `timestamp` (ISO-8601).
- **Governance extensions (Mycelia; a pure-OKF consumer ignores these):**
  - `aliases` — synonyms; reconciliation resolves these to this note's path.
  - `confidence` (`low`/`medium`/`high`) · `status` (`established`/`contested`/`insufficient`) · `contested` (`true`/`false`).

## Links
Standard Markdown, **bundle-relative absolute** so they survive moves — an absolute target such as
`/concepts/code-review.md` written as a Markdown link. No wikilinks. Each link has a reciprocal entry in
the target note's `## Related` section.

## Provenance
- Each source book is a `type: Source` note under `references/`.
- Each note cites its sources in a numbered body `# Citations` section: a grounded
  `[Ch N, p.PP] "verbatim quote"` plus a bundle-relative link to the source note. A concept seen in
  multiple books accrues multiple citations on ONE note.

## Reserved files
- `index.md` — directory listing for progressive disclosure; carries NO frontmatter (the bundle root
  `index.md` may carry only `okf_version`).
- `log.md` — change history; ISO-8601 date headings, newest-first.

## Dedup rule
Check-before-create: normalize (NFKC + casefold), look up slug + aliases, merge into the canonical note
rather than duplicating. Conflicts across sources set `contested: true` and a `## Contradictions`
section (flag, do not resolve).
