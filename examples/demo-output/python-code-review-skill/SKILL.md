---
name: python-code-review-skill
description: "Knowledge base from \"The Mini Guide to Python Code Review\" by Strawberry Code (original demo content). Use when applying its frameworks for reviewing Python — review-for-intent, the Reviewer's Charter, SQL/eval/except/assert security shapes, mutable defaults, guard clauses, small diffs — studying the guide, or referencing its concepts. Proactively recall when reviewing a PR/diff, building SQL strings, using eval/exec on input, writing a bare except, or defining a function with a mutable default argument."
allowed-tools:
  - Read
  - Grep
  - Glob
argument-hint: [topic, framework name, chapter number, "review <path>", or "<topic> in <stack>"]
---

# The Mini Guide to Python Code Review
**Author**: Strawberry Code (original demo content) | **Pages**: ~6 | **Chapters**: 3 | **Generated**: 2026-06-24 | **book-to-skill**: v1.6.0

> **This is a demonstration skill.** It was generated from a small, original, CC0-licensed
> guide bundled with book-to-skill (see `examples/demo-input/`). It shows the shape and
> grounding of a real generated skill without using any copyrighted material.

## How to Use This Skill

- **Without arguments** — load the core frameworks below for reference.
- **With a topic** — ask about `guard clause`, `small diffs`, `sql injection`; I find and read the relevant chapter.
- **With a chapter** — ask for `ch02`; I load that specific chapter file.
- **Review** — `review <path>`: audit a Python codebase against this guide's rules (see below).
- **In your stack** — ask for a concept "in <your stack>"; I re-render the example while citing the original.
- **Browse** — ask "what chapters do you have?" for the full index.

When you ask about a topic not covered in Core Frameworks below, I will read the relevant
chapter file before answering.

## Reviewing a codebase (`review <path>`)

When asked to `review <path>` (or "audit/check this repo against the guide"):

1. **Load rules.** Read `review-rules.md`.
2. **Enumerate.** For each rule, resolve `scope.glob` against `<path>` with Glob; drop anything matching `exclude.glob` (tests, fixtures, examples, generated, migrations, vendored). Zero in-scope files → mark *not applicable*.
3. **Find candidates.** Grep the rule's `detect.grep` patterns within in-scope files; collect `file:line` hits.
4. **Confirm each hit.** Read the hit ±3 lines; apply `detect.context`, `exclude.when`, and `detect.requires`. Failing any → discard.
5. **Classify.** *violation* only if `severity=violation` ∧ `confidence=high` ∧ requirements met ∧ not excluded; otherwise *suggestion*. When unsure, downgrade — never fabricate.
6. **Report** (format below): every finding carries `file:line`, rule id+name, the `[Ch N]` citation, and a one-line fix.
7. **Honesty footer.** List rules with no in-scope files and any guidance that isn't machine-checkable.

Report format:
```markdown
# Conformance report — <path>
Reviewed against: python-code-review-skill (The Mini Guide to Python Code Review)
Files scanned: <N> | Rules applied: <A> of 5

## Violations
### PY-SQLI-01 — SQL built by string concatenation  [Ch 2] "SQL built by string concatenation"
- <file>:<line>  `<offending code>`
  Fix: use a parameterized query; bind user values.

## Suggestions
### PY-MUTDEF-05 — mutable default argument  [Ch 3] "Mutable default argument"  (confidence: high)
- <file>:<line>  `def f(x=[])`
  Fix: default to None and build the list inside.

## Not audited
- Rules with no in-scope files: <ids>
- Guidance not machine-checkable: review-for-intent, the Reviewer's Charter (human judgment)
```

---

## Core Frameworks & Mental Models

- **Review for Intent, Not Style** — read the whole diff for *what changed and why* before any line-level comment; let the formatter own style. [Ch 1] "review for intent first, let the formatter handle style."
- **The Reviewer's Charter** — answer, in order: correct? safe? clear? small enough to understand? [Ch 1] "Is it correct? Is it safe? Is it clear? Is it small enough to understand?"
- **The dangerous shapes (security)** — learn four shapes by sight: SQL built by concatenation, `eval`/`exec` on input, bare except, and `assert` used for validation. [Ch 2] "Treat `eval`/`exec` on request data as remote code execution, because that is exactly what it is."
- **Parameterized queries** — never splice input into SQL; bind it. [Ch 2] "Never concatenate or f-string user input into SQL; pass it as a bound parameter."
- **Guard Clause** — return early on exceptional cases so the success path stays flat. [Ch 3] "Return early on the exceptional cases so the main path stays flat and at the top."
- **Sentinel default** — a mutable default is shared state; default to `None`. [Ch 3] "A mutable default argument is shared state wearing the costume of a fresh value."
- **Small Diffs** — prefer many small, focused changes; a small diff gets a real review, a large one a rubber stamp. [Ch 3] "Prefer many small, focused diffs over one large one"

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-the-code-review-mindset.md) | The Code Review Mindset | Review for Intent, Reviewer's Charter |
| [ch02](chapters/ch02-security-anti-patterns.md) | Security Anti-Patterns in Python | SQL concat, eval/exec, bare except, assert-validation |
| [ch03](chapters/ch03-maintainability-patterns.md) | Maintainability Patterns | Guard Clause, Sentinel default, Small Diffs |

## Topic Index

- **assert validation** → ch02
- **bare except** → ch02
- **eval / exec / RCE** → ch02
- **guard clause** → ch03
- **intent vs style** → ch01
- **mutable default argument** → ch03
- **reviewer's charter** → ch01
- **small diffs** → ch01, ch03
- **sql injection** → ch02

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and patterns with citations
- [cheatsheet.md](cheatsheet.md) — the review order + dangerous-shapes table
- [cues.md](cues.md) — activation cues: trigger → framework → chapter
- [review-rules.md](review-rules.md) — codebase audit rules for `review <path>`

---

## Adapting examples to your stack

Ask for any concept "in <your stack>" — e.g. "the parameterized-query rule in asyncpg",
"guard clauses in TypeScript". I re-express the guide's example in your language/framework
while preserving its intent, and I keep the original:

1. Read the cited example from the relevant `chapters/chNN-*.md` (with its `[Ch N]` citation).
2. Re-render it in your stack idiomatically — same behavior and invariants, your syntax.
3. Show the original (or its citation) alongside, so the mapping is auditable.

---

## Scope & Limits

- **Demo skill.** Built from a deliberately tiny original guide; it is illustrative, not an exhaustive code-review reference.
- **No figures.** Text-mode extraction captured no diagrams; diagrams are not represented.
- **No `templates/` scaffold.** The guide prescribes no buildable project structure, so no scaffold is generated.
- **Human-judgment rules are not machine-checkable.** "Review for intent" and the Reviewer's Charter guide a human reviewer; `review <path>` only audits the five concrete, grep-detectable rules in `review-rules.md`.
