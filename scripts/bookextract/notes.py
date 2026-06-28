"""Pure Note model + schema validation + programmatic grounding.

The agent emits one JSON object per atomic note; this module validates it against
a fixed schema and *grounds* each citation against the immutable ``raw`` text.

Grounding is **normalize-then-match**: the quote and the source are both NFKC-
normalized (folding ligatures like ``ﬁ`` → ``fi``), case-folded, and whitespace-
collapsed (so a quote that spans a line break still matches) before searching.
On a match the original span is recovered from ``raw`` verbatim and its printed
folio computed. This fixes the false negatives a literal single-line grep hits on
real ``pdftotext`` / ``docling`` output.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from bookextract.chunking import folio

ATOMIC_TYPES: Final[frozenset[str]] = frozenset(
    {"Concept", "Framework", "Principle", "Entity", "Method", "AntiPattern"}
)
_CONFIDENCE: Final[frozenset[str]] = frozenset({"low", "medium", "high"})
_STATUS: Final[frozenset[str]] = frozenset({"established", "contested", "insufficient"})
_DEFAULT_CONFIDENCE: Final[str] = "medium"
_DEFAULT_STATUS: Final[str] = "established"
_SLUG: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_WS: Final[re.Pattern[str]] = re.compile(r"\s+")
_QUOTE_PREVIEW: Final[int] = 60


class NoteValidationError(Exception):
    """A note (or its grounding) failed validation; carries an optional fix hint."""

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


@dataclass(frozen=True)
class Citation:
    """An agent-supplied citation: a chapter, a verbatim quote, and a source slug."""

    chapter: int
    quote: str
    source: str


@dataclass(frozen=True)
class GroundedCitation:
    """A citation verified against ``raw``: verbatim span recovered, folio computed."""

    chapter: int
    quote: str
    source: str
    folio: str | None  # None when the source has no derivable page boundaries


@dataclass(frozen=True)
class Note:
    """A validated atomic note as emitted by the agent (pre-assembly, pre-grounding)."""

    type: str
    slug: str
    title: str
    description: str
    tags: tuple[str, ...]
    aliases: tuple[str, ...]
    confidence: str
    status: str
    body: str
    related: tuple[str, ...]
    citations: tuple[Citation, ...]


def _get_str(obj: dict[str, object], key: str, *, required: bool = True) -> str:
    """Return a string field; raise if it's missing/non-string (or empty when required)."""
    val = obj.get(key, "")
    if not isinstance(val, str):
        raise NoteValidationError(f"field {key!r} must be a string")
    if required and not val.strip():
        raise NoteValidationError(f"field {key!r} is required and must be non-empty")
    return val


def _get_list(obj: dict[str, object], key: str) -> tuple[str, ...]:
    """Return a tuple of strings for an optional list field (empty when absent)."""
    val = obj.get(key, [])
    if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
        raise NoteValidationError(f"field {key!r} must be a list of strings")
    return tuple(val)


def _enum(obj: dict[str, object], key: str, allowed: frozenset[str], default: str) -> str:
    """Return an enum field defaulting to ``default``; raise if outside ``allowed``."""
    val = obj.get(key) or default
    if val not in allowed:
        raise NoteValidationError(f"{key} {val!r} not in {sorted(allowed)}")
    return str(val)


def _citations(obj: dict[str, object]) -> tuple[Citation, ...]:
    """Validate and return the note's non-empty citation list."""
    raw = obj.get("citations")
    if not isinstance(raw, list) or not raw:
        raise NoteValidationError("note needs a non-empty 'citations' list")
    out: list[Citation] = []
    for item in raw:
        if not isinstance(item, dict):
            raise NoteValidationError("each citation must be an object")
        chapter = item.get("chapter")
        if not isinstance(chapter, int):
            raise NoteValidationError("citation.chapter must be an integer")
        out.append(Citation(chapter, _get_str(item, "quote"), _get_str(item, "source")))
    return tuple(out)


def validate_note(obj: object) -> Note:
    """Validate one agent-emitted JSON object into a :class:`Note`, or raise."""
    if not isinstance(obj, dict):
        raise NoteValidationError("a note must be a JSON object")
    note_type = _get_str(obj, "type")
    if note_type not in ATOMIC_TYPES:
        raise NoteValidationError(f"type {note_type!r} not in {sorted(ATOMIC_TYPES)}")
    slug = _get_str(obj, "slug")
    if not _SLUG.match(slug):
        raise NoteValidationError(f"slug {slug!r} must be kebab-case ([a-z0-9] with single dashes)")
    return Note(
        type=note_type,
        slug=slug,
        title=_get_str(obj, "title"),
        description=_get_str(obj, "description"),
        tags=_get_list(obj, "tags"),
        aliases=_get_list(obj, "aliases"),
        confidence=_enum(obj, "confidence", _CONFIDENCE, _DEFAULT_CONFIDENCE),
        status=_enum(obj, "status", _STATUS, _DEFAULT_STATUS),
        body=_get_str(obj, "body"),
        related=_get_list(obj, "related"),
        citations=_citations(obj),
    )


def _normalize(text: str) -> str:
    """NFKC + casefold + whitespace-collapse — the comparable form for matching."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Normalized text plus, per normalized char, the original index it came from."""
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, char in enumerate(text):
        if char.isspace():
            if not prev_space:
                out.append(" ")
                idx.append(i)
                prev_space = True
            continue
        prev_space = False
        for folded in unicodedata.normalize("NFKC", char).casefold():
            out.append(folded)
            idx.append(i)
    return "".join(out), idx


def ground_citation(citation: Citation, raw: str, page_offset: int | None) -> GroundedCitation:
    """Verify a citation's quote against ``raw`` and compute its folio, or raise."""
    needle = _normalize(citation.quote)
    if not needle:
        raise NoteValidationError(f"empty quote ({citation.source} Ch {citation.chapter})")
    norm_raw, idx = _normalize_with_map(raw)
    pos = norm_raw.find(needle.strip())
    if pos < 0:
        preview = citation.quote[:_QUOTE_PREVIEW]
        raise NoteValidationError(
            f'quote not found verbatim in source ({citation.source}): "{preview}…"',
            hint="quote text that exists in raw/ — matching folds ligatures + whitespace",
        )
    start = idx[pos]
    end = idx[pos + len(needle.strip()) - 1] + 1
    verbatim = _WS.sub(" ", raw[start:end]).strip()
    page = raw[:start].count("\f") + 1 if "\f" in raw else None
    return GroundedCitation(
        chapter=citation.chapter,
        quote=verbatim,
        source=citation.source,
        folio=folio(page, page_offset) if page is not None else None,
    )
