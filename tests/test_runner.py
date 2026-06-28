"""Tests for the headless runner — pure prompt/parse logic and the resume loop.

The subprocess call is never made here: a fake ``invoke`` is injected, so the
loop, journal/resume, and failure handling are exercised without spending tokens.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.runner import (  # noqa: E402
    BuildConfig,
    CliResult,
    build_bundle,
    build_prompt,
    extract_notes,
    run_chunk,
)


def _note_json(slug: str) -> str:
    note = {
        "type": "Concept",
        "slug": slug,
        "title": slug.title(),
        "description": "A test concept.",
        "tags": ["t"],
        "aliases": [],
        "confidence": "high",
        "status": "established",
        "body": "Body text.",
        "related": [],
        "citations": [{"chapter": 1, "quote": "some quote", "source": "src"}],
    }
    return json.dumps({"notes": [note]})


def test_build_prompt_carries_contract_and_chunk():
    prompt = build_prompt("the chunk body", "my-source", 3)
    assert "my-source" in prompt
    assert "the chunk body" in prompt
    assert "chapter 3" in prompt
    assert '"notes"' in prompt  # the JSON contract is present


def test_extract_notes_plain_json():
    assert extract_notes(_note_json("alpha"))[0]["slug"] == "alpha"


def test_extract_notes_strips_markdown_fence():
    fenced = f"```json\n{_note_json('beta')}\n```"
    assert extract_notes(fenced)[0]["slug"] == "beta"


def test_extract_notes_tolerates_leading_prose():
    noisy = f"Here are the notes:\n{_note_json('gamma')}"
    assert extract_notes(noisy)[0]["slug"] == "gamma"


def test_extract_notes_rejects_non_notes_payload():
    # A dict without a 'notes' list breaks the contract → raise so the chunk is retried.
    import pytest

    with pytest.raises(ValueError, match="notes"):
        extract_notes('{"oops": 1}')


def test_run_chunk_returns_notes_and_cost():
    def invoke(_prompt: str) -> CliResult:
        return CliResult(text=_note_json("alpha"), cost_usd=0.12)

    items, cost = run_chunk("chunk text", "src", 1, invoke)
    assert items[0]["slug"] == "alpha"
    assert cost == 0.12


def _make_bundle(tmp_path: Path, chunks: int) -> Path:
    myc = tmp_path / ".mycelia"
    (myc / "chunks").mkdir(parents=True)
    (tmp_path / "raw" / "src").mkdir(parents=True)
    raw = tmp_path / "raw" / "src" / "full_text.txt"
    raw.write_text("line one\nline two\n", encoding="utf-8")
    (myc / "source.json").write_text(
        json.dumps({"slug": "src", "raw_rel": "raw/src/full_text.txt"}), encoding="utf-8"
    )
    plan = [{"id": i, "chapter": 1, "start_line": 1, "end_line": 2} for i in range(chunks)]
    (myc / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (myc / "journal.json").write_text(json.dumps({"done": []}), encoding="utf-8")
    return tmp_path


def test_build_bundle_resumes_from_journal(tmp_path: Path):
    bundle = _make_bundle(tmp_path, chunks=2)
    calls = {"n": 0}

    def invoke(_prompt: str) -> CliResult:
        calls["n"] += 1
        return CliResult(text=_note_json(f"c{calls['n']}"), cost_usd=1.0)

    first = build_bundle(BuildConfig(bundle=bundle, max_chunks=1), invoke)
    assert first.built == 1
    assert (bundle / ".mycelia" / "chunks" / "0.json").is_file()
    assert not (bundle / ".mycelia" / "chunks" / "1.json").is_file()
    assert json.loads((bundle / ".mycelia" / "journal.json").read_text())["done"] == [0]

    second = build_bundle(BuildConfig(bundle=bundle), invoke)  # resume the rest
    assert second.built == 1  # only the remaining chunk, not chunk 0 again
    assert (bundle / ".mycelia" / "chunks" / "1.json").is_file()
    assert json.loads((bundle / ".mycelia" / "journal.json").read_text())["done"] == [0, 1]


def test_build_bundle_records_failure_without_advancing_journal(tmp_path: Path):
    bundle = _make_bundle(tmp_path, chunks=1)

    def invoke(_prompt: str) -> CliResult:
        return CliResult(text="not json at all", cost_usd=0.0)

    summary = build_bundle(BuildConfig(bundle=bundle), invoke)
    assert summary.built == 0
    assert len(summary.failed) == 1
    assert json.loads((bundle / ".mycelia" / "journal.json").read_text())["done"] == []
