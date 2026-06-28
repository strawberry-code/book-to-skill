"""Tests for the coverage critic (B3) — the loop-until-dry logic with a fake invoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.cover import CoverTask, build_cover_prompt, cover_bundle, cover_chunk  # noqa: E402
from bookextract.runner import CliResult  # noqa: E402


def _note_json(slug: str) -> dict[str, object]:
    return {
        "type": "Concept", "slug": slug, "title": slug.title(), "description": "x.",
        "tags": [], "aliases": [], "confidence": "high", "status": "established",
        "body": "Body.", "related": [],
        "citations": [{"chapter": 1, "quote": "q", "source": "src"}],
    }


def test_build_cover_prompt_lists_known_and_chunk():
    prompt = build_cover_prompt("chunk body here", ["alpha", "beta"], "src", 2)
    assert "alpha, beta" in prompt
    assert "chunk body here" in prompt
    assert "MISSING" in prompt


def test_cover_chunk_stops_when_a_round_is_dry():
    rounds = iter([
        CliResult(text=json.dumps({"notes": [_note_json("gamma")]}), cost_usd=1.0),
        CliResult(text=json.dumps({"notes": []}), cost_usd=1.0),  # dry → stop
    ])

    def invoke(_prompt: str) -> CliResult:
        return next(rounds)

    new, cost = cover_chunk(CoverTask("text", "src", 1), {"alpha"}, invoke, max_rounds=5)
    assert [n["slug"] for n in new] == ["gamma"]
    assert cost == 2.0  # two rounds happened (the second was the dry stop)


def test_cover_chunk_dedupes_repeats_and_respects_max_rounds():
    # The model keeps returning an already-known slug → no fresh notes → stop on round 1.
    def invoke(_prompt: str) -> CliResult:
        return CliResult(text=json.dumps({"notes": [_note_json("alpha")]}), cost_usd=0.5)

    new, cost = cover_chunk(CoverTask("text", "src", 1), {"alpha"}, invoke, max_rounds=4)
    assert new == []
    assert cost == 0.5  # stopped after the first (dry-of-fresh) round


def _bundle_with_chunk(tmp_path: Path) -> Path:
    myc = tmp_path / ".mycelia"
    (myc / "chunks").mkdir(parents=True)
    (tmp_path / "raw" / "src").mkdir(parents=True)
    (tmp_path / "raw" / "src" / "full_text.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
    (myc / "source.json").write_text(
        json.dumps({"slug": "src", "raw_rel": "raw/src/full_text.txt"}), encoding="utf-8"
    )
    (myc / "plan.json").write_text(
        json.dumps([{"id": 0, "chapter": 1, "start_line": 1, "end_line": 3}]), encoding="utf-8"
    )
    (myc / "chunks" / "0.json").write_text(
        json.dumps({"notes": [_note_json("alpha")]}), encoding="utf-8"
    )
    return tmp_path


def test_cover_bundle_appends_to_chunk_file(tmp_path: Path):
    bundle = _bundle_with_chunk(tmp_path)
    rounds = iter([
        CliResult(text=json.dumps({"notes": [_note_json("delta")]}), cost_usd=1.0),
        CliResult(text=json.dumps({"notes": []}), cost_usd=0.0),
    ])

    def invoke(_prompt: str) -> CliResult:
        return next(rounds)

    report = cover_bundle(bundle, invoke, max_rounds=3)
    assert report.chunks == 1
    assert report.added == 1
    saved = json.loads((bundle / ".mycelia" / "chunks" / "0.json").read_text())
    assert [n["slug"] for n in saved["notes"]] == ["alpha", "delta"]  # appended, original kept


def test_cover_bundle_skips_unbuilt_chunks(tmp_path: Path):
    bundle = _bundle_with_chunk(tmp_path)
    # Add a planned-but-unbuilt chunk (no chunks/1.json) — it must be skipped.
    plan = json.loads((bundle / ".mycelia" / "plan.json").read_text())
    plan.append({"id": 1, "chapter": 1, "start_line": 1, "end_line": 3})
    (bundle / ".mycelia" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")

    def invoke(_prompt: str) -> CliResult:
        return CliResult(text=json.dumps({"notes": []}), cost_usd=0.0)

    report = cover_bundle(bundle, invoke)
    assert report.chunks == 1  # only the built chunk 0 was processed
