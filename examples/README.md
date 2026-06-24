# Demo: book-to-skill, end to end

A small, **fully redistributable** example of what `book-to-skill` produces — no copyrighted
material. Use it to see the shape and grounding of a generated skill before running the tool
on your own book.

```
examples/
├── demo-input/
│   └── mini-python-code-review-guide.md      # the source "book" (original, CC0)
└── demo-output/
    └── python-code-review-skill/             # the generated skill
        ├── SKILL.md                          # core frameworks + indexes + reviewer
        ├── chapters/ch01..ch03-*.md          # on-demand chapter summaries
        ├── glossary.md · patterns.md · cheatsheet.md · cues.md
        ├── review-rules.md                   # 5 grep-checkable audit rules
        ├── .book-to-skill.json               # provenance manifest
        └── .source/                          # archived extraction (full_text.txt + metadata.json)
```

## What the demo input is

[`demo-input/mini-python-code-review-guide.md`](demo-input/mini-python-code-review-guide.md) is an
**original** three-chapter guide to Python code review, written for this demo and dedicated to the
public domain (**CC0 1.0**). It is intentionally tiny (~1,100 words) so the generated skill is easy to
read in full. It contains named frameworks (Review for Intent, the Reviewer's Charter, Guard Clause,
Small Diffs) and concrete, grep-detectable anti-patterns (SQL string-building, `eval`/`exec` on input,
bare `except`, `assert`-for-validation, mutable default arguments) — which is what lets the generated
skill act as a code reviewer.

## How to run the tool

Generation itself is the **`/book-to-skill` slash command** in an agent host (Claude Code): the agent
reads the repo's [`SKILL.md`](../SKILL.md) generator and writes the skill into `~/.claude/skills/<slug>/`.

```text
/book-to-skill examples/demo-input/mini-python-code-review-guide.md python-code-review-skill
```

The deterministic, model-free steps are the `book-extract` CLI (no skill generation — just extraction
and upgrades). The demo output's `.source/` was produced exactly this way:

```bash
uv sync --extra pdf
uv run book-extract examples/demo-input/mini-python-code-review-guide.md --mode text
# → full_text.txt + metadata.json in $BOOK_SKILL_WORKDIR (default: $TMPDIR/book_skill_work)

# The provenance manifest is valid, so the upgrade flow runs against the demo skill:
uv run book-extract upgrade examples/demo-output/python-code-review-skill --dry-run
# → "Skill is already current (v1.6.0). Nothing to do."
```

> The `.source/metadata.json` here has had its absolute `source_file`/`output_text` paths rewritten to
> repo-relative ones (a real run records absolute local paths). `source_sha256` is the real SHA-256 of
> the demo input — re-running extraction reproduces it.

## What output to expect

A skill folder where **every framework, mental model and anti-pattern is grounded** in the source: a
`[Ch N]` chapter reference plus a verbatim quote that exists in `.source/full_text.txt` (each quote in
this demo was grep-verified — book-to-skill's "grounding self-check"). Highlights:

- **`SKILL.md`** — the ~4k-token core: frameworks toolkit, a Chapter/Topic index, and the
  `review <path>` reviewer protocol.
- **`review-rules.md`** — five rules (`PY-SQLI-01`, `PY-EVAL-02`, `PY-EXCEPT-03`, `PY-ASSERT-04`,
  `PY-MUTDEF-05`), each with `detect.grep` patterns, `exclude.glob`, confidence, a `[Ch N]` source, and a fix.
- **`.book-to-skill.json`** — `generator_version`, `source_sha256`, `reviewable: true`,
  `review_rule_count: 5`, feature flags — what makes the skill a reproducible, upgradable artifact.

## How an agent uses the generated skill

Once the folder is in the host's skills directory, the agent loads `SKILL.md` on demand and:

- **Explains concepts** — "what's the Reviewer's Charter?" → reads `ch01`, answers with the cited quote.
- **Adapts examples** — "the parameterized-query rule in `asyncpg`" → re-renders the `ch02` example in
  your stack, keeping the original citation visible.
- **Reviews your code** — `review ./src` → resolves each rule's globs, greps `detect.grep`, confirms
  hits by reading ±3 lines, and emits a conformance report with `file:line`, the `[Ch N]` citation, and a fix.
- **Generates checklists / cheatsheets** — pulls the review order and dangerous-shapes table from
  `cheatsheet.md`.

It will **not** scaffold a project here: the guide prescribes no buildable structure, so no `templates/`
was generated — the skill says so in its *Scope & Limits*. That honesty gating is the point: a skill
only claims capabilities its source actually supports.

## Copyright

This demo uses only original CC0 content. Do **not** add copyrighted books, their extracted text, or
skills derived from protected works to this directory — see the repository README →
[Copyright and source material](../README.md#-copyright-and-source-material).
