<h1 align="center">📚 book-to-skill</h1>

<p align="center">
  <a href="https://raw.githubusercontent.com/strawberry-code/book-to-skill/master/assets/hero.mp4" title="Watch in HD">
    <img src="assets/hero.gif" alt="book-to-skill — the book reviews your code" width="720">
  </a>
</p>
<p align="center"><sub>▶ <a href="https://raw.githubusercontent.com/strawberry-code/book-to-skill/master/assets/hero.mp4">Watch in HD</a></sub></p>

<p align="center">
  <strong>Turn any technical book or document into a Claude Code skill — one that doesn't just explain the book, but reviews your code against it, scaffolds its approach, and re-renders its examples in your stack.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-Skill-blueviolet?style=for-the-badge" alt="Claude Code Skill">
  <img src="https://img.shields.io/badge/generator-v1.6.0-success?style=for-the-badge" alt="Generator v1.6.0">
  <img src="https://img.shields.io/badge/PDF%20%E2%80%A2%20EPUB%20%E2%80%A2%20DOCX%20%E2%80%A2%20MD%20%E2%80%A2%20HTML%20%E2%80%A2%20RTF%20%E2%80%A2%20MOBI-supported-green?style=for-the-badge" alt="Formats supported">
  <img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License">
</p>

<p align="center">
  <a href="#-why">Why</a> ·
  <a href="#-what-a-generated-skill-can-do">What a skill can do</a> ·
  <a href="#-what-it-generates">What it generates</a> ·
  <a href="#-how-to">How to</a> ·
  <a href="#-requirements">Requirements</a> ·
  <a href="#-provenance--upgrades">Provenance &amp; upgrades</a> ·
  <a href="#-how-it-works">How it works</a> ·
  <a href="#-faq">FAQ</a> ·
  <a href="#-install">Install</a> ·
  <a href="#-development">Development</a>
</p>

---

## 🤔 Why

You buy a great technical book. You read it once. Three months later you can't remember chapter 7 existed.

The usual workarounds don't help:
- 📄 "Let me just search the PDF" → you get a list of pages, not answers
- 🧠 "I'll ask Claude about this book" → it either hallucinates or says it doesn't have the content
- 📝 "I'll take notes as I read" → you end up with a 200-line doc you never open again

**book-to-skill turns the book into a structured skill Claude loads on demand** — and then *uses* while you work. Type `/your-book replication` and Claude reads the right chapter and answers from the actual content, citing it. No hallucination, no digging through PDFs.

---

## ⚡ What a generated skill can do

A skill is more than search — every answer is **grounded** in the source (chapter + verbatim quote, page folio for text PDFs), and code/technical books gain active capabilities:

| Capability | Invoke | What happens |
|---|---|---|
| **Study / reference** | `/my-book replication` · `/my-book ch05` | Reads the right chapter, answers from it, cites `[Ch N, p.PP] "…"`. |
| **Review your code** | `/my-book review ./src` | Audits a codebase against the book's rules → cited conformance report (violation/suggestion, `file:line`, `[Ch N]`, fix). *Code books only.* |
| **Adapt to your stack** | `/my-book "the Specification pattern in Go"` | Re-renders the book's example in your language/framework, preserving intent and citing the original. *Code books only.* |
| **Scaffold the approach** | `/my-book scaffold` | Lays out the book's project skeleton + a build checklist, each step `[Ch N]`. *Buildable books only.* |
| **See the diagrams** | `/my-book "what does Figure 3-1 show?"` | The book's figures captured as described mental models (caption + what it asserts). *Technical extraction only.* |

> Each capability is **gated**: a politics or economics book gets study/reference only; a code book also gets the reviewer, personalization and scaffold; a diagram-heavy technical PDF also gets figures. The skill never fabricates a capability it can't honestly support.

---

## 📦 What it generates

`/book-to-skill your-book.pdf` writes a full skill to `~/.claude/skills/<slug>/`:

| File | Purpose | When |
|------|---------|------|
| `SKILL.md` | Core mental models + chapter/topic index + capability sections | always (~4,000 tok) |
| `chapters/chNN-*.md` | One file per chapter, loaded on demand | always (~1,000 tok each) |
| `glossary.md` | Every key term, alphabetized with chapter refs | always |
| `patterns.md` | Techniques, algorithms and design patterns (when/how/trade-offs) | always |
| `cheatsheet.md` | Decision tables and quick-reference rules | always |
| `cues.md` | Activation cues: trigger → framework → chapter (drives proactive recall) | always |
| `review-rules.md` | Codebase audit rules for `review <path>` (grep/glob heuristics + citations) | code books |
| `figures.md` | Captured diagrams as described mental models | technical extraction w/ figures |
| `templates/` | Project skeleton + build checklist to scaffold the book's approach | buildable books |
| `.book-to-skill.json` | Provenance manifest (generator version, source hash, feature flags) | always |
| `.source/` | Archived `full_text.txt` + `metadata.json` (+ `figures.json`) for cheap upgrades | always |

**Chapter files load on demand** — they don't count against the skill budget until you ask about that topic. `.source/` and `.book-to-skill.json` are never loaded as skill content.

---

## 🚀 How to

### 1. Convert a book

```
/book-to-skill <path-to-document> [skill-name-slug]
```

It asks whether the book is **technical** (Docling: tables/code/figures) or **text-heavy** (pdftotext: instant, page folios), then extracts, generates, and writes the skill.

```bash
/book-to-skill ~/Downloads/designing-data-intensive-applications.pdf
/book-to-skill ~/books/clean-code.epub clean-code        # custom slug
```

Supported formats: **PDF, EPUB, DOCX, TXT, Markdown, reStructuredText, AsciiDoc, HTML, RTF, MOBI/AZW/AZW3**.

### 2. One-shot a technical PDF (`shred-book`)

A thin wrapper: forces **technical** mode, no questions, and archives the consumed PDF to `~/Downloads/shredded-books/`. It delegates to `book-to-skill` verbatim, so it always gets the latest features.

```bash
/shred-book ~/Downloads/some-technical-book.pdf [slug]
```

### 3. Use the skill

```bash
/my-book                              # load core mental models
/my-book replication                  # find + explain a topic, cited
/my-book ch05                         # dive into one chapter
/my-book review ./src                 # audit your code against the book   (code books)
/my-book "this pattern in TypeScript" # re-render an example in your stack (code books)
/my-book scaffold                     # lay out the book's project skeleton (buildable books)
/my-book "what does Figure 2-1 show?" # the book's diagrams                (technical extraction)
```

### 4. Keep skills current

```bash
python3 scripts/extract.py upgrade ~/.claude/skills/my-book --dry-run   # what's stale?
python3 scripts/extract.py upgrade ~/.claude/skills/my-book             # apply
```

See [Provenance & upgrades](#-provenance--upgrades).

---

## 🔧 Requirements

The extractor tries tools in order per format and uses the first available; if none is installed it tells you the exact command to run. Plain text, Markdown, reStructuredText and AsciiDoc need no extra deps.

**PDF — choose by book type:**

| Book type | Tool | Install | Speed | Extras |
|-----------|------|---------|-------|--------|
| Text-heavy (prose) | `pdftotext` (poppler) | `sudo apt install poppler-utils` | ⚡ instant | **page folios** (#11) |
| Text-heavy fallback | `pypdf` | `pip3 install pypdf` | ⚡ instant | — |
| Text-heavy fallback | `pdfminer.six` | `pip3 install pdfminer.six` | ⚡ instant | page folios |
| **Technical (code, tables, formulas)** | **`docling`** | `pip3 install docling` | ~1.5s/page | **tables, code, figures** (#8) |

> Text mode preserves form-feeds → citations carry the **printed page folio** (`[Ch N, p.PP]`). Technical (Docling) mode captures tables, code blocks and **figures**, but citations are chapter-level (`[Ch N]`).

**EPUB:** `ebooklib` + `beautifulsoup4` (`pip3 install ebooklib beautifulsoup4`, best) or the built-in stdlib `zipfile` reader (always available).

**Other formats:** DOCX → `python-docx`; HTML → `beautifulsoup4`; RTF → `striprtf`; MOBI/AZW/AZW3 → Calibre `ebook-convert` ([download](https://calibre-ebook.com/download)); each falls back to a stdlib path where possible.

**Optional — nicer CLI:** `pip3 install rich` adds a live progress bar (PDF pages / EPUB chapters) and a Docling spinner on a TTY. Silently skipped if absent.

---

## 🔁 Provenance & upgrades

Every generated skill records **how it was built** in `.book-to-skill.json` (generator version, source SHA-256, feature flags like `reviewable` / `scaffolded` / `figures_captured` / `page_offset`) and archives its extraction under `.source/`. This makes a skill a reproducible, upgradable artifact rather than a dead end.

When the generator gains a feature, [`CHANGELOG.md`](CHANGELOG.md) tags it with a **migration class**, and `extract.py upgrade` applies only what's needed:

| Class | Meaning | Cost |
|---|---|---|
| `transform` | rewrite an existing file deterministically (no model) | cheap |
| `additive` | new artifact derived from captured data (model, no source re-read) | medium |
| `regenerate` | needs the book re-read / re-extracted | high |

```bash
python3 scripts/extract.py upgrade <skill-dir> --dry-run   # plan: what changes, which class
python3 scripts/extract.py upgrade <skill-dir>             # apply transforms; bump the manifest
```

Skills generated before provenance existed can be **backfilled** (`upgrade … --backfill --source <doc>`) so future features still apply.

---

## ⚙️ How it works

```
 document (PDF/EPUB/DOCX/…)
        │
        ▼  "Technical or text-heavy?"
   scripts/extract.py --mode <technical|text>
        │   technical → Docling (tables + code + figures, ~1.5s/page)
        │   text      → pdftotext → pypdf → pdfminer (instant, page folios)
        │   EPUB      → ebooklib → stdlib zipfile
        ▼
   work dir: full_text.txt · metadata.json · figures.json (technical only)
        │
        ▼  Claude analyzes structure (title, author, chapters, ToC)
        │  · per-chapter summaries, grounded with [Ch N, p.PP] "verbatim"
        │  · glossary · patterns · cheatsheet · cues
        │  · review-rules (code) · figures (technical) · templates/ (buildable)
        │  · grounding self-check: every cited quote grep-verified
        ▼
   ~/.claude/skills/<slug>/  ✅  + .book-to-skill.json + .source/
   work dir                  🗑️  cleaned up
```

<details>
<summary>Design principles (click to expand)</summary>

1. **Density over completeness** — a 1,000-token summary beats a 10,000-token excerpt.
2. **Practitioner voice** — "Use X when Y", not "The book explains X".
3. **Front-loaded SKILL.md** — compaction keeps the first ~5,000 tokens; the most important content comes first.
4. **On-demand chapters** — the topic index tells Claude which file to read; chapters load only when needed.
5. **Grounded, never invented** — every framework/anti-pattern carries a chapter ref + verbatim quote, grep-verified; honesty gates skip capabilities the book can't support.

</details>

---

## ❓ FAQ

**"Can't I just dump the PDF into my Claude project context?"**
You can — but every conversation burns that budget upfront (~200K tokens for a 400-page book). A skill loads only the relevant chapter. More importantly: raw text is *retrieval*; a skill is *reasoning* over pre-extracted named frameworks, with the ability to review your code, scaffold, and personalize examples.

**"Isn't this just RAG?"**
RAG works at query time (chunk → embed → nearest vectors). book-to-skill works at compile time: one deep pass extracts the author's actual frameworks, names them, captures the anti-patterns, and turns them into *checkable rules*. RAG answers "here are chunks close to your query." A skill answers "here are the frameworks this author built, ready to reason with — and I'll audit your code against them." For searching 50+ books, RAG wins; for going deep on one and using it while you work, a skill wins.

**"Popular books are already in Claude's training data."**
That knowledge is compressed and averaged across the internet, and may hallucinate quotes or chapter locations. book-to-skill works from *your* copy — every framework name, anti-pattern and chapter number is grounded in the text you provided. It also shines for books Claude doesn't know: niche references, internal docs, recent or translated works.

**"NotebookLM handles multiple books better."**
True for "I have 80 books and want to search across all of them." book-to-skill is for going *deep* on one book and embedding its frameworks in your coding workflow — less library search, more "the author sitting next to you while you work."

---

## 📥 Install

Paste into a Claude Code session:

```
Install book-to-skill: https://raw.githubusercontent.com/strawberry-code/book-to-skill/master/SKILL.md
```

Or manually — the extractor is a package (`scripts/bookextract/`), so copy the **whole** `scripts/` directory:

```bash
git clone https://github.com/strawberry-code/book-to-skill /tmp/book-to-skill
mkdir -p ~/.claude/skills/book-to-skill
cp -r /tmp/book-to-skill/SKILL.md /tmp/book-to-skill/scripts ~/.claude/skills/book-to-skill/
```

Then: `/book-to-skill ~/path/to/your-book.pdf`

---

## 📁 Repository structure

```
book-to-skill/
├── SKILL.md                  # The generator: step-by-step generation + upgrade instructions
├── CHANGELOG.md              # Versioned features, each tagged with its migration class
├── scripts/
│   ├── extract.py            # Thin entrypoint (extract · upgrade · backfill subcommands)
│   └── bookextract/          # Extraction package (functional core + imperative shell)
│       ├── cli.py            # argparse + orchestration + mechanical upgrade transforms
│       ├── pipeline.py       # Chain-of-Responsibility runner; ChainResult (text + figures)
│       ├── extractors.py     # Extractor Protocol + adapters (pdftotext/pypdf/docling/…)
│       ├── formats.py        # FormatSpec table: extension → chain/count/deps + sniffing
│       ├── structure.py      # Chapter/ToC detection (pure)
│       ├── pageoffset.py     # Front-matter offset → printed folios; citation remap (#11)
│       ├── metadata.py       # metadata.json assembly (pure)
│       ├── upgrade.py        # Deterministic upgrade planner (manifest vs CHANGELOG) (#10)
│       ├── batch.py          # Fuzzy slug→source matcher for batch backfill
│       ├── progress.py       # Optional rich progress bar / spinner (TTY only)
│       ├── deps.py           # Optional-dependency discovery + install flow
│       └── types.py          # Mode literal, Figure, legal method names, error type, debug
├── tests/                    # 95 tests — extract · upgrade · pageoffset · personalize · figures · batch
├── .claude/skills/
│   └── shred-book/           # One-shot technical-PDF wrapper (delegates to book-to-skill)
├── docs/                     # Sphinx API docs (autodoc + Napoleon) → Read the Docs
├── pyproject.toml            # ruff / mypy / pytest config (quality gate)
└── .pre-commit-config.yaml   # ruff + mypy + lizard + xenon + pytest hooks
```

---

## 🛠️ Development

```bash
python3 -m pytest tests/ -q                       # 95 tests; fixtures built in-process
python3 scripts/extract.py --debug <file>         # see which extractor ran and why a fallback kicked in
```

**Quality gates** — the `bookextract` package holds a strict semantic-LOC / typing / complexity standard:

```bash
pip3 install ruff mypy lizard xenon pre-commit
pre-commit run --all-files                        # the whole gate

ruff check scripts/ tests/                        # lint (blind-except & magic-number bans)
mypy                                              # --strict type check
lizard scripts/bookextract -T nloc=25 -C 8 -a 4 --warnings_only   # NLOC≤25, cyclomatic≤8, args≤4
xenon --max-absolute B --max-average A scripts/bookextract        # complexity grade
```

Thresholds live in `pyproject.toml` and `.pre-commit-config.yaml`.

**Docs** — API reference is generated from docstrings (Sphinx autodoc + Napoleon):

```bash
pip3 install -r docs/requirements.txt
sphinx-build -b html -W docs docs/_build/html && open docs/_build/html/index.html
```

`.readthedocs.yaml` builds the same site (`fail_on_warning: true`); architecture overview in `docs/architecture.rst`.

---

## License

MIT
