"""Deterministic, dependency-free reconciliation of equivalent note slugs.

Beyond exact-slug and shared-alias dedup, this collapses two high-precision,
offline-detectable forms of the *same* concept that don't share a string:

* **acronym ↔ expansion** — a single-token slug equal to the initials of a
  multiword slug (``bsc`` ↔ ``binary-symmetric-channel``);
* **singular ↔ plural** — two slugs differing only by a trailing ``s``
  (``encoder`` ↔ ``encoders``).

It deliberately stops there. Looser stemming (``code`` ↔ ``coding``) and
cross-language or pure-semantic synonymy (``germany`` ↔ ``deutschland``) need
embeddings — a roadmap item — and a false merge (collapsing two genuinely
distinct concepts) is worse than a missed one. Both rules here are asymmetric
and string-checkable, so they almost never fire by accident.

``reconcile_slugs`` returns a map from each non-canonical slug to the canonical
slug it folds into. The assembler records the folded slug as an alias, so the
existing alias machinery resolves ``related`` links through it for free.
"""

from __future__ import annotations

from typing import Final

_MIN_EXPANSION_WORDS: Final[int] = 2  # an acronym needs ≥2 words to abbreviate
_MIN_ACRONYM_LEN: Final[int] = 2  # 1-letter "acronyms" collide with everything


def _acronym_of(slug: str) -> str:
    """Initials of a multiword (dashed) slug, or ``""`` for a single token."""
    words = [w for w in slug.split("-") if w]
    return "".join(w[0] for w in words) if len(words) >= _MIN_EXPANSION_WORDS else ""


def _winner(slug: str, slugs: set[str]) -> str | None:
    """The canonical slug ``slug`` folds into, if any (plural first, then acronym)."""
    if slug.endswith("s") and slug[:-1] in slugs:
        return slug[:-1]  # plural → singular (the shorter form wins)
    if "-" not in slug and len(slug) >= _MIN_ACRONYM_LEN:
        for other in sorted(slugs):  # sorted: deterministic when initials collide
            if "-" in other and _acronym_of(other) == slug:
                return other  # acronym → expansion (the spelled-out form wins)
    return None


def _root(slug: str, edges: dict[str, str]) -> str:
    """Follow fold edges to the canonical slug (cycle-guarded)."""
    seen: set[str] = set()
    cur = slug
    while cur in edges and cur not in seen:
        seen.add(cur)
        cur = edges[cur]
    return cur


def reconcile_slugs(slugs: set[str]) -> dict[str, str]:
    """Map each non-canonical slug to the canonical slug it should fold into."""
    edges = {s: w for s in slugs if (w := _winner(s, slugs)) is not None}
    return {s: r for s in slugs if (r := _root(s, edges)) != s}
