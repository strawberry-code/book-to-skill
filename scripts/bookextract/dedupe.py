"""Semantic reconciliation (Fase D2): fold same-concept notes with no shared slug.

The deterministic pass (``reconcile.py``) folds acronym/plural string variants;
this catches the rest — two notes that mean the same thing but share no slug or
alias (``error-correcting-code`` vs ``channel-code``). It stays dependency-free:
a cheap **token-overlap prefilter** (Jaccard on title+description) proposes only
the plausible candidate pairs, and ``claude -p`` arbitrates each — conservatively.
Cross-lingual-pure synonymy (no shared tokens) is out of scope; that needs
embeddings.

A confirmed merge renames the loser note's slug to the winner's (recording the
old slug as an alias) directly in the chunk JSON, so the existing assembler folds
the two on the next ``assemble`` — no change to the assembly engine. The model
call is the injected ``invoke``, so the prefilter and merge logic test free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from bookextract.runner import Invoke

_NoteList = list[dict[str, object]]

_WORD: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+")
_STOP: Final[frozenset[str]] = frozenset(
    {"the", "a", "an", "of", "and", "or", "to", "in", "is", "for", "with", "that", "as", "by", "on"}
)
_MIN_TOKEN: Final[int] = 3
_DEFAULT_THRESHOLD: Final[float] = 0.6


@dataclass
class DedupeReport:
    """What a semantic dedupe pass proposed and merged."""

    candidates: int = 0
    merged: int = 0
    cost_usd: float = 0.0


def _tokens(text: str) -> set[str]:
    """Content tokens of a string (lowercased, stopwords and very short words dropped)."""
    return {w for w in _WORD.findall(text.lower()) if len(w) >= _MIN_TOKEN and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard overlap of two token sets (0.0 when either is empty)."""
    return len(a & b) / len(a | b) if a and b else 0.0


def _text(note: dict[str, object]) -> str:
    """The title + description text a candidate is matched on."""
    return f"{note.get('title', '')} {note.get('description', '')}"


def candidate_pairs(notes: list[dict[str, object]], threshold: float) -> list[tuple[int, int]]:
    """Index pairs of different-slug notes whose title+description overlap ≥ ``threshold``."""
    toks = [_tokens(_text(n)) for n in notes]
    pairs: list[tuple[int, int]] = []
    for i in range(len(notes)):
        for j in range(i + 1, len(notes)):
            if notes[i].get("slug") == notes[j].get("slug"):
                continue
            if _jaccard(toks[i], toks[j]) >= threshold:
                pairs.append((i, j))
    return pairs


def build_same_prompt(a: dict[str, object], b: dict[str, object]) -> str:
    """Prompt asking whether two notes denote the same concept (conservative)."""
    return (
        "Two candidate knowledge notes may describe the SAME concept.\n\n"
        f"A) {a.get('title', '')}: {a.get('description', '')}\n"
        f"B) {b.get('title', '')}: {b.get('description', '')}\n\n"
        'Reply ONLY JSON {"same": true} if they are the same concept (one should be merged into '
        'the other), else {"same": false}. Be conservative — only true if clearly the same.'
    )


def parse_same(text: str) -> bool:
    """Parse the arbiter's reply; default to False (no merge) on anything unclear."""
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            return False
        loaded = json.loads(stripped[start : end + 1])
    return bool(loaded.get("same")) if isinstance(loaded, dict) else False


def _pick_winner(a: dict[str, object], b: dict[str, object]) -> tuple[str, str]:
    """Return (winner_slug, loser_slug): the fuller body wins, slug alpha breaks ties."""
    la, lb = len(str(a.get("body", ""))), len(str(b.get("body", "")))
    sa, sb = str(a.get("slug", "")), str(b.get("slug", ""))
    if la != lb:
        return (sa, sb) if la > lb else (sb, sa)
    return (sa, sb) if sa < sb else (sb, sa)


def _root(slug: str, merges: dict[str, str]) -> str:
    """Follow merge edges to the surviving canonical slug (cycle-guarded)."""
    seen: set[str] = set()
    cur = slug
    while cur in merges and cur not in seen:
        seen.add(cur)
        cur = merges[cur]
    return cur


def dedupe_notes(
    notes: list[dict[str, object]], invoke: Invoke, threshold: float
) -> tuple[dict[str, str], float, int]:
    """Arbitrate candidate pairs; return (loser→canonical merges, cost, candidates checked)."""
    pairs = candidate_pairs(notes, threshold)
    raw: dict[str, str] = {}
    cost = 0.0
    for i, j in pairs:
        result = invoke(build_same_prompt(notes[i], notes[j]))
        cost += result.cost_usd
        if parse_same(result.text):
            winner, loser = _pick_winner(notes[i], notes[j])
            raw[loser] = winner
    merges = {loser: _root(winner, raw) for loser, winner in raw.items()}
    return {loser: win for loser, win in merges.items() if loser != win}, cost, len(pairs)


def apply_merges(files: dict[Path, dict[str, object]], merges: dict[str, str]) -> int:
    """Rewrite loser slugs to their canonical, keeping the old slug as an alias; return count."""
    applied = 0
    for path, payload in files.items():
        changed = False
        for note in cast(_NoteList, payload.get("notes", [])):
            slug = str(note.get("slug", ""))
            if slug in merges:
                note["aliases"] = sorted({*cast("list[str]", note.get("aliases", [])), slug})
                note["slug"] = merges[slug]
                changed = True
                applied += 1
        if changed:
            payload_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            path.write_text(payload_text, encoding="utf-8")
    return applied


def dedupe_bundle(
    bundle_dir: Path, invoke: Invoke, *, threshold: float = _DEFAULT_THRESHOLD
) -> DedupeReport:
    """Token-overlap prefilter + LLM arbitration over a bundle's chunk notes; apply merges."""
    chunks_dir = bundle_dir / ".mycelia" / "chunks"
    paths = sorted(chunks_dir.glob("*.json"))
    files = {p: json.loads(p.read_text(encoding="utf-8")) for p in paths}
    notes = [n for payload in files.values() for n in cast(_NoteList, payload.get("notes", []))]
    merges, cost, checked = dedupe_notes(notes, invoke, threshold)
    apply_merges(files, merges)
    return DedupeReport(candidates=checked, merged=len(merges), cost_usd=cost)
