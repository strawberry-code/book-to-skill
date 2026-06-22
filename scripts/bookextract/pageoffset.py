"""Front-matter page-offset detection and citation remapping.

#3 grounding cites pages by counting form-feed (``\\f``) page breaks in the
extracted text — the *physical* PDF page index. That is offset from the *printed*
folio by the length of the front matter (cover, ToC, preface). This module recovers
that offset **deterministically** (no model, no I/O) and rewrites already-emitted
``[Ch N, p.PP]`` citations to printed folios.

Detection anchors on chapter-start pages that print their own folio: a physical
page whose first non-empty line is a "Chapter N" heading usually carries the
printed folio in its header/footer. ``physical_index - folio`` is voted across all
such anchors; a confident result needs a non-negative modal offset agreed by a
strict majority of at least ``_MIN_AGREE`` anchors. Form-feed-free text (Docling
technical mode, EPUB) yields no anchors → ``None`` → the caller labels pages as
physical, never silently passing a physical index off as a printed folio.
"""

from __future__ import annotations

import re
from typing import Final

# A chapter heading at the very top of a physical page (the false anchors in a ToC
# or preface reference "Chapter N" mid-line, so anchoring on line 0 excludes them).
_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:chapter|chapitre|capitolo|kapitel|cap[íi]tulo)\s+(\d+)\b", re.IGNORECASE
)
# The printed folio is the leading or trailing integer of the page's header/footer.
_LEAD: Final[re.Pattern[str]] = re.compile(r"^\s*(\d{1,4})\b")
_TRAIL: Final[re.Pattern[str]] = re.compile(r"\b(\d{1,4})\s*$")
_MIN_AGREE: Final[int] = 3
_MAX_FOLIO: Final[int] = 4000
_MIN_PAGES: Final[int] = 2  # need at least one form-feed split to have page structure

# A grounding citation bracket and the page token inside it. Two-level matching keeps
# the page rewrite scoped to citations — a bare "p.21" in prose is never touched.
_BRACKET: Final[re.Pattern[str]] = re.compile(r"\[Ch[^\]]*\]")
_PAGE: Final[re.Pattern[str]] = re.compile(r"(p\.)(\d+)")


def _folio_candidates(line: str, exclude: int) -> list[int]:
    """Leading/trailing integers of ``line`` that could be a printed folio.

    ``exclude`` drops the chapter number itself (the "3" in "CHAPTER 3"), which
    would otherwise masquerade as a folio on the heading line.
    """
    out: list[int] = []
    for match in (_LEAD.search(line), _TRAIL.search(line)):
        if match:
            value = int(match.group(1))
            if 0 < value <= _MAX_FOLIO and value != exclude:
                out.append(value)
    return out


def _winning_offset(votes: dict[int, int]) -> int | None:
    """Modal offset if non-negative and a strict majority of ≥ ``_MIN_AGREE``; else None."""
    if not votes:
        return None
    offset = max(votes, key=lambda key: votes[key])
    count = votes[offset]
    total = sum(votes.values())
    if offset < 0 or count < _MIN_AGREE or count * 2 <= total:
        return None
    return offset


def detect_page_offset(text: str) -> int | None:
    """Return the physical−printed page offset, or None when not confidently detectable.

    Args:
        text: The full extracted document text (with ``\\f`` page breaks for PDFs).

    Returns:
        The integer offset to subtract from a physical page index to get the printed
        folio, or ``None`` when there is no form-feed structure or the anchors do not
        agree (caller should then label pages as physical).
    """
    pages = text.split("\f")
    if len(pages) < _MIN_PAGES:  # no form-feed structure (Docling/EPUB/plain)
        return None
    votes: dict[int, int] = {}
    for index, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        heading = _HEADING.match(lines[0])
        if heading is None:
            continue
        chapter = int(heading.group(1))
        candidates = _folio_candidates(lines[0], chapter)
        if len(lines) > 1:
            candidates += _folio_candidates(lines[-1], chapter)
        # One vote per distinct offset per anchor page, so a footer that is just the
        # folio (matching both leading and trailing patterns) counts once, not twice —
        # then _MIN_AGREE means "≥3 distinct chapter pages agree", as intended.
        for offset in {index - folio for folio in candidates}:
            votes[offset] = votes.get(offset, 0) + 1
    return _winning_offset(votes)


def _remap_bracket(bracket: str, offset: int | None) -> tuple[str, int]:
    """Rewrite page tokens inside one citation bracket; return ``(text, n_changed)``."""
    if offset is None and "(pdf)" in bracket:  # already labelled — idempotent
        return bracket, 0
    count = 0

    def repl(page_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        page = int(page_match.group(2))
        if offset is None:
            return f"{page_match.group(1)}{page} (pdf)"
        return f"{page_match.group(1)}{max(1, page - offset)}"

    return _PAGE.sub(repl, bracket), count


def remap_citations(text: str, offset: int | None) -> tuple[str, int]:
    """Remap every ``[Ch N, p.PP]`` page in ``text`` to a printed folio.

    With a known ``offset`` each physical page ``PP`` becomes ``PP - offset`` (floored
    at 1, so a front-matter citation never goes ≤ 0). With ``offset is None`` each page
    gets a ``(pdf)`` label so the number is not mistaken for a printed folio. The page
    rewrite is scoped to ``[Ch …]`` brackets, so a ``p.21`` in running prose is left
    untouched.

    Args:
        text: File contents containing grounding citations.
        offset: The detected page offset, or ``None`` to label pages as physical.

    Returns:
        ``(new_text, citations_changed)``.
    """
    total = 0
    out: list[str] = []
    last = 0
    for bracket in _BRACKET.finditer(text):
        out.append(text[last : bracket.start()])
        fixed, changed = _remap_bracket(bracket.group(0), offset)
        out.append(fixed)
        total += changed
        last = bracket.end()
    out.append(text[last:])
    return "".join(out), total
