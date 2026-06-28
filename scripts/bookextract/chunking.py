"""Pure section chunking for the Mycelia orchestrated build.

Splits an extracted document into ordered, size-bounded chunks the agent reads
one at a time. Line ranges line up with ``sed -n`` / ``grep -n`` (which are
newline-based), so line numbering here uses ``str.split("\\n")`` — **not**
``str.splitlines()``, which also breaks on form-feeds and would desynchronise
the ranges from the shell tools the agent uses.

Boundaries are size-driven (a word budget) and snapped to a blank line so a
chunk never cuts mid-paragraph; heading detection (reusing ``structure.py``'s
signals, broadened to bare ``N Title`` / ``N.N Title`` book sections) only
*labels* a chunk — real books vary too much for headings to be reliable cut
points. Also exposes the line→printed-folio helpers that complement
``pageoffset.detect_page_offset``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from bookextract.structure import _STRONG_HEADING, _numbered_heading_value

# A bare book-section heading: "2 Algebraic Coding Theory" or "1.1 Communication Systems".
_SECTION_HEADING: Final[re.Pattern[str]] = re.compile(r"^\s*(\d+)(?:\.\d+)*\s+[A-Z]")
# Leading chapter/section marker, stripped to expose the title text for vetting.
_LEADING_NUM: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:(?:chapter|chapitre|capitolo|kapitel|cap[íi]tulo|ch)\.?\s*)?\d+(?:\.\d+)*[.)]?\s*",
    re.IGNORECASE,
)
_MAX_LABEL_LEN: Final[int] = 70
_MAX_SECTION_DIGITS: Final[int] = 3  # "12.4" ok; a 20-digit binary string is not a heading
_MAX_CHAPTER_NO: Final[int] = 99  # a larger leading number is a page number, not a chapter
_MIN_TITLE_WORD: Final[int] = 3  # "Es"/"IO" after a number is a formula, not a section title
_MAX_TITLE_WORDS: Final[int] = 8  # more words is a numbered list item ("1. All code words…")
_SENTENCE_TAIL: Final[str] = ".,;:"
_DEFAULT_TARGET_WORDS: Final[int] = 8000
_SNAP_LOOKAHEAD: Final[int] = 40  # lines scanned past the target for a blank-line boundary
_PDF_TAG: Final[str] = " (pdf)"


@dataclass(frozen=True)
class Chunk:
    """One readable slice of the source: a labelled, 1-based inclusive line range."""

    index: int
    label: str
    chapter: int | None
    start_line: int
    end_line: int
    words: int


def _candidate_number(stripped: str) -> int | None:
    """The chapter/section number if the line matches any heading pattern, else None."""
    strong = _STRONG_HEADING.match(stripped)
    if strong:
        return int(strong.group(1) or strong.group(2))
    numbered = _numbered_heading_value(stripped)
    if numbered is not None:
        return numbered
    section = _SECTION_HEADING.match(stripped)
    if section and len(section.group(1)) <= _MAX_SECTION_DIGITS:
        return int(section.group(1))
    return None


def _is_title_like(stripped: str, after: str) -> bool:
    """Reject prose, running page headers, and formula lines shaped like a heading.

    ``after`` is the text following the leading number. A real section title is
    short (few words), Title-cased, not ALL-CAPS (running headers), and its first
    word is an alphabetic token without digits (``"G1,k+1"``/``"Es"`` are formulas,
    not titles). A many-word title is a numbered list item ("1. All code words…").
    A bare marker (``"Chapter 2"`` with no title) is accepted.
    """
    if len(stripped) > _MAX_LABEL_LEN or stripped[-1] in _SENTENCE_TAIL:
        return False
    if not after:
        return True
    if not after[0].isupper() or after.isupper():
        return False  # lowercase prose, or an ALL-CAPS running header
    words = after.split()
    if len(words) > _MAX_TITLE_WORDS:
        return False  # a sentence-length "title" is a numbered list item, not a heading
    first = words[0]
    return (
        len(first) >= _MIN_TITLE_WORD
        and any(c.isalpha() for c in first)
        and not any(c.isdigit() for c in first)
    )


def _heading_at(line: str) -> tuple[int | None, str] | None:
    """Return ``(chapter_number, heading_text)`` if the line looks like a heading."""
    stripped = line.strip()
    if not stripped:
        return None
    number = _candidate_number(stripped)
    if number is None or number > _MAX_CHAPTER_NO:
        return None
    after = _LEADING_NUM.sub("", stripped, count=1).strip()
    if not _is_title_like(stripped, after):
        return None
    return number, stripped


def _snap(lines: list[str], i: int, n: int) -> int:
    """First blank line at/after ``i`` within the lookahead window, else a hard cut at ``i``."""
    for j in range(i, min(i + _SNAP_LOOKAHEAD, n)):
        if not lines[j].strip():
            return j
    return i


def _chunk_bounds(lines: list[str], target: int) -> Iterator[tuple[int, int]]:
    """Yield 0-based half-open ``[start, end)`` ranges of ~``target`` words each."""
    start = 0
    words = 0
    n = len(lines)
    i = 0
    while i < n:
        words += len(lines[i].split())
        i += 1
        if words >= target:
            end = _snap(lines, i, n)
            yield start, end
            start = i = end
            words = 0
    if start < n:
        yield start, n


def _label_for(lines: list[str], start: int, end: int) -> tuple[int | None, str]:
    """Label a chunk by its first heading, else the nearest preceding one, else its lines."""
    for k in range(start, end):
        head = _heading_at(lines[k])
        if head is not None:
            return head
    for k in range(start - 1, -1, -1):
        head = _heading_at(lines[k])
        if head is not None:
            return head
    return None, f"lines {start + 1}-{end}"


def chunk_sections(text: str, *, target_words: int = _DEFAULT_TARGET_WORDS) -> tuple[Chunk, ...]:
    """Split ``text`` into ordered, size-bounded :class:`Chunk` slices (1-based line ranges)."""
    lines = text.split("\n")
    chunks: list[Chunk] = []
    for start, end in _chunk_bounds(lines, target_words):
        chapter, label = _label_for(lines, start, end)
        words = sum(len(lines[k].split()) for k in range(start, end))
        chunks.append(Chunk(len(chunks), label, chapter, start + 1, end, words))
    return tuple(chunks)


def physical_page_at(text: str, line: int) -> int:
    """Physical page (1-based) of a 1-based line: form-feeds before it, plus one."""
    prefix = "\n".join(text.split("\n")[: max(0, line - 1)])
    return prefix.count("\f") + 1


def folio(physical: int, offset: int | None) -> str:
    """Printed folio token for a physical page: remapped via ``offset``, or tagged ``(pdf)``."""
    if offset is None:
        return f"{physical}{_PDF_TAG}"
    return str(max(1, physical - offset))
