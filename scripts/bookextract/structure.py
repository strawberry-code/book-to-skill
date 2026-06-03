"""Pure document-structure detection: chapter headings and ToC presence.

No I/O, no globals — given the extracted text, return a small dict that feeds
metadata.json (``chapters_detected``, ``chapter_headings_sample``, ``has_toc``).
"""

from __future__ import annotations

import re
from typing import Final

# Strong signal: an explicit "Chapter N" / "Capitolo N" / "ch. N" heading.
_STRONG_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:chapter|chapitre|capitolo|kapitel|cap[íi]tulo)\s+\d+\b"
    r"|^\s*ch\.\s*\d+\b",
    re.IGNORECASE,
)
# Weak signal: a bare "N. Title" numbered heading.
_NUMBERED_HEADING: Final[re.Pattern[str]] = re.compile(r"^\s*\d+\.\s+[A-Z]")
# A line of body text wrongly shaped like a heading is excluded by these guards.
_MAX_HEADING_LEN: Final[int] = 70
_SENTENCE_TAIL: Final[str] = ".,;:"

_TOC_LINE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:table of contents|contents|índice|sumário)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_TOC_SCAN_CHARS: Final[int] = 30000
_HEADING_SAMPLE: Final[int] = 10


def _looks_like_numbered_heading(line: str) -> bool:
    return (
        bool(_NUMBERED_HEADING.match(line))
        and len(line) <= _MAX_HEADING_LEN
        and line[-1] not in _SENTENCE_TAIL
    )


def detect_structure(text: str) -> dict[str, object]:
    """Detect chapter count and table-of-contents presence.

    Scans the whole text (cheap line iteration) so chapters past any fixed prefix
    are not dropped; the ToC keyword is matched on its own line within the front
    matter to avoid false positives like "the contents of this book are...".

    Args:
        text: The full extracted document text.

    Returns:
        A dict with ``chapters_detected`` (int), ``chapter_headings_sample``
        (list of up to 10 headings), and ``has_toc`` (bool).
    """
    chapters_found: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _STRONG_HEADING.match(line) or _looks_like_numbered_heading(line):
            chapters_found.append(line)

    return {
        "chapters_detected": len(chapters_found),
        "chapter_headings_sample": chapters_found[:_HEADING_SAMPLE],
        "has_toc": bool(_TOC_LINE.search(text[:_TOC_SCAN_CHARS])),
    }
