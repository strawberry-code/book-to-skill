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
_MAX_LABEL_LEN: Final[int] = 70
_MAX_SECTION_DIGITS: Final[int] = 3  # "12.4" ok; a 20-digit binary string is not a heading
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


def _heading_at(line: str) -> tuple[int | None, str] | None:
    """Return ``(chapter_number, heading_text)`` if the line looks like a heading."""
    stripped = line.strip()
    if not stripped:
        return None
    strong = _STRONG_HEADING.match(stripped)
    if strong:
        return int(strong.group(1) or strong.group(2)), stripped
    numbered = _numbered_heading_value(stripped)
    if numbered is not None:
        return numbered, stripped
    section = _SECTION_HEADING.match(stripped)
    if (
        section
        and len(section.group(1)) <= _MAX_SECTION_DIGITS
        and len(stripped) <= _MAX_LABEL_LEN
        and stripped[-1] not in _SENTENCE_TAIL
    ):
        return int(section.group(1)), stripped
    return None


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
