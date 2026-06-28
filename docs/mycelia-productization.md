# Mycelia — from working prototype to a serious product

> Assessment written 2026-06-28, grounded in a hands-on scale test: two real books
> (*Coding Theory*, Neubauer et al., 355pp, `pdftotext`; *Computational Genomics with R*,
> Akalin, 463pp, `docling`) ingested into one OKF vault — **24 atomic notes**, cross-chapter
> **and** cross-book reconciliation, all checks green. This is what that test taught us about
> the gap between "it works" and "you'd trust it with hundreds of books."

## What is verified working (keep these)

- **Extraction is fully decoupled and reusable.** Both runs reused existing `.source/full_text.txt`
  unchanged; the generator never touched the extractor. This boundary is sound.
- **OKF format holds on real, messy input** — bundle-relative links, reserved `index.md`/`log.md`,
  `type`-required frontmatter. 38 files, **0 dangling links**.
- **Grounding works.** Every cited quote was verbatim-verifiable against the immutable `raw/` —
  **100% across both books**, including ligature-ridden `pdftotext` and paragraph-joined `docling`.
- **The deterministic linter is the real safety net** — now also enforcing **citation coverage**
  (24/24 atomic notes carry a chapter ref) and **reciprocal backlinks** (66+ links, 0 asymmetric).
- **Reconciliation converges when exercised.** `entropy` ended with two source citations
  (coding-theory + genomics) and the repetition code with two (Ch 1 + Ch 2) — **one canonical note
  per concept, multiple sources, zero duplicates.**

## The core gap

**The agent *is* the generation engine.** Every one of those 24 notes was hand-emitted by the model
following a prose recipe. That is fine for a proof and unacceptable for a product:

- It does not scale. 24 notes from ~16 pages → a 355-page book is **~400–600 notes**; a *library* is
  tens of thousands. One chat session cannot hold that (context compaction, drift, cost).
- It is non-deterministic. Two runs produce different note sets; coverage of the source is unmeasured.
- It is trust-based beyond what the linter checks. The linter validates *structure*; nothing validates
  that a note is atomic, faithful to its quote, or that the right concepts were captured.

**A serious product inverts the responsibility: the LLM emits *data* (validated against a schema),
code assembles *files and links*.** Everything below follows from that.

## Prioritized improvements

### P0 — correctness & scale foundations (without these it is not a product)

1. **Deterministic orchestration harness.** Chunk the book per section; call the model per-chunk with a
   **structured-output schema** (one JSON object per note: type, title, slug, description, aliases,
   body, edges, citations). Code validates each note, retries on schema/grounding failure, and writes
   files. The recipe (`MYCELIA.md`) becomes the *per-chunk prompt*, not the whole pipeline.
2. **Programmatic grounding, not eyeballed.** The verbatim-quote rule fights real text: `pdftotext`
   ligatures (`ﬁ`/`ﬂ`), en-dashes, math glyphs; `docling` joins paragraphs into one line. Build a
   **normalize-then-match** verifier (fold ligatures/whitespace for matching, store the original) that
   spans line breaks. Today the self-check has false negatives and the model wastes effort dodging
   glyphs. Citations (line → form-feed → folio via stored `page_offset`) must be **computed**, not read
   by eye from running headers as I had to here.
3. **Idempotent, resumable ingest.** Re-running today duplicates. Need per-source `sha256` skip
   (partly present), per-note provenance, a journal/checkpoint so a 600-note book resumes chapter by
   chapter, and a budget ceiling (hard token cap, per-chapter cost) surfaced before and during a run.
4. **Code-maintained backlinks.** The model declares edges; **code inserts the reciprocal `## Related`**
   and keeps the graph symmetric. Hand-authoring both sides (as done here, then verified by an
   ad-hoc script before it was folded into the linter) does not scale.

### P1 — the second-brain differentiators

5. **Reconciliation with an index, not per-note `grep` + memory.** It only merged `entropy` because the
   operator *remembered* it existed. Build a **concept index** (canonical id + aliases + embedding).
   Candidate retrieval = deterministic (cosine ≥ ~0.9); **LLM arbitration only on ambiguous candidates**;
   stable `canonicalId` so merges are idempotent. This is what catches `BSC`↔`binary symmetric channel`
   and `mutual information`↔`transinformation` without hand-authored aliases.
6. **Semantic QA pass (LLM-judge).** An independent verifier checks each note's body against its cited
   quote/source for **faithfulness** (no claims beyond the source) and atomicity, and flags over-reach.
   Structure-valid ≠ correct.
7. **Contradiction detection across merged sources.** We hit 0 contradictions (untested). When book A
   and book B disagree on a merged concept, detect it at merge time → `contested: true` + a
   `reports/contradictions.md` dashboard. Flag, never silently overwrite.

### P2 — library-scale hardening

8. **Completeness measurement.** Compare captured notes against an extracted glossary/index of the
   source to report *what was missed*; dedup near-duplicate notes. Coverage of the source is currently
   unknown.
9. **Concurrency control on the shared concept layer.** Parallel workers ingesting different books will
   race on the same canonical note (two books merging `entropy` at once). Needs transactional/locked
   writes.
10. **Extraction standardization for provenance.** `docling` drops page anchors (chapter-only citations);
    `pdftotext` keeps them. A serious product decides this per provenance requirement (and runs
    `page_offset` detection in extraction, storing it) rather than inheriting whatever an old run used.

## Target architecture (sketch)

```
 source.pdf ──extract (unchanged)──▶ raw/{full_text.txt, metadata.json + page_offset}
                                          │
                    ┌─────────────────────┴───────────────────────┐
                    ▼  orchestrator (deterministic, resumable, budgeted)
        per-section: prompt LLM ──▶ Note JSON (schema) ──▶ validate:
                                       • grounding (normalize+match vs raw)
                                       • atomicity / faithfulness (LLM-judge)
                                       • reconcile vs concept index (embed + arbitrate)
                    ▼
            code assembles: files, reciprocal links, index.md/log.md, manifest
                    ▼
            okf_lint (hard gate: type · dangling · coverage · reciprocity · log)
                    ▼
            vault/  (idempotent; journal enables resume)
```

The current `MYCELIA.md` recipe is the seed of the per-section prompt; `okf_lint` is already the gate;
`scripts/bookextract/` is the extractor. The missing middle is the **orchestrator** — that is the
product.

## Suggested build order

1. **P0.1 + P0.2** (orchestrator skeleton + programmatic grounding) on a single book end-to-end —
   replaces hand-emission, makes a full 355-page run actually feasible and measurable.
2. **P0.3 + P0.4** (idempotency/resume + code-maintained links).
3. **P1.5** (index-backed reconciliation) — the second-brain payoff, now testable against a real
   multi-book corpus.
4. **P1.6/P1.7, then P2** as the corpus grows.
