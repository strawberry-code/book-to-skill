"""Pure document-structure detection: chapter headings and ToC presence.

No I/O, no globals — given the extracted text, return a small dict that feeds
metadata.json (``chapters_detected``, ``chapter_headings_sample``, ``has_toc``).
"""

from __future__ import annotations

import re
from typing import Final

# Strong signal: an explicit "Chapter N" / "Capitolo N" / "ch. N" heading.
# The number is captured so repeats (ToC entries, running page headers) collapse
# onto a single chapter instead of being counted once per occurrence.
_STRONG_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:chapter|chapitre|capitolo|kapitel|cap[íi]tulo)\s+(\d+)\b"
    r"|^\s*ch\.\s*(\d+)\b",
    re.IGNORECASE,
)
# Weak signal: a bare "N. Title" numbered heading.
_NUMBERED_HEADING: Final[re.Pattern[str]] = re.compile(r"^\s*(\d+)\.\s+[A-Z]")
# A line of body text wrongly shaped like a heading is excluded by these guards.
_MAX_HEADING_LEN: Final[int] = 70
_SENTENCE_TAIL: Final[str] = ".,;:"

_TOC_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:table of contents|contents|índice|sumário)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOC_SCAN_CHARS: Final[int] = 30000
_HEADING_SAMPLE: Final[int] = 10


def _numbered_heading_value(line: str) -> int | None:
    """Chapter number for a bare ``N. Title`` heading, or None if not one.

    The length/sentence-tail guards keep body prose ("1. The quick brown fox…")
    from registering as a heading.
    """
    match = _NUMBERED_HEADING.match(line)
    if match and len(line) <= _MAX_HEADING_LEN and line[-1] not in _SENTENCE_TAIL:
        return int(match.group(1))
    return None


def detect_structure(text: str) -> dict[str, object]:
    """Detect chapter count and table-of-contents presence.

    Scans the whole text (cheap line iteration) so chapters past any fixed prefix
    are not dropped; the ToC keyword is matched on its own line within the front
    matter to avoid false positives like "the contents of this book are...".

    Headings are deduplicated by chapter number: a ToC listing every chapter and
    the running page header that repeats the title on each page would otherwise
    each count, inflating the total (e.g. 24 real chapters reported as 176). The
    strong "Chapter N" signal wins outright when present; the weak "N. Title"
    form is only used as a fallback so body numbered-lists never mix in.

    Args:
        text: The full extracted document text.

    Returns:
        A dict with ``chapters_detected`` (int), ``chapter_headings_sample``
        (list of up to 10 headings in chapter-number order), and ``has_toc``
        (bool).
    """
    strong: dict[int, str] = {}
    numbered: dict[int, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = _STRONG_HEADING.match(line)
        if match:
            strong.setdefault(int(match.group(1) or match.group(2)), line)
            continue
        weak_number = _numbered_heading_value(line)
        if weak_number is not None:
            numbered.setdefault(weak_number, line)

    chosen = strong or numbered
    ordered = [chosen[number] for number in sorted(chosen)]
    return {
        "chapters_detected": len(chosen),
        "chapter_headings_sample": ordered[:_HEADING_SAMPLE],
        "has_toc": bool(_TOC_LINE.search(text[:_TOC_SCAN_CHARS])),
    }
