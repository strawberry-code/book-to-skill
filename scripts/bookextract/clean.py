"""Deterministic raw-text cleanup (Fase E): strip running headers/footers + page numbers.

``pdftotext`` interleaves page furniture into the body — bare page-number lines and
repeated ALL-CAPS running headers/footers (``322 ACRONYMS``, ``ALGEBRAIC CODING
THEORY``). Left in, they pollute chunks and tempt the model to quote them, causing
grounding noise. This removes them before chunking, with no dependency and a
conservative rule so prose is never touched:

* a line that is **only** a page number (``^\\d{1,4}$``);
* a line whose alpha content is **all-caps** (no lowercase letters) and that
  **repeats** across the document (≥ ``_MIN_REPEAT`` times after trimming edge
  digits) — the repetition is what distinguishes a running header from a one-off
  all-caps heading, which is kept.

Form-feed (``\\f``) lines are never removed, so physical-page/folio counting stays
exact. Returns the cleaned text and how many lines were dropped (reported, never
silent).
"""

from __future__ import annotations

import re
from typing import Final

_PAGE_NUM: Final[re.Pattern[str]] = re.compile(r"^\d{1,4}$")
_EDGE_DIGITS: Final[re.Pattern[str]] = re.compile(r"^[\d\s]+|[\d\s]+$")
_MIN_REPEAT: Final[int] = 5  # an all-caps line seen this often is a running header
_MAX_HEADER_LEN: Final[int] = 60


def _header_core(line: str) -> str:
    """A header line's stable core: trimmed of leading/trailing page digits."""
    return _EDGE_DIGITS.sub("", line.strip()).strip()


def _is_caps(text: str) -> bool:
    """True when ``text`` has letters and none are lowercase (an ALL-CAPS line)."""
    return bool(text) and text == text.upper() and any(c.isalpha() for c in text)


def _running_headers(lines: list[str]) -> set[str]:
    """All-caps line cores that repeat often enough to be running headers/footers."""
    counts: dict[str, int] = {}
    for line in lines:
        core = _header_core(line)
        if core and len(core) <= _MAX_HEADER_LEN and _is_caps(core):
            counts[core] = counts.get(core, 0) + 1
    return {core for core, n in counts.items() if n >= _MIN_REPEAT}


def clean_text(text: str) -> tuple[str, int]:
    """Strip page-number lines and repeated all-caps running headers; return (text, removed)."""
    lines = text.split("\n")
    running = _running_headers(lines)
    kept: list[str] = []
    removed = 0
    for line in lines:
        stripped = line.strip()
        if _PAGE_NUM.match(stripped):
            removed += 1
            continue
        core = _header_core(stripped)
        if core in running and _is_caps(core) and len(core) <= _MAX_HEADER_LEN:
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed
