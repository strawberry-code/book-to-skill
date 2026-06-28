"""Headless orchestration: drive ``claude -p`` to emit Note JSON per chunk.

Inverts the in-session manual emission (MYCELIA.md) into an unattended loop the
code owns: for each pending chunk it builds a fixed-prefix prompt (the Note-JSON
contract + the chunk text), invokes ``claude -p --model opus --output-format
json``, extracts the notes from the model's ``result``, and writes them where the
assembler expects. The journal makes the loop resumable and idempotent.

The subprocess call (``invoke_claude``) is the only side-effecting primitive and
is injected into :func:`run_chunk` / :func:`build_bundle`, so the prompt-building,
JSON-extraction, and loop/resume logic are all testable without spending tokens.
The fixed instruction prefix is identical across chunks of a book so Claude's
prompt cache amortizes the per-call system-prompt overhead.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, cast

from bookextract.notes import validate_note

_MODEL_DEFAULT: Final[str] = "opus"
_FENCE: Final[str] = "```"
_DEFAULT_TIMEOUT: Final[int] = 600
_ERR_PREVIEW: Final[int] = 200

INSTRUCTIONS: Final[str] = """\
You extract atomic knowledge notes from one book chunk for an OKF knowledge vault.

Output ONLY a JSON object {{"notes": [ ... ]}} — no prose, no fences, no tool use.
Each note object has exactly these fields:
- type: one of Concept, Framework, Principle, Entity, Method, AntiPattern
- slug: kebab-case unique id (e.g. "binary-symmetric-channel")
- title: short human-readable title
- description: one sentence
- tags: list of short tags (may be [])
- aliases: list of alternative names/acronyms, e.g. ["bsc"] (use [] if none)
- confidence: one of low, medium, high
- status: one of established, contested, insufficient
- body: 2-5 sentences in your own words, faithful to the chunk
- related: slugs of other notes in THIS chunk that this note connects to
- citations: NON-EMPTY list; each item is
    {{"chapter": <int>, "quote": "<verbatim substring from the chunk>", "source": "{source_slug}"}}

Rules:
- Each quote MUST be copied verbatim from the chunk (checked byte-for-byte against the source).
- Be EXHAUSTIVE: one note per distinct atomic concept/method/principle/entity/framework.
- Prefer the spelled-out form as the slug; put any acronym in aliases.
- Use the source slug exactly: {source_slug}."""


class RunnerError(Exception):
    """A ``claude -p`` invocation failed or returned something unusable."""


@dataclass(frozen=True)
class CliResult:
    """The text and billed cost of one ``claude -p`` call."""

    text: str
    cost_usd: float


@dataclass(frozen=True)
class BuildConfig:
    """Inputs for an unattended build over a bundle's pending chunks."""

    bundle: Path
    model: str = _MODEL_DEFAULT
    max_chunks: int | None = None
    timeout: int = _DEFAULT_TIMEOUT


@dataclass
class BuildSummary:
    """What a build run produced (mutable: accumulated across chunks)."""

    built: int = 0
    notes: int = 0
    cost_usd: float = 0.0
    failed: list[tuple[int, str]] = field(default_factory=list)


def build_prompt(chunk_text: str, source_slug: str, chapter: int | None) -> str:
    """The full ``claude -p`` prompt: fixed Note-JSON contract + the chunk body."""
    head = INSTRUCTIONS.format(source_slug=source_slug)
    label = f" (chapter {chapter})" if chapter is not None else ""
    return f"{head}\n\n=== CHUNK{label} ===\n{chunk_text}\n=== END CHUNK ==="


def _strip_fences(text: str) -> str:
    """Remove a leading ```/```json fence and its closing fence, if present."""
    stripped = text.strip()
    if not stripped.startswith(_FENCE):
        return stripped
    body = stripped[len(_FENCE) :]
    body = body.split("\n", 1)[1] if "\n" in body else ""
    end = body.rfind(_FENCE)
    return (body[:end] if end >= 0 else body).strip()


def extract_notes(result_text: str) -> list[dict[str, object]]:
    """Parse the model's result into a list of raw note dicts (fence/prose tolerant)."""
    text = _strip_fences(result_text)
    try:
        payload: object = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    items = payload.get("notes") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("model output has no 'notes' list")
    return items


def invoke_claude(prompt: str, model: str, *, timeout: int = _DEFAULT_TIMEOUT) -> CliResult:
    """Run ``claude -p`` headlessly and return its result text + billed cost."""
    cmd = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"claude -p failed to run: {exc}") from exc
    if proc.returncode != 0:
        raise RunnerError(f"claude -p exited {proc.returncode}: {proc.stderr[:_ERR_PREVIEW]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RunnerError(f"claude -p non-JSON output: {proc.stdout[:_ERR_PREVIEW]}") from exc
    if data.get("is_error"):
        detail = str(data.get("result", ""))[:_ERR_PREVIEW]
        raise RunnerError(f"claude -p reported an error: {detail}")
    cost = float(data.get("total_cost_usd") or 0.0)
    return CliResult(text=str(data.get("result", "")), cost_usd=cost)


# A model-bound invocation: takes the prompt, returns the result text + cost. The
# model/timeout are bound by the caller so per-chunk code stays model-agnostic.
Invoke = Callable[[str], CliResult]


def run_chunk(
    chunk_text: str, source_slug: str, chapter: int | None, invoke: Invoke
) -> tuple[list[dict[str, object]], float]:
    """Emit + shape-validate the notes for one chunk; returns (note dicts, cost)."""
    result = invoke(build_prompt(chunk_text, source_slug, chapter))
    items = extract_notes(result.text)
    for item in items:
        validate_note(item)  # fail fast on a malformed note before it reaches the journal
    return items, result.cost_usd


def _chunk_text(lines: list[str], chunk: dict[str, object]) -> str:
    """The raw text of a plan chunk (1-based inclusive line range)."""
    start = cast(int, chunk["start_line"]) - 1
    end = cast(int, chunk["end_line"])
    return "\n".join(lines[start:end])


def load_raw_by_source(bundle_dir: Path) -> dict[str, list[str]]:
    """Map each book's slug to its raw text split into lines (multi- or single-book)."""
    myc = bundle_dir / ".mycelia"
    multi = myc / "sources.json"
    if multi.is_file():
        entries = json.loads(multi.read_text(encoding="utf-8"))
    else:
        entries = [json.loads((myc / "source.json").read_text(encoding="utf-8"))]
    out: dict[str, list[str]] = {}
    for entry in entries:
        raw = (bundle_dir / entry["raw_rel"]).read_text(encoding="utf-8", errors="replace")
        out[entry["slug"]] = raw.split("\n")
    return out


def _chunk_source(chunk: dict[str, object], default_slug: str) -> str:
    """The book slug a chunk belongs to (``source`` field, else the sole/first book)."""
    return cast(str, chunk.get("source") or default_slug)


def build_bundle(cfg: BuildConfig, invoke: Invoke) -> BuildSummary:
    """Run ``invoke`` over every pending chunk, writing notes + advancing the journal."""
    myc = cfg.bundle / ".mycelia"
    plan = json.loads((myc / "plan.json").read_text(encoding="utf-8"))
    journal_path = myc / "journal.json"
    done = set(json.loads(journal_path.read_text(encoding="utf-8")).get("done", []))
    raw_by_source = load_raw_by_source(cfg.bundle)
    default_slug = next(iter(raw_by_source), "")

    pending = [c for c in plan if c["id"] not in done]
    if cfg.max_chunks is not None:
        pending = pending[: cfg.max_chunks]

    summary = BuildSummary()
    for chunk in pending:
        slug = _chunk_source(chunk, default_slug)
        lines = raw_by_source.get(slug, [])
        try:
            items, cost = run_chunk(
                _chunk_text(lines, chunk), slug, chunk.get("chapter"), invoke
            )
        except (RunnerError, ValueError, json.JSONDecodeError) as exc:
            summary.failed.append((cast(int, chunk["id"]), str(exc)))
            continue
        out = myc / "chunks" / f"{chunk['id']}.json"
        out.write_text(json.dumps({"notes": items}, indent=2, ensure_ascii=False) + "\n", "utf-8")
        done.add(chunk["id"])
        journal_path.write_text(json.dumps({"done": sorted(done)}, indent=2) + "\n", "utf-8")
        summary.built += 1
        summary.notes += len(items)
        summary.cost_usd += cost
    return summary
