---
name: book-to-skill
description: "Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW with Calibre) into structured agent skills, extracting frameworks, mental models, principles, techniques, and anti-patterns. Use when the user wants to study a document through Amp or Claude Code, apply an author's frameworks while working, or build a reusable knowledge base from a file."
compatibility: "Amp skill directories (.agents/skills, ~/.config/agents/skills, ~/.config/amp/skills) and Claude Code skill directories (~/.claude/skills)."
allowed-tools:
  - shell_command
  - Read
  - Write
  - Glob
  - Grep
argument-hint: <path-to-document> [skill-name-slug]
---

# Book-to-Skill Converter

Transform written knowledge into actionable agent skills by extracting structure — not producing summaries.

## Philosophy

Books contain crystallized expertise: frameworks, principles, and techniques that took years to develop. This skill extracts that knowledge into a format Amp, Claude Code, or another compatible agent can leverage repeatedly.

**Extract structure, not summaries.** A skill isn't a book report. It's a toolkit of:
- Named frameworks (mental models with clear application)
- Actionable principles (rules that guide decisions)
- Techniques (step-by-step methods)
- Anti-patterns (what to avoid and why)
- Voice calibration (how the author thinks and communicates)

**Preserve the author's precision.** Frameworks often have specific names for reasons. "The 5 Whys" isn't interchangeable with "ask why multiple times." Capture the exact formulation.

**Layer depth appropriately.** Simple books → simple skills. Complex books with 10+ frameworks → skills with reference files and on-demand chapters.

---

## Modes of Operation

Three paths available. Route based on what the user asks:

### 1. Full Conversion (Default)
**Trigger:** User provides a supported document path without special instructions
**Action:** Run all steps below (Steps 0–9)
**Output:** Complete skill with SKILL.md, chapters/, glossary, patterns, cheatsheet

### 2. Analyze Only
**Trigger:** User says "analyze", "just extract", or "I want to review before generating"
**Action:** Run Steps 0–3, then produce a structured extraction report (frameworks, principles, techniques found). Stop — do NOT generate skill files.
**Output:** Analysis report for user review

### 3. Generate from Prior Analysis
**Trigger:** User has existing analysis notes or previously ran analyze-only
**Action:** Skip Steps 0–3, use the provided analysis as input, run Steps 4–9
**Output:** Skill files from the provided analysis

### 4. Upgrade an Existing Skill
**Trigger:** User runs `book-to-skill upgrade <skill-dir>`, or asks to bring a previously generated skill up to the current generator version
**Action:** Run the Upgrade flow (see "Upgrading generated skills" below). Read the skill's `.book-to-skill.json` manifest, diff its `generator_version` against the current one via `CHANGELOG.md`, and apply only the changes that apply — re-running source-dependent steps over the skill's archived `.source/full_text.txt`.
**Output:** The same skill, updated in place, with a bumped manifest. No re-extraction; source-dependent regeneration only for the steps that changed.

---

## Skill Locations

This converter can run from multiple skill systems. When looking for this converter's helper script or writing the generated book skill, prefer these locations in order:

1. Amp project-local skills: `.agents/skills/`
2. Amp global skills: `~/.config/agents/skills/`
3. Amp legacy global skills: `~/.config/amp/skills/`
4. Claude Code skills: `~/.claude/skills/`

Generated skills should default to `~/.config/agents/skills/` for Amp unless the user asks for project-local or Claude Code output.

---

## Step 0 — Out-of-scope check

If the argument is NOT a path to a supported document file, stop and respond:
> "book-to-skill requires a supported document path. Usage: `book-to-skill /path/to/book.pdf [skill-name]`, `book-to-skill /path/to/book.epub [skill-name]`, or another supported format such as `.docx`, `.md`, `.txt`, `.html`, `.rtf`, `.mobi`, or `.azw3`."

Throughout the workflow, treat the first argument as `BOOK_PATH` and the optional second argument as `SKILL_NAME`.

---

## Step 1 — Validate input

```bash
test -f "$BOOK_PATH" && echo "FILE_OK" || echo "FILE_NOT_FOUND: $BOOK_PATH"
case "${BOOK_PATH##*.}" in
  pdf|PDF|epub|EPUB|docx|DOCX|txt|TXT|md|MD|markdown|MARKDOWN|rst|RST|adoc|ADOC|asciidoc|ASCIIDOC|html|HTML|htm|HTM|rtf|RTF|mobi|MOBI|azw|AZW|azw3|AZW3) echo "FORMAT_OK" ;;
  *) echo "FORMAT_UNKNOWN" ;;
esac
```

Check the file extension (`.pdf`, `.epub`, `.docx`, `.txt`, `.md`, `.markdown`, `.rst`, `.adoc`, `.html`, `.htm`, `.rtf`, `.mobi`, `.azw`, `.azw3`) or magic bytes (`%PDF` or `PK` zip header for EPUB/DOCX).

If the file is not found or the format is not supported, stop with a clear error message listing supported formats.

---

## Step 1.5 — Identify book type

Before extracting, ask the user:

> "What kind of content does this book have? This helps me choose the best extraction method.
>
> 1. **Technical** — has code blocks, tables, formulas, diagrams (e.g. programming books, academic papers, architecture guides)
> 2. **Text-heavy** — mostly prose, few or no tables/code (e.g. management, productivity, narrative non-fiction)
> 3. **Not sure** — I'll use the fast method and warn you if quality seems limited"

Store the answer as `BOOK_TYPE`:
- Option 1 → `BOOK_TYPE=technical`
- Option 2 → `BOOK_TYPE=text`
- Option 3 → `BOOK_TYPE=text`

**If `BOOK_TYPE=technical`**, inform the user before proceeding:
> "📐 Technical mode selected — using Docling for structure-aware extraction (tables, code blocks, formulas preserved as markdown). This takes ~1.5s per page, so expect a few minutes for longer books. Starting now…"

**If `BOOK_TYPE=text`**, inform:
> "📄 Text mode selected — using the fastest suitable extractor for this file type. Plain text/Markdown/HTML are usually ready in seconds; PDFs use pdftotext when available."

---

## Step 2 — Extract text from the source document

Run the extraction script, passing the book type:

```bash
SCRIPT_PATH=""
for candidate in \
  ".agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/amp/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.claude/skills/book-to-skill/scripts/extract.py"
do
  if [ -f "$candidate" ]; then
    SCRIPT_PATH="$candidate"
    break
  fi
done

if [ -z "$SCRIPT_PATH" ]; then
  echo "Could not find scripts/extract.py for book-to-skill" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" "$SCRIPT_PATH" "$BOOK_PATH" --mode <BOOK_TYPE> --install-missing ask
```

Before extraction, the script checks optional Python packages needed for the detected format. If a better extractor is missing, it prompts the user with the available fallback, for example:

> "DOCX extraction uses python-docx if installed, otherwise a stdlib ZIP/XML parser. Missing package(s) detected. Do you want to install? y=install, n=fallback"

Use `--install-missing yes` to install missing Python packages without prompting, `--install-missing no` or `--no-install-missing` to always use fallbacks, or `BOOK_SKILL_INSTALL_MISSING=yes|no|ask` to set the behavior by environment variable. Non-interactive sessions default to fallback unless install mode is explicitly `yes`.

- PDF `--mode technical` → uses Docling (layout-aware, preserves tables and code blocks as markdown)
- PDF `--mode text` → uses pdftotext → pypdf → pdfminer fallback chain (fast, plain text)
- EPUB → uses ebooklib + BeautifulSoup4, then stdlib ZIP/HTML fallback
- DOCX → uses python-docx, then stdlib ZIP/XML fallback
- TXT/Markdown/reStructuredText/AsciiDoc → reads directly as text
- HTML → uses BeautifulSoup4, then stdlib HTML fallback
- RTF → uses striprtf, then a basic regex fallback
- MOBI/AZW/AZW3 → uses Calibre `ebook-convert` when installed, else falls back to the pure-Python `mobi` package (`pip install mobi`). Calibre is an external app, not a pip package; if neither backend is present the script reports both install options.

This creates:
- `<tempdir>/book_skill_work/full_text.txt` — full extracted text
- `<tempdir>/book_skill_work/metadata.json` — title, estimated pages, token count, size, extraction_mode

Read the `output_text` path in `<tempdir>/book_skill_work/metadata.json` to understand what was extracted. The extractor uses the platform temp directory by default and supports `BOOK_SKILL_WORKDIR` if an explicit work directory is needed.

---

## Step 2.5 — Pre-flight cost estimate

Read `<tempdir>/book_skill_work/metadata.json` and present the user with an estimate **before doing any generation**:

```
📖 Source detected: <filename> (<format>)
📄 Pages/Spine items/Sections: ~<N> | Words: ~<N> | Source tokens: ~<N>K

💰 Estimated token cost (Full Conversion):
   Input  (book reading + prompts): ~<N>K tokens
   Output (skill files generated):  ~<N>K tokens
   Total:                           ~<N>K tokens

   Reference prices (as of 2025):
   Claude Sonnet 4.5 → ~$<X> USD
   Claude Haiku 4.5  → ~$<X> USD

   ⏱  Estimated time: ~<N> minutes

📁 Files to be generated:
   SKILL.md + <N> chapter files + glossary + patterns + cheatsheet

➡  Proceed with Full Conversion? (or type "analyze only" to preview first)
```

**How to estimate:**
- Input tokens ≈ `estimated_tokens` from metadata × 1.3 (prompts overhead per chapter pass)
- Output tokens ≈ chapters × 1,000 + 4,000 (SKILL.md) + 4,500 (glossary + patterns + cheatsheet)
- Price: Sonnet input=$3/MTok output=$15/MTok — Haiku input=$0.80/MTok output=$4/MTok

Wait for the user to confirm before proceeding. If they say "analyze only", switch to Mode 2.

---

## Step 2.6 — REPL-style access for large books (> 50k tokens)

Inspired by the Recursive Language Model (RLM) paradigm: treat `full_text.txt` as a queryable corpus, not a single read. Loading the whole file into context burns budget you will need later for generation.

For books over ~50k tokens, prefer programmatic probes over `Read(full_text.txt)` without bounds:

```bash
# Size check before any Read
wc -w "$FULL_TEXT_PATH"

# Find chapter offsets without loading the whole file
grep -n -E "^\s*(Chapter|CHAPTER)\s+[0-9]+" "$FULL_TEXT_PATH" | head -40

# Pull only the chapter you need (lines start..end inclusive)
sed -n '<start>,<end>p' "$FULL_TEXT_PATH"

# Verify a framework is actually mentioned before claiming it in SKILL.md
grep -c -i "westrum\|dora" "$FULL_TEXT_PATH"

# Targeted Read with offset/limit avoids dumping the full file
# Read(file_path=full_text.txt, offset=<line>, limit=<lines>)
```

Use this approach for Step 3 (structure analysis), Step 7 (per-chapter summaries), and Step 8 (glossary / patterns extraction). On books under 50k tokens, a single `Read` is fine.

Why this matters: a 200-page book is ~75k tokens. Re-reading it once per chapter (28 passes) costs ~2M input tokens; using grep + sed to pull only relevant slices keeps generation cost proportional to the output, not the source.

---

## Step 3 — Analyze book structure

Read the first 8,000 characters of the extracted `full_text.txt` to identify:
- Book **title** and **author(s)**
- **Chapter structure** (look for "Chapter N", "PART I", numbered headings, table of contents)
- **Core themes** and subject domain
- Approximate number of chapters

Then read the Table of Contents section if present to map all chapters.

**If mode is "Analyze Only":** produce the extraction report now and stop. Structure:
```
## Extraction Report — <Title>

### Author's Core Frameworks
- **<Framework Name>**: <what it is and when to apply>

### Key Principles
- <Principle>: <actionable rule>

### Techniques & Methods
- <Technique>: <step-by-step or how-to>

### Anti-patterns
- <What to avoid>: <why>

### Suggested Skill Name
`{author-lastname}-{core-concept}` — e.g. `cialdini-influence`

### Chapters Detected
| # | Title | Main Frameworks |
```

---

## Step 3.5 — Establish citation anchors (grounding)

Every framework, principle, technique, and anti-pattern you capture must carry a
**verifiable source**: a chapter ref (always) plus a page ref (when derivable)
plus a short verbatim quote. Before generating, determine what anchors the
extraction exposes.

**Canonical citation format** — reuse this exact shape everywhere:
```
[Ch N, p.PP] "verbatim snippet from the book"
```
- **Chapter** is mandatory. Derive it from the chapter heading that encloses the item.
- **`p.PP`** is included **only when derivable** (see below). Never fabricate a page number — omit `p.PP` rather than guess.
- **Quote** is mandatory and must be verbatim (see Step 7 / Step 8.5 — every quote is grep-verified against `full_text.txt`). Keep it ≤ 25 words (fair-use sized).

**Are page anchors derivable?** Read `extraction_method` from `metadata.json`:

| `extraction_method` | Page anchors | Why |
|---|---|---|
| `pdftotext`, `pdfminer` | **yes** — `\f` form-feeds delimit pages | text-mode PDF preserves page breaks |
| `docling`, `pypdf`, `ebooklib`, DOCX/HTML/RTF/TXT/MD | **no** — use chapter ref only | markdown/joined output drops page boundaries |

When pages are derivable, the **physical** page of a given line = (count of `\f`
form-feeds before it) + 1. That physical index is offset from the **printed book
folio** by the front matter; `metadata.json` carries `page_offset` (an int, or
`null`) so you cite the folio a reader actually sees:
```bash
# Find the line of an exact quote, then its printed folio:
LINE=$(awk -v q='EXACT VERBATIM QUOTE' 'index($0,q){print NR; exit}' "$FULL_TEXT_PATH")
PHYS=$(( $(head -n "$LINE" "$FULL_TEXT_PATH" | tr -cd '\f' | wc -c) + 1 ))
META="$(dirname "$FULL_TEXT_PATH")/metadata.json"
OFFSET=$(python3 -c "import json;print(json.load(open('$META')).get('page_offset'))")
if [ "$OFFSET" = "None" ] || [ -z "$OFFSET" ]; then
  echo "p.$PHYS (pdf)"          # offset undetectable → label the physical page honestly
else
  echo "p.$(( PHYS - OFFSET ))" # printed folio the reader sees
fi
```
- **`page_offset` is an int** → cite the printed folio `[Ch N, p.<phys − offset>]` (floored at 1).
- **`page_offset` is `null`** but pages are derivable → cite `[Ch N, p.<phys> (pdf)]`; the `(pdf)` tag tells the reader it is a physical PDF index, not the printed folio. Never drop the tag.

When pages are **not** derivable at all, every citation is just `[Ch N] "quote"` — this is correct and expected (notably for `docling`/technical books); do not invent pages.

---

## Step 4 — Ask purpose (Full Conversion only)

Before generating, ask the user:

> "What should this skill help you do? (Pick one or more)
> 1. Apply the author's frameworks while working
> 2. Think with the author's mental models
> 3. Reference specific chapters and concepts
> 4. All of the above"

Use the answer to weight what gets highlighted in the SKILL.md Core section.

---

## Step 5 — Determine skill name

If `SKILL_NAME` was provided, use it as the skill slug.
Otherwise, propose two options and let the user choose:
- **By author-concept**: `{author-lastname}-{core-concept}` (e.g. `cialdini-influence`, `meadows-systems`)
- **By title**: lowercase hyphens from book title (e.g. `designing-data-intensive-apps`)

Default to author-concept format if the book has a strong methodological identity.

Choose the destination skill root:
- **Amp default**: `~/.config/agents/skills`
- **Amp project-local**: `.agents/skills` when the user explicitly wants the generated book skill scoped to the current workspace
- **Amp legacy**: `~/.config/amp/skills` if that is the user's existing global skill location
- **Claude Code**: `~/.claude/skills` if the user explicitly asks for Claude Code output

Set `SKILLS_HOME` to the selected root and check that `$SKILLS_HOME/<skill_name>/` does NOT already exist.
If it does, append `-2` or ask the user before overwriting.

---

## Step 6 — Create skill directory structure

```bash
mkdir -p "$SKILLS_HOME/<skill_name>/chapters"
```

---

## Step 7 — Generate chapter summaries

**TOKEN BUDGET RULE — CRITICAL:**
- Each chapter summary file: **800–1,200 tokens** (dense, not verbose)
- Files are loaded on-demand — they are NOT capped per se, but keep them useful and tight

For EACH chapter/major section identified in Step 3:

Read the corresponding section of the extracted `full_text.txt` (use character offsets or grep for chapter headings).

Create `$SKILLS_HOME/<skill_name>/chapters/ch<NN>-<slug>.md` using the structure below.

**Adapt emphasis based on `BOOK_TYPE`:**
- `technical` → prioritize "Code Examples", "Reference Tables", and "Commands & APIs" sections; preserve exact syntax
- `text` → prioritize "Frameworks Introduced", "Mental Models", and "Key Takeaways"; skip empty technical sections

<!-- GROUNDING (Step 3.5): every Framework, Mental Model, and Anti-pattern carries a
     `Source:` citation [Ch N, p.PP] "verbatim quote". The quote must exist in
     full_text.txt verbatim (Step 8.5 verifies every one). Omit p.PP when not derivable. -->

```markdown
# Chapter N: <Full Title>

## Core Idea
<1–2 sentences: the single most important thing this chapter teaches>

## Frameworks Introduced
- **<Framework Name>**: <exact formulation — preserve the author's naming>
  - When to use: <specific situation>
  - How: <steps or criteria>
  - Source: [Ch N, p.PP] "<verbatim quote naming/defining this framework>"

## Key Concepts
- **<Term>**: <precise definition in 1 sentence> [Ch N]
(5–10 most important terms from this chapter)

## Mental Models
<2–4 frameworks or thinking tools. Write as "Use X when Y" or "Think of X as Y">
- Source: [Ch N, p.PP] "<verbatim quote>"

## Anti-patterns
- **<What to avoid>**: <why it fails> — Source: [Ch N, p.PP] "<verbatim quote>"

## Code Examples *(technical books only — omit if BOOK_TYPE=text)*
<!-- Copy the most instructive snippet from the chapter. Preserve indentation exactly. -->
```<language>
<key code example from this chapter>
```
- **What it demonstrates**: <one line>

## Reference Tables *(technical books only — omit if BOOK_TYPE=text)*
<!-- Reproduce any comparison matrix, parameter table, or decision table from the chapter in markdown. -->

## Key Takeaways
1. <Actionable insight>
2. <Actionable insight>
3. <Actionable insight>
(3–7 takeaways a practitioner must remember)

## Connects To
- **Ch N**: <why this chapter relates>
- **<Concept>**: <external concept or standard it connects with>
```

---

## Step 8 — Generate supporting files

### glossary.md
Create `$SKILLS_HOME/<skill_name>/glossary.md`:
- Every significant term from the book, alphabetically sorted
- Format: `**Term** — definition (Ch N)`
- Max 1,500 tokens

### patterns.md
Create `$SKILLS_HOME/<skill_name>/patterns.md`:
- All concrete techniques, design patterns, algorithms from the book
- Format: `## Pattern Name\n**When to use**: ...\n**How**: ...\n**Trade-offs**: ...\n**Source**: [Ch N, p.PP] "<verbatim quote>"`
- Max 2,000 tokens

### cheatsheet.md
Create `$SKILLS_HOME/<skill_name>/cheatsheet.md`:
- Decision tables, comparison matrices, quick-reference rules
- The content you'd want on a single printed page
- Max 1,000 tokens

### cues.md — proactive activation cues
Create `$SKILLS_HOME/<skill_name>/cues.md`. This is what makes the skill fire
*while the user works*, not only when explicitly asked. Map each major framework to
the concrete coding/working situations that should bring it to mind.

For EACH major framework/principle/anti-pattern, attach ≥1 **trigger** — a situation
the agent can detect from the current task, expressed as one or more of:
- **task keywords** — what the user is doing ("retry", "migration", "controller", "rate limit")
- **code shapes** — constructs in view ("a class importing a framework package", "a nested loop", "a public setter")
- **file patterns** — globs that signal the context (`**/adapters/**`, `*.tf`, `**/*Controller*`)

Format (keep ≤ 1,500 tokens, most-used frameworks first):
```markdown
# Activation Cues — <skill_name>
When the current task matches a trigger below, recall the named framework and, if
useful, read the cited chapter before advising.

| When you're… (trigger) | Recall | Where |
|------------------------|--------|-------|
| writing a REST adapter / `**/adapters/**`, "controller" | Ports & Adapters boundary rule | ch04 |
| domain code `import`ing a framework package | Dependency inversion / clean core | ch03 |
| "retry", "backoff", flaky network call | <framework> | chNN |

## Triggers index (keyword → framework → chapter)
- **controller**, **endpoint** → Ports & Adapters → ch04
- **import framework in domain** → Dependency Rule → ch03
```
Rules:
- Triggers must be **concrete and detectable**, not vague ("when designing" is too broad).
- Every major framework gets ≥1 cue; cover the frameworks already named in the chapters.
- This file is derived from the captured frameworks — it needs no source re-read.

### review-rules.md — codebase audit rules *(code-checkable books only — see gate)*
This is what makes the skill an **active reviewer**: it lets `<skill> review <path>`
audit a user's codebase against the book's rules, not just explain them. Derived from
the captured `## Anti-patterns`, `cues.md` code/glob triggers, and `patterns.md` — it
needs **no source re-read**.

**GATE — decide whether to write this file at all.** Count the captured anti-patterns /
cues that have a **concrete code/file/structural signal** a `grep` or glob could detect
(e.g. "SQL built by string concatenation", "verb in a URI path", "domain class imports a
framework type", "unquoted shell variable"). Vague/conceptual anti-patterns ("thinking in
silos", "ignoring opportunity cost") do NOT count.
- **≥3 concrete rules** → write `review-rules.md` (full).
- **1–2** → write it with only those rules + a "partial coverage" note.
- **0** (narrative / non-code books) → **do NOT create the file**; instead add to the
  generated SKILL.md Scope & Limits: "This skill has no machine-checkable rule set;
  `review <path>` is not supported for this book." (Do not gate on `book_type` — it is
  unreliable for backfilled skills.)

Format (cap ~2,000 tokens). A top index table, then one block per rule:
```markdown
# Review Rules — <skill_name>
Audit a codebase against this book's rules; each is checkable by Read/Grep/Glob.
Citations are chapter-level only (no per-rule page anchors); the quoted name after
[Ch N] is the verbatim anti-pattern title from that chapter file.

## Rules index
| id | rule | severity | confidence | scope | source |
|----|------|----------|------------|-------|--------|
| SEC-SQLI-01 | SQL built by string concatenation | violation | high | server code | ch05 |

## Rules

### SEC-SQLI-01 — SQL query built by string concatenation
- intent: user input must never be concatenated into SQL; use parameterized queries.
- scope.glob: ["**/*.py","**/*.java","**/*.js","**/*.ts","**/*.go","**/*.rb","**/*.php"]
- detect.grep:                       # broad ERE candidate-catchers (a hit is NOT yet a finding)
  - '(SELECT|INSERT|UPDATE|DELETE)[^;]*"\s*\+\s*'
  - 'f"[^"]*\b(SELECT|INSERT|UPDATE|DELETE)\b[^"]*\{'
- detect.context: the interpolated token must be a variable/param, not a literal or a
  validated allowlist constant. Confirm by Reading the hit line ±3.
- detect.requires: ≥1 SQL-keyword signal AND ≥1 interpolation signal on the same statement.
- severity: violation
- confidence: high
- exclude.glob: ["**/test*/**","**/*_test.*","**/*spec*","**/migrations/**","**/fixtures/**","**/examples/**","**/vendor/**","**/node_modules/**","**/generated/**"]
- exclude.when: the interpolated value is a literal, an enum/allowlist constant, or a validated table/column name.
- source: [Ch 5] "SQL injection"        # verbatim `- **bold name**:` from chapters/ch05-*.md
- fix: use a parameterized query / prepared statement; bind user values, never build the string.
```

Field rules:
- `severity`: MUST-rules / anti-patterns → `violation`; SHOULD / style → `suggestion`.
- `confidence`: `high` only for unambiguous code signatures; `medium` for structural/heuristic rules (downgraded at review time).
- `exclude.glob` ALWAYS includes tests, fixtures, examples, generated, migrations, vendored.
- `id` = `PREFIX-TOPIC-NN` (PREFIX from the skill, e.g. SEC / REST / HEX / BASH).
- **Citation honesty**: cite `[Ch N] "<verbatim anti-pattern name>"` only — the name must
  exist verbatim in `chapters/chNN-*.md`. **Never** attach a page or a fabricated quote to a rule.

### templates/ — executable scaffold *(buildable technical books only — see gate)*
This turns the skill from "things to read" into "things you run": a `templates/`
directory holding the **project skeleton + build checklist** the book prescribes, so a
user can scaffold the book's approach in seconds. Derived from the captured chapters /
`patterns.md` / `cheatsheet.md` — it needs **no source re-read**.

**GATE — decide whether to write this directory at all.** Only when the book describes a
**concrete, reproducible structure or buildable procedure** — a project/file layout, a
step-by-step method, a repeatable workflow (e.g. the hexagonal 3-module layout, a REST
resource skeleton, a CI pipeline). Conceptual/narrative books (politics, economics,
history) and reference books with no buildable structure → **do NOT create the directory**;
add to the generated SKILL.md Scope & Limits: "This book prescribes no buildable structure;
no `templates/` scaffold is generated."

**Scope — skeleton + checklist only. Do NOT emit compilable/runnable starter code** (it
rots and can be subtly wrong). Emit an annotated structure and a procedure the user fills
in. Cap ~1,500 tokens total. Files:
- `templates/README.md` — what this scaffolds, how to use it, and a one-line **"starting
  point, not production — adapt and verify"** banner. Cite the chapters it implements `[Ch N]`.
- `templates/structure.md` — the prescribed directory/file **layout as a tree**, every node
  annotated with one line: what goes there + `[Ch N]` + why. No code bodies.
- `templates/checklist.md` — the book's build procedure as an **ordered `- [ ]` checklist**,
  each step carrying its `[Ch N]` citation. This is the runnable artifact even when no
  skeleton dirs make sense (e.g. a methodology book).
- skeleton directories (optional) named exactly as the book prescribes, each with a
  `.gitkeep` and a leading comment line `# <what lives here> [Ch N]` — **no source files**.

Every node/step must cite a chapter; if you cannot cite it, the book did not prescribe it —
leave it out. Mark the whole directory clearly as a starting point, never as the book's code.

### figures.md — captured diagrams *(layout-aware extraction only — see gate)*
Technical books are diagram-heavy; pure-text extraction drops them. When the extractor
captured figures it writes `figures.json` (a list of `{page, caption, kind}`) into the work
dir. Turn each into a **described mental model** so the diagram's knowledge survives as text.

**GATE.** Read `figures.json` from the work dir.
- **Absent or empty** (text-mode/EPUB, or no detectable figures) → **do NOT create the file**;
  add to the generated SKILL.md Scope & Limits: "No figures were captured (text-mode extraction
  or no detectable figures); diagrams are not represented." Do not invent figures.
- **Non-empty** → write `figures.md` (cap ~1,500 tokens).

Format — a block per figure:
```markdown
# Figures — <skill_name>
Diagrams captured from the book, each summarized as a described mental model.
The caption is verbatim from the source; the summary is an interpretation, not a quote.

### <caption verbatim from figures.json> [Ch N]
<1–2 lines: what this diagram asserts / the relationship it shows — written from the caption
and the surrounding chapter text you already read. Not quoted as the book.>
```
Rules:
- **Caption verbatim** from `figures.json` — do not paraphrase it (it is the citable handle).
- **Chapter**: parse the figure label when present (`Figure 3.1` / `Fig. 3-2` → `[Ch 3]`);
  otherwise place it under the chapter whose page range contains the figure's `page`.
- The summary is **your gloss** of what the diagram shows — never wrap it in quotes or present
  it as book text. No image bytes, no ASCII recreation.
- Skip a figure whose caption is too thin to summarize honestly rather than padding it.

---

## Step 8.5 — Grounding self-check (verify every quote)

After chapter files and supporting files are written, verify the grounding before
generating SKILL.md. This is the measurable quality gate for citations.

**1. Verify every quote is verbatim.** For each `"quote"` emitted in any generated
file, confirm it exists in `full_text.txt`. A quote that does not match is a
fabrication — fix it (re-quote from the source) or drop the item.
```bash
# Check only quotes that are part of a grounding citation — i.e. the quoted string
# that immediately follows a [Ch …] reference. Do NOT grep every "…" in the files:
# chapters legitimately contain non-source quotes (slogans, UI examples, mnemonics)
# that are not book passages and would be false-positive "failures".
# A line printed by this loop = a cited quote NOT found verbatim in the source → must fix.
grep -rhoE '\[Ch[^]]*\] *"[^"]+"' "$SKILLS_HOME/<skill_name>/chapters" \
     "$SKILLS_HOME/<skill_name>/patterns.md" "$SKILLS_HOME/<skill_name>/SKILL.md" 2>/dev/null \
  | grep -oE '"[^"]+"' | sed 's/^"//; s/"$//' | sort -u \
  | while IFS= read -r q; do
      grep -Fq "$q" "$FULL_TEXT_PATH" || echo "UNVERIFIED QUOTE: $q"
    done
```

**2. Compute citation coverage.** Count captured items (Frameworks, Mental Models,
Anti-patterns, patterns) and how many carry a `Source:`/`[Ch N]` ref. Coverage =
cited / total. Target: **≥ 80%** of items cited; **every** framework has ≥ a
chapter ref. List by name any uncited item so the gap is visible.

**3. Report** the coverage figure and the count of unverified quotes (must be 0
before proceeding). Carry the coverage % into the Step 10 report.

**4. Review-rules name check** *(only if `review-rules.md` was written)*. Each rule's
`source: [Ch N] "<anti-pattern name>"` must name a chapter file that exists and a string
found verbatim in it (or in `cues.md`). A name not found is a fabricated citation — fix
the name or drop the rule. Must be 100% before proceeding.
```bash
grep -oE '\[Ch[^]]*\] *"[^"]+"' "$SKILLS_HOME/<skill_name>/review-rules.md" 2>/dev/null \
  | grep -oE '"[^"]+"' | sed 's/^"//; s/"$//' | sort -u \
  | while IFS= read -r q; do
      grep -Frq "$q" "$SKILLS_HOME/<skill_name>/chapters" "$SKILLS_HOME/<skill_name>/cues.md" \
        >/dev/null 2>&1 || echo "UNVERIFIED RULE CITATION: $q"
    done
```

---

## Step 9 — Generate the master SKILL.md

**CRITICAL TOKEN BUDGET: Keep SKILL.md body under 4,000 tokens.**
Compaction truncates from the END — put the most important content FIRST.

Create `$SKILLS_HOME/<skill_name>/SKILL.md`:

```markdown
---
name: <skill_name>
description: "Knowledge base from \"<Full Title>\" by <Author(s)>. Use when applying <author>'s frameworks for <key topics, 3–6 terms>, studying the book, or referencing its concepts. Proactively recall when <every common user task from cues.md that should fire this skill — phrase each as the user would say it (the symptom/action, NOT book jargon), merge related ones, most-frequent first; cover all the high-frequency triggers, not a 2–4 sample>."
allowed-tools:
  - Read
  - Grep
  - Glob   # include Glob ONLY when review-rules.md was written (feature #1, codebase audit); omit otherwise
argument-hint: [topic, framework name, chapter number, or "review <path>"]
---
<!-- DESCRIPTION TUNING (feature #2): the "Proactively recall when…" tail is the ONLY
     activation signal the agent sees at discovery time — cues.md is NOT in the activation
     index, so a trigger that lives only in cues.md will never fire the skill. The tail must
     therefore reflect EVERY high-frequency trigger from cues.md, each phrased as the user
     would say it (the symptom/action, not book jargon). Merge related triggers into one
     clause and lead with the most common so it stays readable; do NOT cap at a 2–4 sample —
     coverage of all common tasks is the goal, not a fixed count.
     ARGUMENT-HINT: include "review <path>" ONLY when review-rules.md exists; include
     "<topic> in <stack>" ONLY for code/technical books (feature #9); include "scaffold"
     ONLY when templates/ exists (feature #4). -->

# <Full Title>
**Author**: <Author(s)> | **Pages**: ~<N> | **Chapters**: <N> | **Generated**: <YYYY-MM-DD> | **book-to-skill**: v<generator_version>

## How to Use This Skill

- **Without arguments** — load core frameworks for reference
- **With a topic** — ask about `replication`, `pricing`, or another indexed topic; I find and read the relevant chapter
- **With chapter** — ask for `ch05`; I load that specific chapter
- **Review** — `review <path>`: audit a codebase against this book's rules *(only when review-rules.md exists)*
- **In your stack** — ask for a concept "in Go / Spring / TypeScript"; I re-render the book's example in your language while citing the original *(only for code/technical books, feature #9)*
- **Scaffold** — ask to "scaffold" / "set up the project"; I lay out the book's skeleton + build checklist from `templates/` *(only when templates/ exists, feature #4)*
- **Figures** — ask "what does Figure N show?" / "the diagrams"; I read `figures.md`, the book's captured diagrams as described mental models *(only when figures.md exists, feature #8)*
- **Browse** — ask "what chapters do you have?" to see the full index

When you ask about a topic not covered in Core Frameworks below, I will read
the relevant chapter file before answering.

<!-- REVIEWER SECTION (feature #1): include the block below ONLY when review-rules.md was
     written. If it was not (non-code book), omit this block and instead add the
     "no machine-checkable rule set" line to Scope & Limits. -->

## Reviewing a codebase (`review <path>`)

When asked to `review <path>` (or "audit / check this repo against the book"):

1. **Load rules.** Read `review-rules.md`. If absent, say this skill has no machine-checkable rule set and stop.
2. **Enumerate.** For each rule, resolve `scope.glob` against `<path>` with Glob; drop anything matching `exclude.glob` (tests, fixtures, examples, generated, migrations, vendored). Zero in-scope files → mark the rule *not applicable*, don't invent findings.
3. **Find candidates.** Grep the rule's `detect.grep` patterns within its in-scope files. Collect `file:line` hits.
4. **Confirm each hit** (this is where false positives die): Read the hit ±3 lines; apply `detect.context` (is it the dangerous *shape* — a variable not a literal, a path segment not a noun?), `exclude.when`, and `detect.requires`. Failing any → discard.
5. **Classify.** *violation* only if `severity=violation` ∧ `confidence=high` ∧ requirements met ∧ not excluded. Otherwise *suggestion* (downgrade, don't drop). Prototype/one-off/script code in scope → downgrade. **When unsure, downgrade — never fabricate.**
6. **Report** (format below): group by severity then rule; every finding carries `file:line`, rule id+name, the `[Ch N]` citation verbatim from the rule, and the one-line fix. Never emit a finding without a `file:line`.
7. **Honesty footer.** List rules that were *not applicable* and any book guidance that isn't machine-checkable, so the user knows what was NOT audited. Never imply full coverage.

Report format:
```markdown
# Conformance report — <path>
Reviewed against: <skill_name> (<Book Title>)
Files scanned: <N> | Rules applied: <A> of <T>

## Violations
### <RULE-ID> — <name>  [Ch N] "<anti-pattern name>"
- <file>:<line>  `<offending code>`
  Fix: <one-line remedy>

## Suggestions
### <RULE-ID> — <name>  [Ch N] "<name>"  (confidence: medium)
- <file>:<line>  `<code>`
  Fix: <remedy>

## Not audited
- Rules with no in-scope files: <ids>
- Book guidance not machine-checkable: <topics>
```

---

## Core Frameworks & Mental Models
<!-- ~2,000 tokens: the author's most important named frameworks and principles.
     Preserve exact names. Write as "Use X when Y", "Prefer X over Y because Z".
     This is a toolkit, not a summary.
     GROUNDING: each framework carries an inline [Ch N] ref and a short verbatim
     quote so the headline toolkit is itself checkable. e.g.
     - **The 5 Whys** — ask "why" five times to reach root cause. [Ch 3] "keep asking why until the root cause emerges" -->

<generate 2,000 tokens of the most critical frameworks and insights here>

---

## Chapter Index

| # | Title | Key Frameworks |
|---|-------|----------------|
| [ch01](chapters/ch01-<slug>.md) | <Title> | <framework1>, <framework2> |
| [ch02](chapters/ch02-<slug>.md) | <Title> | <framework1>, <framework2> |
...

## Topic Index

<!-- Alphabetical. Major terms/frameworks → chapter(s) that cover them. -->
- **<Term>** → ch<N>[, ch<N>]
- **<Term>** → ch<N>

## Supporting Files

- [glossary.md](glossary.md) — all key terms with definitions
- [patterns.md](patterns.md) — all techniques and design patterns
- [cheatsheet.md](cheatsheet.md) — quick reference tables and decision guides
- [cues.md](cues.md) — activation cues: trigger → framework → chapter
- [review-rules.md](review-rules.md) — codebase audit rules for `review <path>` *(include this line only when the file exists)*
- [templates/](templates/) — project skeleton + build checklist to scaffold the book's approach *(include this line only when the directory exists, feature #4)*
- [figures.md](figures.md) — the book's diagrams captured as described mental models *(include this line only when the file exists, feature #8)*

---

<!-- PERSONALIZE SECTION (feature #9): include the block below ONLY for code/technical
     books (same gate as the reviewer section). Omit it for non-code books. -->

## Adapting examples to your stack

Ask for any concept "in <your stack>" — e.g. "the Specification pattern in TypeScript",
"show this in Go", "Spring instead of Quarkus". I re-express the book's example in your
language/framework while preserving its intent, and I keep the original:

1. Read the cited example from the relevant `chapters/chNN-*.md` (with its `[Ch N]` citation).
2. Re-render it in your stack idiomatically — same behaviour and invariants, your syntax.
3. Show the original (or its citation) alongside, so the mapping is auditable; the book
   stays the source of truth. I never present a translation as if it were the book's text.

If a construct has no faithful equivalent in your stack, I say so rather than forcing it.

---

## Scope & Limits

This skill covers the book content only. For hands-on implementation in your codebase,
combine with project-specific tools. For topics beyond this book, check related skills
or ask the agent directly.
<!-- If review-rules.md was NOT written (non-code book), add here:
     "This skill has no machine-checkable rule set; `review <path>` is not supported for this book." -->
<!-- If the Adapting-examples section was omitted (non-code book), no extra line is needed. -->
```

---

## Step 9.5 — Write the provenance manifest

Write `$SKILLS_HOME/<skill_name>/.book-to-skill.json`. This is what the Upgrade
flow reads to decide what is stale. Pull `generator_version` and `source_sha256`
straight from the extraction's `metadata.json` (do not retype them):

```bash
META="$WORKDIR/metadata.json"   # the metadata.json produced by extract.py
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - "$META" "$SKILLS_HOME/<skill_name>" "<BOOK_TYPE>" <<'PY'
import json, sys
from pathlib import Path
meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
skill_dir = Path(sys.argv[2])
manifest = {
    "generator_version": meta["generator_version"],
    "source_sha256": meta["source_sha256"],
    "source_filename": meta["filename"],
    "book_type": sys.argv[3],
    "extraction_method": meta["extraction_method"],
    # Feature #11: front-matter offset (physical→printed folio). null when undetectable.
    "page_offset": meta.get("page_offset"),
    "generated": __import__("datetime").date.today().isoformat(),
    # Steps that produced content from the source — drives selective regenerate on upgrade.
    "steps_run": [3, 5, 6, 7, 8, 8.5, 9],
    "artifacts": sorted(p.name for p in skill_dir.iterdir() if p.is_file()),
    # Feature #1: whether a review-rules.md was written, and how many rules it holds.
    "reviewable": (skill_dir / "review-rules.md").is_file(),
    "review_rule_count": sum(
        1 for line in (skill_dir / "review-rules.md").read_text().splitlines()
        if line.startswith("### ")
    ) if (skill_dir / "review-rules.md").is_file() else 0,
    # Feature #9: whether this skill offers stack-personalized examples (code books only;
    # tracks the reviewable gate — a book worth review rules has code examples to re-render).
    "personalizable": (skill_dir / "review-rules.md").is_file(),
    # Feature #4: whether a templates/ scaffold was written, and how many top-level entries.
    "scaffolded": (skill_dir / "templates").is_dir(),
    "template_count": sum(1 for _ in (skill_dir / "templates").iterdir())
    if (skill_dir / "templates").is_dir() else 0,
    # Feature #8: number of figure blocks in figures.md (0 when none captured).
    "figures_captured": sum(
        1 for line in (skill_dir / "figures.md").read_text().splitlines()
        if line.startswith("### ")
    ) if (skill_dir / "figures.md").is_file() else 0,
}
(skill_dir / ".book-to-skill.json").write_text(json.dumps(manifest, indent=2) + "\n")
print("manifest written:", skill_dir / ".book-to-skill.json")
PY
```

The manifest plus the archived `.source/` (Step 10) make the skill self-describing:
which generator built it, from which exact bytes, and where the extraction lives
so regeneration never re-reads the original document.

---

## Step 10 — Cleanup and report

**Persist the extraction first, then clean the workdir.** Copy `full_text.txt` +
`metadata.json` into `$SKILLS_HOME/<skill_name>/.source/` so a future upgrade can
regenerate source-dependent steps without re-running extraction (Docling is the
slow part). `.source/` is not Markdown, so agents never load it as skill content.

```bash
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

"$PYTHON_BIN" - "$SKILLS_HOME/<skill_name>" <<'PY'
import os
import shutil
import sys
import tempfile
from pathlib import Path

workdir = Path(os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work"))
source_dir = Path(sys.argv[1]) / ".source"
source_dir.mkdir(parents=True, exist_ok=True)
# figures.json (feature #8) is archived too so figures.md can be regenerated without
# re-running Docling; it is simply absent for text-mode/EPUB extractions.
for name in ("full_text.txt", "metadata.json", "figures.json"):
    src = workdir / name
    if src.exists():
        shutil.copy2(src, source_dir / name)
print("archived extraction to:", source_dir)

shutil.rmtree(workdir, ignore_errors=True)
PY
```

Then report to the user:

```
✅ Skill created: $SKILLS_HOME/<skill_name>/

📚 Book: <Full Title> — <Author>
📄 Pages: ~<N> | Chapters: <N>

Files generated:
  SKILL.md         — core frameworks + index   (~X tokens)
  chapters/        — <N> chapter summaries     (~X tokens each, ~X total)
  glossary.md      — key terms                 (~X tokens)
  patterns.md      — techniques & patterns     (~X tokens)
  cheatsheet.md    — quick reference           (~X tokens)
  ─────────────────────────────────────────────────────
  Total skill size: ~X tokens (loaded on-demand, not all at once)

🔎 Citation coverage: ~NN% of items cited (chapter ref + verbatim quote) | unverified quotes: 0

💡 Tip: check your agent's session cost/usage command to see actual token usage.

Usage:
  Ask for <skill_name>                  → load core frameworks
  Ask <skill_name> about <topic>        → find and explain a topic
  Ask <skill_name> for ch<N>            → dive into a specific chapter
```

---

## Quality Rules

1. **Extract structure, not summaries** — capture named frameworks, exact formulations, anti-patterns; not chapter recaps
2. **Preserve the author's precision** — "The 5 Whys" ≠ "ask why multiple times"; keep exact naming
3. **Density over completeness** — a 1,000-token summary beats a 10,000-token excerpt
4. **Practitioner voice** — write "Use X when Y", not "The book explains X"
5. **Front-load SKILL.md** — compaction keeps the first 5,000 tokens; most important content comes first
6. **Chapter files are on-demand** — they don't count against skill budget until loaded
7. **Never copy raw book text** — always synthesize, summarize, extract signal
8. **Topic index is critical** — it's how the agent navigates to the right chapter file
9. **Ground every item** — each framework/principle/technique/anti-pattern carries `[Ch N, p.PP] "verbatim quote"`; chapter ref always, page only when derivable (never invent one), quotes verbatim and ≤25 words (fair-use); every quote is grep-verified against `full_text.txt` (Step 8.5)

---

## Upgrading generated skills (Mode 4)

A generated skill is a **derived artifact** of `(source + generator version)`. When
the generator gains features, existing skills go stale. This flow updates them
**efficiently** (pay LLM-on-source only for what actually changed) and
**effectively** (the manifest says exactly what is stale, so nothing is missed).

### Migration classes
Every `CHANGELOG.md` entry is tagged with how it must be applied:

| Class | Meaning | How to apply on upgrade | Needs `.source/`? |
|-------|---------|-------------------------|-------------------|
| **additive** | new file derived from already-captured skill data | generate just the new artifact | usually no |
| **transform** | rewrites an existing file, no new data from the book | rewrite in place | no |
| **regenerate** | needs the book re-read (new data: quotes, figures, …) | re-run the listed steps over `.source/full_text.txt` | **yes** |

### Upgrade procedure — `book-to-skill upgrade <skill-dir>`

The deterministic decision (manifest read, CHANGELOG diff, semver delta, `.source/`
verification, class grouping, manifest bump) is done by the planner command — do
not re-derive it by hand:

```bash
# Show the plan without writing anything:
"$PYTHON_BIN" "$SCRIPT_PATH" upgrade "<skill-dir>" --dry-run
```
`SCRIPT_PATH` is the same `extract.py` resolved in Step 2. The command prints the
grouped plan (additive / transform / regenerate / skipped), whether the archived
`.source/` is present and matches, and what — if anything — still needs
model-backed regeneration. Then:

1. **Read the plan.** If it says "already current", stop. If it reports
   `MISSING — re-extract needed`, the skill has no usable `.source/`: ask the user
   for the original document and re-extract once (Step 2) into `.source/`.
   If there is no manifest at all, the skill predates provenance → fall back to a
   full regenerate from the original source.

2. **Run without `--dry-run`** to apply mechanical transforms and bump the manifest
   when nothing model-backed remains. The command lists any `regenerate` (and
   un-mechanizable `additive`/`transform`) entries it left for you.

3. **Execute the model-backed remainder** the command reported — for each entry,
   re-run only the SKILL.md steps it names (e.g. `steps 7,8,8.5,9`) over
   `.source/full_text.txt`. Preserve the skill name, paths, and user edits to
   unaffected files. After regenerating, rewrite the manifest (Step 9.5) with the
   new `generator_version`.

4. **Class order — cheapest first (what the planner applies / you regenerate):**
   - **additive** → create each new artifact from the existing skill files (and
     `.source/full_text.txt` only if the entry says so). Never touch unrelated files.
   - **transform** → rewrite only the named files in place.
   - **regenerate** → re-run *only* the steps listed in the CHANGELOG entry (e.g.
     `[regenerate; steps 7,8,9]`) against `.source/full_text.txt`. Do not re-run
     the whole pipeline. Preserve the skill name, paths, and any user edits to
     unaffected files.

5. **Show a diff and confirm.** Before writing, summarize what will change
   (files added / rewritten / regenerated) and get user approval. Upgrades are
   re-runnable and idempotent.

6. **Bump the manifest.** Set `generator_version` to the current version, refresh
   `generated`, `artifacts`, and (if `.source/` was re-extracted) `source_sha256`.

### Efficiency rules
- **Never full-regenerate when the delta is only additive/transform.** That is the
  whole point of the manifest + CHANGELOG classes.
- **Never re-extract when `.source/full_text.txt` exists and `source_sha256` still
  matches** — extraction is deterministic and already archived.
- **Prefer additive features.** When a new capability can be a new file derived
  from existing captured structure, the CHANGELOG should tag it `additive` so
  upgrades cost almost nothing.
