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

---

## Execution plan A–E (2026-06-28)

P0 (orchestrator + programmatic grounding) and the deterministic slice of P1 (acronym/plural
reconciliation) have shipped and were proven end-to-end on the real *Coding Theory* book (lint
green, idempotent, live acronym fold, ligature/line-break grounding). The assessment of what still
blocks "NASA-level" reliability is: the deterministic skeleton is production-grade, but the part that
determines vault *quality* — knowledge extraction — is still a manual, unverified, non-deterministic
step with no faithfulness check, no coverage guarantee, and no eval harness. The plan below closes
that, ordered so quality is **measurable before it is scaled**.

**Headless verified**: `claude -p --model opus --output-format json` runs on `claude-opus-4-8`
(smoke-tested). Caveats to absorb: ~200K context and a ~64K cached-prefix overhead per cold call
(≈$0.67 for a trivial call) → prompt-prefix caching and a cost model are load-bearing, not optional.

Cross-cutting constraints: copyrighted gold/raw stay out of the repo (CC0 synthetic fixture in repo);
pure core + thin CLI; frozen dataclasses; ruff/mypy strict, complexity ≤8; zero new deps except the
D2 embedding fork.

- **Fase A — the ruler: eval harness + gold standard** *(gap: no metrics)*. `eval.py` (pure) +
  `book-extract eval <bundle> --gold <gold.json>`: concept recall/precision, link recall, fact-anchor
  coverage, with a faithfulness-rate hook filled by B1. *Success*: reproducible metrics on the CC0
  fixture; a private baseline on the real book. **Everything else is measured against this.**
- **Fase B — quality gates**. *B2 chapter check* (pure: cited quote's physical line must fall in a
  chunk whose chapter == `citation.chapter`). *B1 semantic QA* (LLM judges body⊨cited-quote;
  unsupported = gate; reuses C's runner). *B3 coverage critic* (LLM lists concepts present per chunk;
  diff vs emitted → loop-until-dry). *Success*: injected wrong-chapter/unfaithful notes are caught;
  recall improves on the gold. **Status (B1 shipped & validated)**: `qa.py` + `book-extract verify`
  judges each note's body against its cited quotes, batched per call. On 12 real headless notes:
  faithfulness 75% (9 supported, 3 overreach, 0 unsupported) at $0.55 (~$0.046/note batched,
  ≈$2.3/51-note book). The 3 overreach findings were genuine semantic defects (a misstated coding
  theorem, an invented application list, a definition conflated with the decision region) that lint
  and grounding cannot see. B2 (low value, heuristic chapter map) deferred.
  **Status (B3 shipped & validated)**: `cover.py` + `book-extract cover` — loop-until-dry critic
  that re-reads each chunk with its extracted slugs in hand and appends only the missing concepts.
  On the BSC region, recall rose **67% (manual) → 83% (build) → 92% (after cover)**; the bundle grew
  51 → 82 atomic notes, lint green. B3 surfaced two real robustness bugs, both fixed: `validate_note`
  now canonicalizes the note `type` case-insensitively (`concept`→`Concept`), and `assemble` is now
  resilient — an ungroundable citation or a fully-uncited note is dropped and reported (`log.md` +
  `.mycelia.json` `dropped`) instead of aborting the whole bundle (2 citations + 1 note dropped on
  this run).
- **Fase C — headless orchestration** *(gap #1, now in-scope: Opus headless confirmed)*. *C1 runner*
  drives `claude -p --model opus --output-format json` per pending chunk → `validate_note` → journal
  (resume/idempotent); in-session path stays as fallback on the same Note-JSON contract. *C2*
  prefix caching + concurrency cap + budget. *Success*: full book built unattended, lint green,
  resumable after kill; a documented cost-per-book. **Status (C1 shipped & validated)**: real
  headless runs on the *Coding Theory* book produced 18 and 35 notes for two chunks (lint green,
  100% citation coverage) at ≈$0.92 and $1.12 → **~$1/chunk, ≈$18–20 for an 18-chunk book**.
  On the BSC region (same gold as the manual baseline) headless recall was **83% vs 67% manual** —
  more exhaustive, not just unattended. C2 (prefix-cache optimization, concurrency, budget cap) is
  the remaining polish.
- **Fase D — deep reconciliation & multi-book** *(gaps: fragmentation, single-book)*. *D1*
  multi-source assemble (cross-book citations on shared canonical notes). *D2* embedding
  reconciliation for semantic/cross-lingual synonyms — **deps fork** (local sentence-transformers /
  API / extended-deterministic), with a no-false-merge guard. *Success*: a shared concept accrues
  citations from two books; a "germany/deutschland"-class fold with zero false-merge regression.
- **Fase E — upstream extraction quality** *(gap: noisy source)*. Docling/technical mode for
  math/tables/figures; cleaner raw; surfaced extraction confidence. *Success*: a formula/table-heavy
  chunk yields fewer grounding failures than pdftotext, measured by A.

Dependency order: `A` → `B2 ‖ C1` → `B1, B3` (use C) → **re-measure with A** → `D` → `E`.
