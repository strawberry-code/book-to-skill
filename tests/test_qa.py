"""Tests for the semantic faithfulness gate (B1) — parsing + the batched loop.

The model call is a fake ``invoke``; no tokens are spent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.assemble import AssembleInputs, Source, assemble  # noqa: E402
from bookextract.notes import Citation, Note  # noqa: E402
from bookextract.qa import (  # noqa: E402
    QAReport,
    Verdict,
    build_qa_prompt,
    parse_verdicts,
    read_qa_notes,
    verify_bundle,
)
from bookextract.runner import CliResult  # noqa: E402

_RAW = "alpha concept text appears here\nbeta concept text appears here\n"
_SOURCE = Source(
    slug="src", title="Test Source", authors=("Tester",), extraction_method="plain-text",
    source_sha256="abc", source_filename="t.md", raw_rel="raw/src/full_text.txt", page_offset=None,
)


def _note(slug: str, *, quote: str) -> Note:
    return Note(
        type="Concept", slug=slug, title=slug.title(), description=f"The {slug}.",
        tags=("t",), aliases=(), confidence="high", status="established",
        body=f"This note explains {slug} in detail.", related=(),
        citations=(Citation(1, quote, "src"),),
    )


def _build(tmp_path: Path) -> Path:
    inputs = AssembleInputs.single(
        notes=[
            _note("alpha", quote="alpha concept text"),
            _note("beta", quote="beta concept text"),
        ],
        source=_SOURCE, raw_text=_RAW, timestamp="2026-06-28T00:00:00Z",
    )
    assert assemble(inputs, tmp_path).ok
    return tmp_path


def test_read_qa_notes_extracts_body_and_quotes(tmp_path: Path):
    notes = {n.slug: n for n in read_qa_notes(_build(tmp_path))}
    assert set(notes) == {"alpha", "beta"}
    assert "explains alpha" in notes["alpha"].body
    assert "alpha concept text" in notes["alpha"].quotes  # recovered from # Citations


def test_build_qa_prompt_lists_each_note(tmp_path: Path):
    notes = read_qa_notes(_build(tmp_path))
    prompt = build_qa_prompt(notes)
    assert "NOTE alpha" in prompt and "NOTE beta" in prompt
    assert "verdicts" in prompt


def test_parse_verdicts_plain_and_coerces_unknown():
    text = json.dumps(
        {"verdicts": [
            {"slug": "alpha", "verdict": "supported", "reason": "ok"},
            {"slug": "beta", "verdict": "nonsense", "reason": "?"},
        ]}
    )
    out = parse_verdicts(text)
    assert out["alpha"].status == "supported"
    assert out["beta"].status == "unsupported"  # unknown verdict coerced


def test_parse_verdicts_tolerates_fence():
    fenced = '```json\n{"verdicts": [{"slug": "a", "verdict": "overreach", "reason": "x"}]}\n```'
    assert parse_verdicts(fenced)["a"].status == "overreach"


def test_verify_bundle_tallies_and_gates(tmp_path: Path):
    bundle = _build(tmp_path)

    def invoke(_prompt: str) -> CliResult:
        verdicts = {"verdicts": [
            {"slug": "alpha", "verdict": "supported", "reason": "ok"},
            {"slug": "beta", "verdict": "unsupported", "reason": "claim not in quote"},
        ]}
        return CliResult(text=json.dumps(verdicts), cost_usd=0.5)

    report = verify_bundle(bundle, invoke, batch_size=10)
    assert report.total == 2
    assert report.supported == 1 and report.unsupported == 1
    assert report.cost_usd == 0.5
    assert report.faithfulness == 0.5
    assert not report.ok(0.0)  # an unsupported note fails the gate regardless of floor
    assert ("beta", "unsupported", "claim not in quote") in report.failures


def test_missing_verdict_counts_as_unsupported(tmp_path: Path):
    bundle = _build(tmp_path)

    def invoke(_prompt: str) -> CliResult:
        # Model only returns a verdict for alpha; beta is silently dropped.
        verdicts = {"verdicts": [{"slug": "alpha", "verdict": "supported", "reason": "ok"}]}
        return CliResult(text=json.dumps(verdicts), cost_usd=0.0)

    report = verify_bundle(bundle, invoke)
    assert report.unsupported == 1  # beta defaulted to unsupported
    assert any(slug == "beta" for slug, _, _ in report.failures)


def test_clean_report_passes_gate():
    report = QAReport(total=3, supported=3)
    assert report.ok(0.9)
    assert report.faithfulness == 1.0
    _ = Verdict("supported", "")  # smoke
