---
name: mycelia
description: "Converts books and documents (PDF, EPUB, DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW) into an atomic, interlinked OKF knowledge vault — one note per concept, framework, principle, entity, method, and anti-pattern, densely cross-linked with verifiable citations. Use when the user wants a scalable second brain across many books, to ingest a book into an existing vault, or to build a portable agent-queryable knowledge base. This is the default emitter; for the legacy single-book skill format see SKILL.md."
compatibility: "Produces a self-contained OKF v0.1 bundle (a directory of Markdown files) droppable on any filesystem and consumable by any OKF-aware agent."
allowed-tools:
  - shell_command
  - Read
  - Write
  - Glob
  - Grep
argument-hint: <path-to-document> [vault-dir]
---

# Mycelia — Book → OKF Knowledge Vault

Transform written knowledge into an **atomic, interlinked vault** — a network (a *mycelium*) of small, single-idea notes that reference each other and carry verifiable citations back to the source.

## Philosophy

Books contain crystallized expertise. At the scale of *hundreds* of books, the unit that scales is **not** one skill per book (every skill description is injected into context each session → context ceiling + selection degrades). The unit that scales is a **vault**: interlinked Markdown + semantic retrieval. So Mycelia emits a vault, not a skill.

**Atomic / Zettelkasten granularity.** One note = one concept, framework, principle, entity, method, or anti-pattern. The note's *path is its identity*. Notes link densely to each other; a per-book MOC and a root `index.md` provide navigation.

**Extract structure, not summaries.** A note captures a named idea with its exact formulation, an actionable definition, and a grounded citation — not a chapter recap. "The 5 Whys" is not "ask why a few times": preserve the author's precision.

**Convergence across books is the killer feature.** When book A and book B both cover *apoptosis*, the vault must hold **one** canonical `concepts/apoptosis.md` with citations to *both* sources — not two duplicates. This is the difference between a second brain and a pile of notes (see [Reconciliation](#reconciliation--check-before-create)).

**OKF-native, no hybrids.** The on-disk format is [Open Knowledge Format](https://okf.md/spec/) v0.1: a directory of Markdown files with YAML frontmatter, standard Markdown links, reserved `index.md`/`log.md`. OKF requires only one field (`type`); everything else is recommended or a documented governance extension. A pure-OKF consumer ignores our extensions without breaking (they degrade gracefully). No wikilinks in the core.

---

## Modes of Operation

Route based on what the user asks:

### 1. New vault (Default)
**Trigger:** User provides a document path and no existing vault dir (or the dir is empty).
**Action:** Run all steps. Create a fresh OKF bundle and ingest the book into it.

### 2. Ingest into existing vault (cross-book)
**Trigger:** The target `vault-dir` already contains a `index.md` with `okf_version`.
**Action:** Run all steps, but in Step 9 **reconcile** every atomic note against the notes already present (check-before-create) instead of writing blindly. This is how a second book's concepts merge into shared canonical notes.

### 3. Analyze only
**Trigger:** User says "analyze", "just extract", or "preview before generating".
**Action:** Run Steps 0–3, produce the extraction report (frameworks, principles, entities found + a proposed note inventory), then stop. Write nothing.

---

## Orchestrated build (default for large books)

For anything bigger than a few chapters, do **not** hand-write note files. Use the deterministic orchestrator: you emit validated **Note JSON**, and the code assembles the OKF bundle — files, reciprocal `## Related` backlinks, computed folios, slug/alias dedup, and citations grounded against `raw/` — then runs `okf_lint` as the gate. This is what keeps quality from drifting at scale. The hand-emission Steps 6–10 below remain the fallback for small books.

**Flow:**
1. Extract (Step 2) → `full_text.txt` + `metadata.json` in the work dir.
2. `book-extract build-plan <work-dir> --out <bundle> [--slug s] [--target-words N]` → chunks the book, archives `raw/<slug>/`, writes `.mycelia/{plan,journal,source}.json`.
3. Fill `.mycelia/source.json` `title` + `authors` (from Step 3).
4. For each chunk in `.mycelia/plan.json`: read its `start_line..end_line` with `sed -n` (REPL-style, Step 2.6), extract atomic notes, and **write `.mycelia/chunks/<id>.json`** (schema below). Apply the Step 3.5 grounding contract to the quotes. Do **not** write `.md` files, links, folios, or citations — the assembler owns those.
5. `book-extract assemble <bundle>` → validates + grounds every note, dedups by slug, inserts reciprocal links, writes the bundle, runs the lint gate. Fix any reported error and re-run (idempotent). Record the chunk in `.mycelia/journal.json` so a long book resumes across context compaction.

**Note JSON schema** — one file per chunk, `{"notes": [ <note>, … ]}`; each note (comments illustrative, not valid JSON):
```jsonc
{
  "type": "Concept",                     // Concept|Framework|Principle|Entity|Method|AntiPattern
  "slug": "channel-capacity",            // kebab-case; the note's identity (its path)
  "title": "Channel capacity",
  "description": "one-line definition (progressive disclosure)",
  "tags": ["coding-theory"],
  "aliases": ["Shannon capacity"],       // synonyms — reconciliation merges on these
  "confidence": "high",                  // low | medium | high
  "status": "established",               // established | contested | insufficient
  "body": "2–5 sentences, practitioner voice, no headings",
  "related": ["mutual-information", "binary-symmetric-channel"],  // slugs; the code links + reciprocates
  "citations": [
    {"chapter": 1, "quote": "verbatim text present in raw/", "source": "<slug>"}
  ]
}
```
What the assembler enforces (target it): every note needs ≥1 citation whose `quote` exists in `raw/` (matching folds ligatures + whitespace, so a quote may span line breaks); `related` are **slugs** (it links and reciprocates them, so you only state one direction); **a slug emitted in two chunks is merged** into one canonical note accruing both citations — this is the cross-chapter/cross-book reconciliation, so emit the *same slug* for the *same concept*. Page folios are computed for you from where each quote sits in `raw/`.

---

## Step 0 — Out-of-scope check

If the first argument is not a path to a supported document file, stop and respond:
> "mycelia requires a supported document path. Usage: `mycelia /path/to/book.pdf [vault-dir]` (also `.epub`, `.docx`, `.md`, `.txt`, `.html`, `.rtf`, `.mobi`, `.azw3`). Pass an existing OKF vault dir as the second argument to ingest the book into it."

Treat the first argument as `BOOK_PATH` and the optional second as `VAULT_DIR`.

---

## Step 1 — Validate input

```bash
test -f "$BOOK_PATH" && echo "FILE_OK" || echo "FILE_NOT_FOUND: $BOOK_PATH"
case "${BOOK_PATH##*.}" in
  pdf|PDF|epub|EPUB|docx|DOCX|txt|TXT|md|MD|markdown|MARKDOWN|rst|RST|adoc|ADOC|asciidoc|ASCIIDOC|html|HTML|htm|HTM|rtf|RTF|mobi|MOBI|azw|AZW|azw3|AZW3) echo "FORMAT_OK" ;;
  *) echo "FORMAT_UNKNOWN" ;;
esac
```

If the file is not found or the format is unsupported, stop with a clear error listing supported formats.

---

## Step 1.5 — Identify book type

Before extracting, ask the user:

> "What kind of content does this book have? This helps me choose the best extraction method.
>
> 1. **Technical** — has code blocks, tables, formulas, diagrams (programming, academic, architecture)
> 2. **Text-heavy** — mostly prose (management, narrative non-fiction, science writing)
> 3. **Not sure** — I'll use the fast method and warn you if quality seems limited"

Store as `BOOK_TYPE`: option 1 → `technical`; options 2/3 → `text`.

**If `technical`:** "📐 Technical mode — Docling for structure-aware extraction (tables/code/formulas as markdown). ~1.5s/page; expect a few minutes for long books."
**If `text`:** "📄 Text mode — fastest suitable extractor. Plain text/Markdown/HTML in seconds; PDFs use pdftotext when available."

---

## Step 2 — Extract text from the source document

Mycelia reuses the **same** mechanical extractor as the legacy skill emitter (`scripts/extract.py`). Resolve it across install locations, then shell out passing the book type:

```bash
SCRIPT_PATH=""
for candidate in \
  ".agents/skills/mycelia/scripts/extract.py" \
  "$HOME/.config/agents/skills/mycelia/scripts/extract.py" \
  "$HOME/.claude/skills/mycelia/scripts/extract.py" \
  ".agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.claude/skills/book-to-skill/scripts/extract.py" \
  "scripts/extract.py"
do
  if [ -f "$candidate" ]; then SCRIPT_PATH="$candidate"; break; fi
done

if [ -z "$SCRIPT_PATH" ]; then
  echo "Could not find scripts/extract.py for mycelia" >&2
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"

"$PYTHON_BIN" "$SCRIPT_PATH" "$BOOK_PATH" --mode <BOOK_TYPE> --install-missing ask
```

Extraction method by mode/format (unchanged from the extractor):
- PDF `technical` → Docling (layout-aware, tables/code preserved); PDF `text` → pdftotext → pypdf → pdfminer.
- EPUB → ebooklib + BeautifulSoup4, then stdlib ZIP/HTML fallback. DOCX → python-docx, then stdlib ZIP/XML.
- TXT/Markdown/RST/AsciiDoc → read directly. HTML → BeautifulSoup4, then stdlib. RTF → striprtf, then regex.
- MOBI/AZW/AZW3 → Calibre `ebook-convert` when present, else the pure-Python `mobi` package.

This produces in the work dir (platform temp by default; `BOOK_SKILL_WORKDIR` overrides):
- `full_text.txt` — full extracted text
- `metadata.json` — title, pages, token count, size, `extraction_method`, `source_sha256`, `page_offset`, `generator_version`

Read `output_text` in `metadata.json` to confirm what was extracted.

---

## Step 2.5 — Pre-flight cost estimate

Read `metadata.json` and present an estimate **before any generation**:

```
📖 Source: <filename> (<format>)
📄 Pages/Spine/Sections: ~<N> | Words: ~<N> | Source tokens: ~<N>K

💰 Estimated token cost (vault ingest):
   Input  (book reading + reconciliation lookups): ~<N>K
   Output (atomic notes + MOC + index/log):        ~<N>K
   Total:                                           ~<N>K

   Reference prices (2026): Claude Opus 4.8 · Sonnet 4.6 · Haiku 4.5 — see the claude-api skill for current rates.
   ⏱  Estimated time: ~<N> minutes

📁 Vault: <VAULT_DIR>  (<new bundle | ingest into existing>)
   ~<N> atomic notes expected across concepts/ frameworks/ principles/ entities/ methods/ anti-patterns/

➡  Proceed? (or "analyze only" to preview first)
```

Estimate: input ≈ `estimated_tokens` × 1.3; output ≈ expected_notes × ~400 + index/log/MOC overhead. Wait for confirmation. "analyze only" → Mode 3.

---

## Step 2.6 — REPL-style access for large books (> 50k tokens)

Treat `full_text.txt` as a queryable corpus, not a single read — loading it whole burns the budget you need for note generation.

```bash
wc -w "$FULL_TEXT_PATH"                                            # size check first
grep -n -E "^\s*(Chapter|CHAPTER|PART)\s+[0-9IVX]+" "$FULL_TEXT_PATH" | head -40   # chapter offsets
sed -n '<start>,<end>p' "$FULL_TEXT_PATH"                          # pull one chapter
grep -c -i "apoptosis\|necrosis" "$FULL_TEXT_PATH"                 # verify a concept is present before noting it
```

Use this for Step 3 (structure), Step 9 (per-chapter note extraction), and the grounding self-check. Under 50k tokens, a single `Read` is fine.

---

## Step 3 — Analyze book structure

Read the first ~8,000 characters of `full_text.txt` to identify:
- Book **title** and **author(s)**
- **Chapter structure** (look for "Chapter N", "PART I", numbered headings, ToC)
- **Core themes** and subject domain; approximate chapter count

Read the Table of Contents if present to map all chapters.

**If mode is "Analyze Only":** produce this report and stop:
```
## Extraction Report — <Title>

### Proposed note inventory
| type | slug | one-line description | source ref |
|------|------|----------------------|------------|
| Concept | apoptosis | programmed cell death | Ch 12 |
| Framework | ... | ... | ... |

### Core themes / domain
### Suggested vault name
`<domain>` or `<author-lastname>-<core-concept>`
### Chapters detected
| # | Title | Candidate notes |
```

---

## Step 3.5 — Establish citation anchors (grounding)

Every atomic note must carry a **verifiable source**: a chapter ref (always) + a page ref (when derivable) + a short verbatim quote, recorded in the note's `# Citations` section.

**Canonical citation format** — reuse this exact shape everywhere:
```
[Ch N, p.PP] "verbatim snippet from the book"
```
- **Chapter** is mandatory (from the heading enclosing the item).
- **`p.PP`** only when derivable (table below). Never fabricate a page — omit `p.PP` rather than guess.
- **Quote** is mandatory, verbatim, ≤ 25 words (fair-use), grep-verified in Step 9.6.

**Are page anchors derivable?** Read `extraction_method` from `metadata.json`:

| `extraction_method` | Page anchors | Why |
|---|---|---|
| `pdftotext`, `pdfminer` | **yes** — `\f` form-feeds delimit pages | text-mode PDF keeps page breaks |
| `docling`, `pypdf`, `ebooklib`, DOCX/HTML/RTF/TXT/MD | **no** — chapter ref only | markdown/joined output drops page boundaries |

When derivable, physical page of a line = (count of `\f` before it) + 1, remapped to the printed folio via `page_offset`:
```bash
LINE=$(awk -v q='EXACT VERBATIM QUOTE' 'index($0,q){print NR; exit}' "$FULL_TEXT_PATH")
PHYS=$(( $(head -n "$LINE" "$FULL_TEXT_PATH" | tr -cd '\f' | wc -c) + 1 ))
META="$(dirname "$FULL_TEXT_PATH")/metadata.json"
OFFSET=$(python3 -c "import json;print(json.load(open('$META')).get('page_offset'))")
if [ "$OFFSET" = "None" ] || [ -z "$OFFSET" ]; then echo "p.$PHYS (pdf)"; else echo "p.$(( PHYS - OFFSET ))"; fi
```
- `page_offset` is an int → cite the printed folio `[Ch N, p.<phys − offset>]` (floored at 1).
- `page_offset` is `null` but pages derivable → cite `[Ch N, p.<phys> (pdf)]`; keep the `(pdf)` tag.
- Pages not derivable at all → every citation is `[Ch N] "quote"` (correct and expected, notably for `docling`).

---

## Step 4 — Determine vault name and destination

If `VAULT_DIR` was provided **and** contains `index.md` with `okf_version` → **Mode 2 (ingest)**: `BUNDLE="$VAULT_DIR"`, `BOOK_SLUG=<kebab-case of book title>`.

Otherwise **Mode 1 (new vault)**. Propose a vault name and let the user choose:
- **By domain** (best for a multi-book library): `cell-biology`, `clinical-pharmacology`
- **By author-concept** (single authoritative book): `<author-lastname>-<core-concept>`
- **By title**: lowercase-hyphens of the book title

Set `BUNDLE` to a **self-contained, portable** directory (default `./<vault-name>/`, or wherever the user wants — it has no external dependencies and can be moved/copied anywhere). Set `BOOK_SLUG`. Confirm with the user whether this is a new vault or an addition to an existing library.

---

## Step 5 — Create / open the OKF bundle skeleton

```bash
mkdir -p "$BUNDLE"/{concepts,frameworks,principles,entities,methods,anti-patterns,references,moc,raw}
```

**If new bundle**, write the root `index.md` (the ONLY file allowed `okf_version`, and the ONLY frontmatter an index.md may carry):
```markdown
---
okf_version: "0.1"
---

# <Vault Name>

An atomic, interlinked OKF knowledge vault generated by Mycelia.

## Sections
- [Concepts](/concepts/) — canonical single-idea notes
- [Frameworks](/frameworks/) — named models with application
- [Principles](/principles/) — actionable rules
- [Entities](/entities/) — people, organisms, organizations, named things
- [Methods](/methods/) — procedures and techniques
- [Anti-patterns](/anti-patterns/) — what to avoid and why
- [References](/references/) — one note per source book
- [Maps of content](/moc/) — navigation hubs by theme

## Sources
<!-- one bullet per ingested book, linking its reference note -->
```

Write `log.md` (newest-first, ISO-8601 date headings, prose entries with a leading bold word):
```markdown
# Log

## <YYYY-MM-DD>
- **Create** Initialized vault and ingested "<Book Title>" by <Author> (<N> notes).
```

Write **`SCHEMA.md`** — the editorial schema layer (this is what keeps the vault from drifting; see [SCHEMA.md template](#schemamd-template) below).

**If ingesting** into an existing bundle, skip the skeleton writes; only ensure the type dirs exist and append to `log.md` and the root `index.md` Sources list at the end.

---

## Step 6 — Archive the raw source (immutable layer)

Copy the extraction into `raw/<BOOK_SLUG>/` so the vault is self-describing and notes can be regenerated without re-reading the original document. **`raw/` is immutable — never edit its files; re-ingestion overwrites them wholesale.**

```bash
PYTHON_BIN="${PYTHON_BIN:-python3}"; command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
"$PYTHON_BIN" - "$BUNDLE" "$BOOK_SLUG" <<'PY'
import os, shutil, sys, tempfile
from pathlib import Path
workdir = Path(os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work"))
raw = Path(sys.argv[1]) / "raw" / sys.argv[2]
raw.mkdir(parents=True, exist_ok=True)
for name in ("full_text.txt", "metadata.json", "figures.json"):
    src = workdir / name
    if src.exists():
        shutil.copy2(src, raw / name)
print("archived raw source to:", raw)
PY
```

`raw/` is not part of the OKF concept graph (its files have no frontmatter and are not linked as concepts); it is the re-derivable ground truth.

---

## Step 7 — Emit the source reference note + book MOC

Write `references/<BOOK_SLUG>.md` — a first-class `type: Source` concept. This is the OKF-native provenance anchor every `# Citations` links back to:
```markdown
---
type: Source
title: "<Full Title>"
description: "<Author(s)> — <one-line scope of the book>"
tags: [<domain>, source]
timestamp: <YYYY-MM-DD>T00:00:00Z
authors: [<Author(s)>]
extraction_method: <from metadata.json>
source_sha256: <from metadata.json>
raw: /raw/<BOOK_SLUG>/full_text.txt
---

# <Full Title>

**Author(s):** <…> · **Pages:** ~<N> · **Chapters:** <N> · **Ingested:** <YYYY-MM-DD>

<2–4 sentence neutral description of the book and its domain.>

# Citations
<!-- this note IS the source; no external citations needed here -->
```

Write `moc/<BOOK_SLUG>.md` — a hand-curated map of content for this book (`type: MOC`), listing every note extracted from it grouped by note type, with bundle-relative links:
```markdown
---
type: MOC
title: "<Book Title> — map of content"
description: "Navigation hub for notes sourced from <Book Title>"
tags: [<domain>, moc]
timestamp: <YYYY-MM-DD>T00:00:00Z
source: /references/<BOOK_SLUG>.md
---

# <Book Title> — Map of Content

## Concepts
- [Apoptosis](/concepts/apoptosis.md) — programmed cell death
## Frameworks
- ...
## Principles / Entities / Methods / Anti-patterns
- ...
```

---

## Step 8 — Plan the atomic note inventory

From the structure (Step 3) and chapter probes (Step 2.6), build the list of atomic notes to emit, each tagged with: `type` (Concept/Framework/Principle/Entity/Method/AntiPattern), a kebab-case `slug` (→ `<type-dir>/<slug>.md`, the note's identity), a one-line `description`, candidate `aliases` (synonyms), and its grounding anchor `[Ch N, p.PP] "quote"`.

One idea per note. Split compound ideas; do not merge distinct concepts into one note. Prefer the most canonical name for the slug; record other names in `aliases` so reconciliation can find the note later.

---

## Step 9 — Emit atomic notes (with reconciliation)

For each planned note, **check-before-create** (full algorithm in [Reconciliation](#reconciliation--check-before-create)):

1. **Look up** the slug and every alias (NFKC + casefold) across the type dirs.
2. **If a matching note exists** → *merge*, do not duplicate: add this book's line to its `# Citations`, fold in any genuinely new substance, add the source to its `## Related`/MOC, and union `aliases`. If the existing note and this book **conflict**, set `contested: true` and record both positions under `## Contradictions` (flag, don't resolve).
3. **If no match** → *create* the note.

Note template (one concept; **standard OKF Markdown links only — no wikilinks**):
```markdown
---
type: Concept
title: Apoptosis
description: Programmed, regulated cell death that removes cells without inflammation.
tags: [cell-biology, cell-death]
timestamp: <YYYY-MM-DD>T00:00:00Z
aliases: [programmed cell death, PCD]
confidence: high            # low | medium | high  (governance extension)
contested: false            # true → surfaced by the linter/report
status: established          # established | contested | insufficient
---

# Apoptosis

<2–5 sentences: the precise, actionable definition in the practitioner voice.
Capture the author's exact formulation; do not summarize the chapter.>

## Related
- [Necrosis](/concepts/necrosis.md) — unregulated, inflammatory cell death (contrast)
- [Caspase cascade](/methods/caspase-cascade.md) — the executioner pathway

## Contradictions
<!-- present ONLY when contested: true. State each conflicting position + its source. -->

# Citations
[1] [Ch 12, p.340] "apoptosis is a programmed sequence of events leading to cell death" — [<Book Title>](/references/<BOOK_SLUG>.md)
```

Rules:
- **Links are bundle-relative absolute** (`/concepts/apoptosis.md`) so they survive moves. Every link target must exist (the linter enforces zero dangling) — only link to notes you have created or will create in this run.
- **`## Related` is the backlink fabric.** When note A links to B, add the reciprocal link in B's `## Related` (the linter does not auto-create these; the recipe must).
- **`# Citations` is the provenance** (OKF puts sources in the body, not frontmatter): numbered, each entry = the grounded `[Ch N, p.PP] "verbatim quote"` + a bundle-relative link to the source reference note. A concept seen in multiple books accrues multiple numbered citations on the **same** note.
- Append each emitted note to the book MOC (Step 7) and to the relevant `## Related` lists.

---

## Step 9.5 — Update index and log (progressive disclosure)

- **Root `index.md`:** add a bullet under `## Sources` linking the new `references/<BOOK_SLUG>.md`. (Keep index.md frontmatter-free except the root `okf_version`.)
- **Per-section `index.md` (optional but recommended at scale):** in each type dir that gained notes, maintain an `index.md` (no frontmatter) listing its notes as `- [Title](/concepts/slug.md) — description`. This is OKF progressive disclosure: an agent reads section indexes before opening individual notes.
- **`log.md`:** prepend a dated entry (newest-first):
```markdown
## <YYYY-MM-DD>
- **Update** Ingested "<Book Title>": +<created> notes, <merged> merged into existing concepts, <contested> contradictions flagged.
```

---

## Step 9.6 — Grounding self-check + OKF lint (quality gate)

**1. Verify every cited quote is verbatim.** For each `[Ch …] "quote"` emitted in `# Citations`, confirm it exists in the archived `raw/<BOOK_SLUG>/full_text.txt`. A non-matching quote is a fabrication — re-quote or drop the item.
```bash
RAW="$BUNDLE/raw/$BOOK_SLUG/full_text.txt"
grep -rhoE '\[Ch[^]]*\] *"[^"]+"' "$BUNDLE"/concepts "$BUNDLE"/frameworks "$BUNDLE"/principles \
     "$BUNDLE"/entities "$BUNDLE"/methods "$BUNDLE"/anti-patterns 2>/dev/null \
  | grep -oE '"[^"]+"' | sed 's/^"//; s/"$//' | sort -u \
  | while IFS= read -r q; do grep -Fq "$q" "$RAW" || echo "UNVERIFIED QUOTE: $q"; done
```

**2. Citation coverage.** Count atomic notes and how many carry ≥ 1 `# Citations` entry. Target **≥ 80%**; **every** note must carry at least a chapter ref. List uncited notes by name.

**3. Run the deterministic OKF linter** — this is the verifiable success criterion (zero dangling links, valid OKF), not a matter of trust:
```bash
"$PYTHON_BIN" "$SCRIPT_PATH" lint "$BUNDLE"
```
The linter checks: every non-reserved `.md` has a non-empty `type`; every `](/…md)` / `](./…md)` link resolves (zero dangling); `index.md` files carry no frontmatter (except root `okf_version`); `log.md` dates are ISO-8601 and newest-first. **Fix every error before reporting success.**

---

## Step 9.7 — Write / update the provenance manifest

Write `$BUNDLE/.mycelia.json` (bundle root). For a new vault it records the first source; for an ingest it **appends** to `sources`. Pull `generator_version`/`source_sha256` from the extraction `metadata.json` (do not retype):
```bash
"$PYTHON_BIN" - "$BUNDLE" "$BOOK_SLUG" "<BOOK_TYPE>" <<'PY'
import json, sys
from datetime import date
from pathlib import Path
bundle = Path(sys.argv[1]); slug = sys.argv[2]; book_type = sys.argv[3]
meta = json.loads((bundle / "raw" / slug / "metadata.json").read_text(encoding="utf-8"))
mpath = bundle / ".mycelia.json"
manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {
    "generator_version": meta["generator_version"], "okf_version": "0.1", "sources": [],
}
def count(sub: str) -> int:
    d = bundle / sub
    return sum(1 for p in d.glob("*.md") if p.name != "index.md") if d.is_dir() else 0
manifest["generator_version"] = meta["generator_version"]
manifest["updated"] = date.today().isoformat()
manifest["sources"] = [s for s in manifest.get("sources", []) if s.get("slug") != slug] + [{
    "slug": slug, "source_filename": meta["filename"], "book_type": book_type,
    "extraction_method": meta["extraction_method"], "source_sha256": meta["source_sha256"],
    "page_offset": meta.get("page_offset"), "ingested": date.today().isoformat(),
}]
manifest["note_counts"] = {s: count(s) for s in
    ("concepts", "frameworks", "principles", "entities", "methods", "anti-patterns")}
mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print("manifest written:", mpath)
PY
```

---

## Step 10 — Cleanup and report

Remove the temp work dir (the extraction already lives in `raw/`):
```bash
"$PYTHON_BIN" - <<'PY'
import os, shutil, tempfile
from pathlib import Path
shutil.rmtree(Path(os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work")), ignore_errors=True)
PY
```

Report to the user:
```
✅ Vault <new | updated>: <BUNDLE>/

📚 Ingested: <Full Title> — <Author>
🧬 Notes: +<created> created, <merged> merged into existing concepts, <contested> contradictions flagged
🔗 Sections touched: concepts(<n>) frameworks(<n>) principles(<n>) entities(<n>) methods(<n>) anti-patterns(<n>)
🔎 Citation coverage: ~NN% | unverified quotes: 0 | OKF lint: PASS (0 dangling links)

The vault is a self-contained OKF bundle — copy it anywhere; any OKF-aware agent can read it.
Ingest another book:  mycelia <next-book> "<BUNDLE>"
```

---

## Reconciliation — check-before-create

The mechanism that makes the vault *converge* instead of *fragment*. Before creating any atomic note:

1. **Build the candidate key set:** the planned slug + every alias, each normalized = NFKC + casefold + strip punctuation/whitespace.
2. **Look up** across the type dirs. Match if: a file `<type>/<slug>.md` exists, OR any existing note's `aliases` (normalized) contains a candidate key, OR a normalized title matches. Prefer an existing `concepts/` note as the canonical home.
   ```bash
   # fast prefilter: does a note with this slug or alias already exist?
   grep -rilE "^(title|aliases):.*<term>" "$BUNDLE"/concepts "$BUNDLE"/frameworks \
        "$BUNDLE"/principles "$BUNDLE"/entities "$BUNDLE"/methods "$BUNDLE"/anti-patterns 2>/dev/null
   ```
3. **On match → merge** (never duplicate): append this book's numbered `# Citations` entry; fold in only genuinely new substance (don't restate); union `aliases`; add reciprocal `## Related` links; add the note to this book's MOC. Bump the note's `updated` (add the key if absent).
4. **On conflict** (the two sources disagree on a fact, not just emphasis): keep one canonical note, set `contested: true`, add both positions under `## Contradictions` with their citations, and log it. **Flag, do not adjudicate** — resolution is a human call.
5. **On no match → create** the note fresh.

This is intentionally a v1 **agentic** mechanism (zero extra dependencies). Embedding-based dedup (cosine similarity + LLM arbitration for semantic synonyms that don't share a string, e.g. "Deutschland"/"Germany") is a roadmap item, not v1.

---

## SCHEMA.md template

Write this into every new bundle. It is the **schema layer** that keeps the vault consistent across ingests (without it, multi-book vaults drift):

```markdown
---
type: Schema
title: Vault Schema
description: Editorial conventions for this OKF vault — note types, frontmatter, linking, provenance, dedup.
timestamp: <YYYY-MM-DD>T00:00:00Z
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
Standard Markdown, **bundle-relative absolute** so they survive moves — an absolute target such as `/concepts/code-review.md` written as a Markdown link. No wikilinks. Each link has a reciprocal entry in the target note's `## Related`.

## Provenance
- Each source book is a `type: Source` note under `references/`.
- Each note cites its sources in a numbered body `# Citations` section: a grounded `[Ch N, p.PP] "verbatim quote"` plus a bundle-relative link to the source note. A concept seen in multiple books accrues multiple citations on ONE note.

## Reserved files
- `index.md` — directory listing for progressive disclosure; carries NO frontmatter (the bundle root `index.md` may carry only `okf_version`).
- `log.md` — change history; ISO-8601 date headings, newest-first.

## Dedup rule
Check-before-create: normalize (NFKC + casefold), look up slug + aliases, merge into the canonical note rather than duplicating. Conflicts across sources set `contested: true` and a `## Contradictions` section (flag, do not resolve).
```

> `SCHEMA.md` carries `type: Schema` so it is itself OKF-valid (only `index.md`/`log.md` are reserved/untyped). The linter (Step 9.6) will flag any non-reserved `.md` lacking `type`.

---

## Quality Rules

1. **Atomic** — one idea per note. Split compound ideas; never merge distinct concepts.
2. **Extract structure, not summaries** — exact framework names, actionable definitions, anti-patterns; not chapter recaps.
3. **Preserve precision** — "The 5 Whys" ≠ "ask why a few times".
4. **Converge, don't fragment** — always check-before-create; one canonical note per concept across all books.
5. **Ground every note** — `[Ch N, p.PP] "verbatim quote"` in `# Citations`; chapter ref always, page only when derivable (never invent), quotes ≤25 words and grep-verified.
6. **OKF-native, no hybrids** — bundle-relative Markdown links, `type` on every note, reserved `index.md`/`log.md`. Governance fields are documented extensions that degrade gracefully.
7. **Reciprocal links** — every link has a backlink in the target's `## Related`. Zero dangling (linter-enforced).
8. **Flag, don't resolve** — contradictions across sources are surfaced (`contested`, `## Contradictions`, `log.md`), never silently adjudicated.
9. **Portable & self-contained** — the bundle has no external dependencies; it must remain navigable when copied to any filesystem.

---

## Relationship to the legacy skill emitter

`SKILL.md` (the original `book-to-skill` recipe) remains in this repo as the **legacy** single-book → agent-skill emitter. Mycelia is the default and the path that scales to large libraries. Both sit on the same mechanical extractor (`scripts/bookextract/`) and the same Step 3.5 grounding contract; they differ only in what they emit. A converter from old book-skills to OKF vaults is on the roadmap.
