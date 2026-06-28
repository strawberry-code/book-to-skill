"""Tests for semantic dedupe (D2) — prefilter + arbitration + merge application."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.dedupe import (  # noqa: E402
    apply_merges,
    candidate_pairs,
    dedupe_bundle,
    dedupe_notes,
    parse_same,
)
from bookextract.runner import CliResult  # noqa: E402


def _n(slug: str, title: str, desc: str, body: str = "body") -> dict[str, object]:
    return {"slug": slug, "title": title, "description": desc, "body": body, "aliases": []}


def test_prefilter_pairs_only_high_overlap():
    notes = [
        _n("error-correcting-code", "Error Correcting Code", "a code that corrects channel errors"),
        _n("channel-code", "Channel Code", "a code that corrects channel errors reliably"),
        _n("entropy", "Entropy", "a measure of information uncertainty"),
    ]
    pairs = candidate_pairs(notes, threshold=0.5)
    assert (0, 1) in pairs  # the two near-identical descriptions
    assert (0, 2) not in pairs and (1, 2) not in pairs  # entropy shares nothing


def test_parse_same_tolerant_and_conservative():
    assert parse_same('{"same": true}') is True
    assert parse_same('```json\n{"same": false}\n```') is False
    assert parse_same("garbage, no json") is False  # default to no-merge


def test_dedupe_notes_merges_confirmed_pair_fuller_body_wins():
    long_body = "x" * 50
    notes = [
        _n("channel-code", "Channel Code", "corrects channel errors", body="short"),
        _n("error-correcting-code", "Error Correcting Code", "corrects channel errors", long_body),
    ]

    def invoke(_prompt: str) -> CliResult:
        return CliResult(text='{"same": true}', cost_usd=0.3)

    merges, cost, checked = dedupe_notes(notes, invoke, threshold=0.5)
    assert checked == 1
    assert merges == {"channel-code": "error-correcting-code"}  # longer body is canonical
    assert cost == 0.3


def test_dedupe_notes_respects_negative_verdict():
    notes = [
        _n("a-thing", "A Thing", "corrects channel errors"),
        _n("b-thing", "B Thing", "corrects channel errors"),
    ]

    def invoke(_prompt: str) -> CliResult:
        return CliResult(text='{"same": false}', cost_usd=0.1)

    merges, _cost, checked = dedupe_notes(notes, invoke, threshold=0.5)
    assert checked == 1
    assert merges == {}  # arbiter said no → no merge


def test_apply_merges_renames_slug_and_keeps_alias(tmp_path: Path):
    path = tmp_path / "0.json"
    notes = [_n("channel-code", "Channel Code", "d"), _n("entropy", "Entropy", "d")]
    path.write_text(json.dumps({"notes": notes}), encoding="utf-8")
    files = {path: json.loads(path.read_text())}
    applied = apply_merges(files, {"channel-code": "error-correcting-code"})
    assert applied == 1
    saved = json.loads(path.read_text())
    renamed = {n["slug"]: n for n in saved["notes"]}
    assert "error-correcting-code" in renamed
    assert "channel-code" in renamed["error-correcting-code"]["aliases"]  # old slug kept
    assert "entropy" in renamed  # untouched


def test_dedupe_bundle_end_to_end(tmp_path: Path):
    chunks = tmp_path / ".mycelia" / "chunks"
    chunks.mkdir(parents=True)
    notes = [
        _n("channel-code", "Channel Code", "corrects channel errors", body="short"),
        _n("error-correcting-code", "Error Correcting Code", "corrects channel errors", "x" * 30),
    ]
    (chunks / "0.json").write_text(json.dumps({"notes": notes}), encoding="utf-8")

    def invoke(_prompt: str) -> CliResult:
        return CliResult(text='{"same": true}', cost_usd=0.5)

    report = dedupe_bundle(tmp_path, invoke, threshold=0.5)
    assert report.merged == 1
    saved = json.loads((chunks / "0.json").read_text())
    slugs = {n["slug"] for n in saved["notes"]}
    assert slugs == {"error-correcting-code"}  # both now share the canonical slug
