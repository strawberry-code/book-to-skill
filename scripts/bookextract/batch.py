"""Fuzzy-match pre-provenance skills to archived source documents for batch backfill.

The matcher is pure (text in, decisions out) so it is unit-testable without a
filesystem: it scores each skill slug against each candidate filename by how many
of the slug's significant tokens appear in the filename. Author-surname slugs match
naturally because the surname is a token in both (e.g. ``geopolitics-chapman`` ↔
"Geopolitics A Guide to the Issues … Chapman …").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Tokens too common to discriminate sources; dropped before scoring.
_STOP: Final[frozenset[str]] = frozenset(
    {"the", "of", "a", "an", "and", "for", "with", "to", "in", "on", "guide", "introduction"}
)
_TOKEN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_LEN: Final[int] = 3
_DEFAULT_THRESHOLD: Final[float] = 0.6


def _tokens(text: str) -> list[str]:
    """Lowercase significant tokens: drop stopwords and tokens shorter than 3 chars."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) >= _MIN_TOKEN_LEN]


@dataclass(frozen=True)
class Match:
    """One slug's matching decision against the candidate filenames."""

    slug: str
    source: str | None  # the chosen filename, or None when ambiguous / no confident match
    score: float  # fraction of the slug's tokens found in the best filename (0..1)
    ambiguous: bool  # True when two files tie at/above threshold (needs manual --source)


def _best_two(
    slug_tokens: list[str], file_tokens: dict[str, set[str]]
) -> tuple[float, str | None, float]:
    """Return ``(best_score, best_file, second_score)`` for one slug over all files."""
    if not slug_tokens:
        return (0.0, None, 0.0)
    scored = sorted(
        (
            (sum(t in toks for t in slug_tokens) / len(slug_tokens), name)
            for name, toks in file_tokens.items()
        ),
        reverse=True,
    )
    best_score, best_file = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    return (best_score, best_file, second_score)


def match_sources(
    slugs: list[str], filenames: list[str], *, threshold: float = _DEFAULT_THRESHOLD
) -> list[Match]:
    """Match each slug to its most likely source filename.

    A match is confident when the best filename scores at/above ``threshold`` and
    strictly beats the runner-up. A tie at/above threshold is flagged ``ambiguous``
    (``source=None``) so the caller asks for an explicit source rather than guessing.

    Args:
        slugs: Skill slugs (hyphenated), e.g. ``"hexagonal-architecture-java"``.
        filenames: Candidate source filenames in the archive.
        threshold: Minimum token-overlap fraction to accept a match.

    Returns:
        One :class:`Match` per slug, in input order.
    """
    file_tokens = {name: set(_tokens(name)) for name in filenames}
    matches: list[Match] = []
    for slug in slugs:
        slug_tokens = _tokens(slug.replace("-", " "))
        best_score, best_file, second_score = _best_two(slug_tokens, file_tokens)
        confident = best_score >= threshold and best_score > second_score
        ambiguous = best_score >= threshold and best_score == second_score
        matches.append(
            Match(
                slug=slug,
                source=best_file if confident else None,
                score=round(best_score, 3),
                ambiguous=ambiguous,
            )
        )
    return matches
