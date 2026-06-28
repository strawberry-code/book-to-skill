"""Semantic QA (Fase B1): is each note's body faithful to its cited quotes?

Grounding (``notes.py``) proves a citation's quote exists verbatim in the source;
it does **not** prove the note's *body* is supported by that quote — an agent can
write a plausible body that overreaches or misreads what it cites, and the lint
gate still passes. This module closes that gap: for each atomic note it asks an
independent model whether the body's claims are entailed by the quotes it cites,
returning supported / overreach / unsupported.

The model call is the injected ``invoke`` (the same headless primitive as the
runner), so the note parsing, prompt building, verdict parsing, and batching loop
are all testable without spending tokens. Notes are verified in **batches** per
call to amortize the fixed per-call system-prompt overhead.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from bookextract.okf_lint import parse_frontmatter
from bookextract.runner import Invoke

_RESERVED: Final[frozenset[str]] = frozenset({"index.md", "log.md"})
_EXEMPT_TYPES: Final[frozenset[str]] = frozenset({"source", "moc", "schema"})
_QUOTE: Final[re.Pattern[str]] = re.compile(r'"([^"]+)"')
_H1: Final[re.Pattern[str]] = re.compile(r"^#\s+(.*)$")
_HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s")
_CITATIONS_H: Final[re.Pattern[str]] = re.compile(r"^#{1,6}\s+citations\b", re.IGNORECASE)
_VERDICTS: Final[frozenset[str]] = frozenset({"supported", "overreach", "unsupported"})
_DEFAULT_BATCH: Final[int] = 10


@dataclass(frozen=True)
class NoteForQA:
    """A note reduced to what a faithfulness check needs: its claims and its evidence."""

    slug: str
    title: str
    body: str
    quotes: tuple[str, ...]


@dataclass(frozen=True)
class Verdict:
    """One faithfulness judgement for a note."""

    status: str  # supported | overreach | unsupported
    reason: str


@dataclass
class QAReport:
    """Accumulated faithfulness results across a bundle's notes."""

    total: int = 0
    supported: int = 0
    overreach: int = 0
    unsupported: int = 0
    cost_usd: float = 0.0
    failures: list[tuple[str, str, str]] = field(default_factory=list)  # slug, verdict, reason

    @property
    def faithfulness(self) -> float:
        """Fraction of notes judged fully ``supported`` (1.0 when there are none)."""
        return 1.0 if self.total == 0 else self.supported / self.total

    def ok(self, min_faithful: float) -> bool:
        """True when no note is ``unsupported`` and faithfulness clears the floor."""
        return self.unsupported == 0 and self.faithfulness >= min_faithful


def _parse_note(text: str, slug: str) -> NoteForQA:
    """Split a rendered note into (title, body, cited quotes)."""
    title, body_lines, quotes = "", [], []
    section: str | None = None
    for line in text.splitlines():
        h1 = _H1.match(line)
        if h1 and not title:
            title, section = h1.group(1).strip(), "body"
            continue
        if _HEADING.match(line):
            section = "citations" if _CITATIONS_H.match(line) else None
            continue
        if section == "body":
            body_lines.append(line)
        elif section == "citations":
            found = _QUOTE.search(line)
            if found:
                quotes.append(found.group(1))
    return NoteForQA(slug, title, "\n".join(body_lines).strip(), tuple(quotes))


def read_qa_notes(bundle_dir: Path) -> list[NoteForQA]:
    """Read every atomic note from a built bundle as a :class:`NoteForQA`."""
    notes: list[NoteForQA] = []
    for path in sorted(bundle_dir.rglob("*.md")):
        if path.name in _RESERVED:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        note_type = (parse_frontmatter(text) or {}).get("type", "").strip().lower()
        if not note_type or note_type in _EXEMPT_TYPES:
            continue
        notes.append(_parse_note(text, path.stem))
    return notes


def build_qa_prompt(batch: list[NoteForQA]) -> str:
    """A single prompt asking for a faithfulness verdict on each note in the batch."""
    blocks = []
    for note in batch:
        quotes = "\n".join(f'- "{q}"' for q in note.quotes) or "- (none)"
        blocks.append(
            f"=== NOTE {note.slug} ===\nTITLE: {note.title}\n"
            f"BODY:\n{note.body}\nQUOTES:\n{quotes}"
        )
    body = "\n\n".join(blocks)
    return (
        "You check whether each knowledge note's body is faithful to its cited source quotes.\n"
        "For EACH note decide one verdict:\n"
        "- supported: every claim in the body is backed by the quotes (plus uncontroversial "
        "general knowledge).\n"
        "- overreach: mostly backed, but the body asserts more than the quotes justify.\n"
        "- unsupported: a key claim is not backed by (or contradicts) the quotes.\n\n"
        'Reply ONLY JSON: {"verdicts": [{"slug": "...", "verdict": "...", '
        '"reason": "<one sentence>"}]}'
        " — one entry per note, no prose, no fences.\n\n" + body
    )


def _load_json(text: str) -> dict[str, object]:
    """Parse a JSON object from model output, tolerating fences/leading prose."""
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        loaded = json.loads(stripped[start : end + 1])
    if not isinstance(loaded, dict):
        raise ValueError("expected a JSON object")
    return loaded


def parse_verdicts(text: str) -> dict[str, Verdict]:
    """Map slug → :class:`Verdict` from the model's batch reply."""
    items = _load_json(text).get("verdicts")
    if not isinstance(items, list):
        raise ValueError("reply has no 'verdicts' list")
    out: dict[str, Verdict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("verdict", "")).lower().strip()
        if status not in _VERDICTS:
            status = "unsupported"
        out[str(item.get("slug", ""))] = Verdict(status, str(item.get("reason", "")))
    return out


def _tally(report: QAReport, slug: str, verdict: Verdict) -> None:
    """Fold one verdict into the report, recording non-supported notes as failures."""
    report.total += 1
    setattr(report, verdict.status, getattr(report, verdict.status) + 1)
    if verdict.status != "supported":
        report.failures.append((slug, verdict.status, verdict.reason))


def verify_bundle(
    bundle_dir: Path,
    invoke: Invoke,
    *,
    batch_size: int = _DEFAULT_BATCH,
    max_notes: int | None = None,
) -> QAReport:
    """Judge faithfulness of every atomic note (batched per call), returning a report."""
    notes = read_qa_notes(bundle_dir)
    if max_notes is not None:
        notes = notes[:max_notes]
    report = QAReport()
    for start in range(0, len(notes), max(1, batch_size)):
        batch = notes[start : start + batch_size]
        result = invoke(build_qa_prompt(batch))
        report.cost_usd += result.cost_usd
        verdicts = parse_verdicts(result.text)
        for note in batch:
            _tally(report, note.slug, verdicts.get(note.slug, Verdict("unsupported", "no verdict")))
    return report


def format_qa(report: QAReport) -> str:
    """Render a :class:`QAReport` as human-readable text."""
    lines = [
        f"Faithfulness: {report.faithfulness:.0%} "
        f"({report.supported}/{report.total} supported; "
        f"{report.overreach} overreach, {report.unsupported} unsupported). "
        f"Cost: ${report.cost_usd:.4f}.",
    ]
    lines.extend(
        f"   {status.upper()} {slug}: {reason}" for slug, status, reason in report.failures
    )
    return "\n".join(lines)
