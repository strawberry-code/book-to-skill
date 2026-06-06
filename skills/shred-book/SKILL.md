---
name: shred-book
description: "One-shot wrapper around book-to-skill for technical PDFs. Extracts a PDF with Docling (technical mode), generates a Claude Code skill from it using the current session, then moves the source PDF into ~/Downloads/shredded-books. Use when the user passes a technical PDF path and wants the whole pipeline (extract → skill → archive) in one go."
allowed-tools:
  - Bash
  - Read
  - Write
  - Glob
  - Grep
argument-hint: <path-to-pdf> [skill-name-slug]
---

# shred-book

Micro wrapper over the `book-to-skill` converter. Forces **technical** extraction
(Docling, layout-aware), builds the skill with the current Claude session, and
archives the consumed PDF.

Treat the first argument as `BOOK_PATH`, the optional second as `SKILL_NAME`.

This skill does NOT re-implement extraction or generation — it drives the
existing `book-to-skill` logic with two fixed choices: mode is always
`technical`, and on success the PDF is moved to `~/Downloads/shredded-books`.

---

## Step 0 — Validate input

Only PDFs are in scope here (technical mode = Docling = PDF). For other formats,
tell the user to use `/book-to-skill` directly.

```bash
test -f "$BOOK_PATH" || { echo "FILE_NOT_FOUND: $BOOK_PATH" >&2; exit 1; }
case "${BOOK_PATH##*.}" in
  pdf|PDF) echo "PDF_OK" ;;
  *) echo "NOT_A_PDF: shred-book is technical-PDF only. Use /book-to-skill for ${BOOK_PATH##*.}." >&2; exit 1 ;;
esac
```

If not a PDF, stop and point the user at `/book-to-skill`.

---

## Step 1 — Extract with technical mode

Locate `extract.py` (repo checkout first, then installed skill locations), then
run it with `--mode technical`. Do NOT ask the user for the book type — it is
fixed.

```bash
SCRIPT_PATH=""
for candidate in \
  "scripts/extract.py" \
  "$HOME/github/strawberry-code/book-to-skill/scripts/extract.py" \
  ".agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/agents/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.config/amp/skills/book-to-skill/scripts/extract.py" \
  "$HOME/.claude/skills/book-to-skill/scripts/extract.py"
do
  [ -f "$candidate" ] && { SCRIPT_PATH="$candidate"; break; }
done
[ -z "$SCRIPT_PATH" ] && { echo "Could not find scripts/extract.py for book-to-skill" >&2; exit 1; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"

"$PYTHON_BIN" "$SCRIPT_PATH" "$BOOK_PATH" --mode technical --install-missing ask
```

Output lands in `<tempdir>/book_skill_work/` (or `$BOOK_SKILL_WORKDIR`):
- `full_text.txt` — extracted text
- `metadata.json` — title, pages, token count, `extraction_mode`

Read `metadata.json` and confirm `extraction_mode` is `technical`. If Docling
fell back to the text chain (mode reported as `text`), warn the user — Docling
is likely not installed (`pip3 install docling`) — and ask whether to continue
with the text-quality extraction or abort.

If extraction fails (non-zero exit, no `full_text.txt`), STOP. Do not generate,
do not move the PDF.

---

## Step 2 — Generate the skill (current session)

Follow `book-to-skill` **Steps 3 and 5–9** using the extracted `full_text.txt`,
with `BOOK_TYPE=technical` throughout (prioritize Code Examples, Reference
Tables, Commands & APIs; preserve exact syntax).

- Skip Step 4 (purpose question) — assume "All of the above"; this is a one-shot.
- Step 5: if `SKILL_NAME` was given, use it. Otherwise derive an
  author-concept or title slug as book-to-skill describes. Default
  `SKILLS_HOME="$HOME/.claude/skills"`. Refuse to overwrite an existing
  `$SKILLS_HOME/<skill_name>/` — append `-2` or ask.
- Steps 6–9: create the directory, chapter files, glossary/patterns/cheatsheet,
  and the master `SKILL.md`, honoring the token budgets.

Do all generation in THIS session (Read/Write the files directly) — that is the
"create the skill using the current Claude session" requirement.

If generation cannot complete (e.g. unreadable text, zero chapters found), STOP
before Step 3 — leave the PDF where it is.

---

## Step 3 — Archive the PDF (success only)

Only reach this step if Step 1 produced a valid extraction AND Step 2 wrote a
complete skill (at minimum `$SKILLS_HOME/<skill_name>/SKILL.md` exists). Move —
do not copy — the source PDF into the archive, creating it if needed. Never
overwrite an existing archived file of the same name.

```bash
ARCHIVE="$HOME/Downloads/shredded-books"
mkdir -p "$ARCHIVE"
base="$(basename "$BOOK_PATH")"
dest="$ARCHIVE/$base"
if [ -e "$dest" ]; then
  stem="${base%.*}"; ext="${base##*.}"
  dest="$ARCHIVE/${stem}-$(date +%Y%m%d%H%M%S).${ext}"
fi
mv -n "$BOOK_PATH" "$dest" && echo "ARCHIVED: $dest"
```

---

## Step 4 — Cleanup and report

Remove the work directory, then report to the user:

```bash
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
"$PYTHON_BIN" - <<'PY'
import os, shutil, tempfile
from pathlib import Path
shutil.rmtree(
    os.environ.get("BOOK_SKILL_WORKDIR", Path(tempfile.gettempdir()) / "book_skill_work"),
    ignore_errors=True,
)
PY
```

Final report (concise):
- Skill created at `$SKILLS_HOME/<skill_name>/` (list files + token estimate)
- How to invoke it (`/<skill_name>`, `/<skill_name> <topic>`)
- PDF archived at `~/Downloads/shredded-books/<file>`
