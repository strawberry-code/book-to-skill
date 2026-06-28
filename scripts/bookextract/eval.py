"""Deterministic evaluation of a built OKF bundle against a gold standard.

The other modules guarantee a bundle is *well-formed* (``okf_lint``) and that its
citations are *grounded* (``notes``); this one measures whether it captured the
*right knowledge*. Given a hand-curated gold spec — the concepts that must appear
(each with acceptable aliases), the links that must exist, and an optional fact
anchor per concept — it reports concept recall, link recall, and fact-anchor
coverage. It is the ruler every quality change is judged by; the semantic
faithfulness rate it leaves as a hook is filled by the QA pass (Fase B1).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bookextract.okf_lint import parse_frontmatter

_RESERVED: Final[frozenset[str]] = frozenset({"index.md", "log.md"})
_EXEMPT_TYPES: Final[frozenset[str]] = frozenset({"source", "moc", "schema"})
_LINK: Final[re.Pattern[str]] = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_RELATED_HEADING: Final[re.Pattern[str]] = re.compile(r"^##\s+Related\b", re.IGNORECASE)
_HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,2}\s")
_SLUG_LINK: Final[re.Pattern[str]] = re.compile(r"/([a-z0-9-]+)\.md")
_WS: Final[re.Pattern[str]] = re.compile(r"\s+")
_MISSING_PREVIEW: Final[int] = 12  # cap how many misses are listed in the report


def _norm(value: str) -> str:
    """NFKC + casefold + whitespace-collapse — the comparable form for matching."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


@dataclass(frozen=True)
class BundleNote:
    """An atomic note read back from a built bundle (for evaluation only)."""

    slug: str
    keys: frozenset[str]  # normalized slug + aliases
    related: frozenset[str]  # target slugs linked from ## Related
    text: str


@dataclass(frozen=True)
class GoldConcept:
    """A concept the bundle must contain, with acceptable aliases and a fact probe."""

    slug: str
    aliases: tuple[str, ...]
    fact_anchor: str | None


@dataclass(frozen=True)
class Gold:
    """The hand-curated expectation a bundle is scored against."""

    concepts: tuple[GoldConcept, ...]
    links: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EvalReport:
    """Scored metrics plus the specific misses, for acting on the gaps."""

    concepts_total: int
    concepts_found: int
    links_total: int
    links_found: int
    facts_total: int
    facts_found: int
    missing_concepts: tuple[str, ...]
    missing_links: tuple[tuple[str, str], ...]
    unanchored: tuple[str, ...]

    @staticmethod
    def _ratio(found: int, total: int) -> float:
        return 1.0 if total == 0 else found / total

    @property
    def concept_recall(self) -> float:
        return self._ratio(self.concepts_found, self.concepts_total)

    @property
    def link_recall(self) -> float:
        return self._ratio(self.links_found, self.links_total)

    @property
    def fact_coverage(self) -> float:
        return self._ratio(self.facts_found, self.facts_total)

    def ok(self, min_recall: float) -> bool:
        """True when concept recall clears ``min_recall`` (the headline gate)."""
        return self.concept_recall >= min_recall


def _aliases(fields: dict[str, str]) -> list[str]:
    """Parse the frontmatter ``aliases: [a, b]`` scalar into a list."""
    inner = fields.get("aliases", "").strip().strip("[]")
    return [a.strip() for a in inner.split(",") if a.strip()]


def _related_slugs(text: str) -> frozenset[str]:
    """Target slugs linked from a note's ``## Related`` section."""
    out: set[str] = set()
    in_section = False
    for line in text.splitlines():
        if _HEADING.match(line):
            in_section = bool(_RELATED_HEADING.match(line))
            continue
        if in_section:
            for match in _LINK.finditer(line):
                slug = _SLUG_LINK.search(match.group(1))
                if slug:
                    out.add(slug.group(1))
    return frozenset(out)


def read_notes(bundle_dir: Path) -> list[BundleNote]:
    """Read every atomic note (typed, non-reserved, non-exempt) from a built bundle."""
    notes: list[BundleNote] = []
    for path in sorted(bundle_dir.rglob("*.md")):
        if path.name in _RESERVED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fields = parse_frontmatter(text)
        note_type = (fields or {}).get("type", "").strip().lower()
        if not fields or not note_type or note_type in _EXEMPT_TYPES:
            continue
        keys = frozenset(_norm(k) for k in (path.stem, *_aliases(fields)))
        notes.append(BundleNote(path.stem, keys, _related_slugs(text), text))
    return notes


def load_gold(path: Path) -> Gold:
    """Load a gold spec from JSON (``concepts`` with aliases/fact_anchor, ``links``)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    concepts = tuple(
        GoldConcept(c["slug"], tuple(c.get("aliases", [])), c.get("fact_anchor"))
        for c in data.get("concepts", [])
    )
    links = tuple((a, b) for a, b in data.get("links", []))
    return Gold(concepts, links)


def _index(notes: list[BundleNote]) -> dict[str, BundleNote]:
    """Map every note key (slug/alias) to its note for O(1) gold lookup."""
    idx: dict[str, BundleNote] = {}
    for note in notes:
        for key in note.keys:
            idx.setdefault(key, note)
    return idx


def _match(concept: GoldConcept, idx: dict[str, BundleNote]) -> BundleNote | None:
    """The bundle note a gold concept resolves to (by slug or any alias), if present."""
    for key in (_norm(concept.slug), *(_norm(a) for a in concept.aliases)):
        if key in idx:
            return idx[key]
    return None


def _linked(src: BundleNote | None, tgt: BundleNote | None) -> bool:
    """True when ``src``'s Related section links to ``tgt`` (either direction is checked)."""
    return src is not None and tgt is not None and tgt.slug in src.related


def evaluate(notes: list[BundleNote], gold: Gold) -> EvalReport:
    """Score a bundle's notes against the gold spec into an :class:`EvalReport`."""
    idx = _index(notes)
    matched = {c.slug: _match(c, idx) for c in gold.concepts}
    missing_concepts = tuple(c.slug for c in gold.concepts if matched[c.slug] is None)

    facts_total = facts_found = 0
    unanchored: list[str] = []
    for concept in gold.concepts:
        if not concept.fact_anchor:
            continue
        facts_total += 1
        note = matched[concept.slug]
        if note is not None and _norm(concept.fact_anchor) in _norm(note.text):
            facts_found += 1
        else:
            unanchored.append(concept.slug)

    missing_links: list[tuple[str, str]] = []
    for a, b in gold.links:
        na, nb = idx.get(_norm(a)), idx.get(_norm(b))
        if not (_linked(na, nb) or _linked(nb, na)):
            missing_links.append((a, b))

    return EvalReport(
        concepts_total=len(gold.concepts),
        concepts_found=len(gold.concepts) - len(missing_concepts),
        links_total=len(gold.links),
        links_found=len(gold.links) - len(missing_links),
        facts_total=facts_total,
        facts_found=facts_found,
        missing_concepts=missing_concepts,
        missing_links=tuple(missing_links),
        unanchored=tuple(unanchored),
    )


def format_eval(report: EvalReport) -> str:
    """Render an :class:`EvalReport` as human-readable text."""
    lines = [
        f"Concept recall: {report.concept_recall:.0%} "
        f"({report.concepts_found}/{report.concepts_total})",
        f"Link recall:    {report.link_recall:.0%} ({report.links_found}/{report.links_total})",
        f"Fact coverage:  {report.fact_coverage:.0%} ({report.facts_found}/{report.facts_total})",
    ]
    if report.missing_concepts:
        shown = ", ".join(report.missing_concepts[:_MISSING_PREVIEW])
        lines.append(f"Missing concepts: {shown}")
    if report.missing_links:
        shown = ", ".join(f"{a}~{b}" for a, b in report.missing_links[:_MISSING_PREVIEW])
        lines.append(f"Missing links: {shown}")
    if report.unanchored:
        lines.append(f"Fact anchor not found: {', '.join(report.unanchored[:_MISSING_PREVIEW])}")
    return "\n".join(lines)
