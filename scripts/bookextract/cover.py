"""Coverage critic (Fase B3): loop-until-dry to catch concepts the first pass missed.

A single extraction pass under-covers a dense chunk (the eval baseline showed
~67% recall — real concepts present in the text but never emitted). This module
re-reads each chunk with the already-extracted slugs in hand and asks the model
for ONLY the atomic concepts still missing, appending them and repeating until a
round finds nothing new (bounded by ``max_rounds``). It reuses the runner's
Note-JSON parsing and injected ``invoke``, so the loop is testable without spend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from bookextract.notes import NoteValidationError, validate_note
from bookextract.runner import Invoke, extract_notes

_DEFAULT_ROUNDS: Final[int] = 3


@dataclass(frozen=True)
class CoverTask:
    """The one chunk a coverage pass works on (grouped to keep arity small)."""

    chunk_text: str
    source_slug: str
    chapter: int | None


@dataclass
class CoverReport:
    """What a coverage pass added across a bundle's already-built chunks."""

    chunks: int = 0
    added: int = 0
    cost_usd: float = 0.0


def build_cover_prompt(
    chunk_text: str, known_slugs: list[str], source_slug: str, chapter: int | None
) -> str:
    """Prompt asking ONLY for atomic notes missing from ``known_slugs``."""
    known = ", ".join(known_slugs) or "(none yet)"
    label = f" (chapter {chapter})" if chapter is not None else ""
    return (
        "You are completing the atomic-note extraction of one book chunk for an OKF vault.\n"
        f"ALREADY EXTRACTED slugs — do NOT repeat any of these: {known}\n\n"
        "Emit Note JSON ONLY for atomic concepts/methods/principles/entities/frameworks that are "
        "present in the chunk but MISSING from that list. "
        'If nothing is missing, return {"notes": []}.\n'
        "Each note has fields: type, slug (kebab-case), title, description, tags, aliases, "
        "confidence (low|medium|high), status (established|contested|insufficient), body, related, "
        'and a NON-EMPTY citations list of {"chapter": <int>, '
        '"quote": "<verbatim substring copied from the chunk>", '
        f'"source": "{source_slug}"}}.\n'
        'Output ONLY {"notes": [ ... ]} — no prose, no fences.\n\n'
        f"=== CHUNK{label} ===\n{chunk_text}\n=== END CHUNK ==="
    )


def cover_chunk(
    task: CoverTask,
    known_slugs: set[str],
    invoke: Invoke,
    max_rounds: int = _DEFAULT_ROUNDS,
) -> tuple[list[dict[str, object]], float]:
    """Loop-until-dry: collect notes missing from ``known_slugs`` (returns new notes, cost)."""
    known = set(known_slugs)
    new: list[dict[str, object]] = []
    cost = 0.0
    for _ in range(max_rounds):
        prompt = build_cover_prompt(task.chunk_text, sorted(known), task.source_slug, task.chapter)
        result = invoke(prompt)
        cost += result.cost_usd
        fresh = [
            item
            for item in extract_notes(result.text)
            if isinstance(item, dict) and item.get("slug") not in known
        ]
        if not fresh:
            break
        for item in fresh:
            try:
                validate_note(item)  # shape-check; a malformed note is skipped, not fatal
            except NoteValidationError:
                continue
            known.add(cast(str, item["slug"]))
            new.append(item)
    return new, cost


def _chunk_text(lines: list[str], chunk: dict[str, object]) -> str:
    """The raw text of a plan chunk (1-based inclusive line range)."""
    start = cast(int, chunk["start_line"]) - 1
    end = cast(int, chunk["end_line"])
    return "\n".join(lines[start:end])


def cover_bundle(
    bundle_dir: Path,
    invoke: Invoke,
    *,
    max_rounds: int = _DEFAULT_ROUNDS,
    max_chunks: int | None = None,
) -> CoverReport:
    """Run the coverage critic over every already-built chunk, appending missed notes."""
    myc = bundle_dir / ".mycelia"
    source = json.loads((myc / "source.json").read_text(encoding="utf-8"))
    plan = json.loads((myc / "plan.json").read_text(encoding="utf-8"))
    raw = (bundle_dir / source["raw_rel"]).read_text(encoding="utf-8", errors="replace")
    lines = raw.split("\n")

    built = [c for c in plan if (myc / "chunks" / f"{c['id']}.json").is_file()]
    if max_chunks is not None:
        built = built[:max_chunks]

    report = CoverReport()
    for chunk in built:
        path = myc / "chunks" / f"{chunk['id']}.json"
        existing = json.loads(path.read_text(encoding="utf-8")).get("notes", [])
        known = {n.get("slug") for n in existing}
        task = CoverTask(_chunk_text(lines, chunk), source["slug"], chunk.get("chapter"))
        new, cost = cover_chunk(task, known, invoke, max_rounds)
        report.chunks += 1
        report.cost_usd += cost
        if new:
            payload = {"notes": existing + new}
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", "utf-8")
            report.added += len(new)
    return report
