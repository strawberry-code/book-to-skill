"""Tests for the deterministic note→OKF-bundle assembler."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.assemble import AssembleInputs, Source, assemble  # noqa: E402
from bookextract.notes import Citation, Note  # noqa: E402

_RAW = "alpha concept text appears here\nbeta concept text appears here\n"
_SOURCE = Source(
    slug="src",
    title="Test Source",
    authors=("Tester",),
    extraction_method="plain-text",
    source_sha256="abc123",
    source_filename="t.md",
    raw_rel="raw/src/full_text.txt",
    page_offset=None,
)


def _note(slug: str, *, related: tuple[str, ...], quote: str, body: str = "Body.") -> Note:
    return Note(
        type="Concept",
        slug=slug,
        title=slug.title(),
        description=f"The {slug}.",
        tags=("t",),
        aliases=(),
        confidence="high",
        status="established",
        body=body,
        related=related,
        citations=(Citation(1, quote, "src"),),
    )


def _assemble(notes: list[Note], tmp_path: Path):
    inputs = AssembleInputs(
        notes=notes, source=_SOURCE, raw_text=_RAW, timestamp="2026-06-28T00:00:00Z"
    )
    return assemble(inputs, tmp_path)


def test_assemble_writes_a_clean_bundle(tmp_path: Path):
    a = _note("alpha", related=("beta",), quote="alpha concept text")
    b = _note("beta", related=("alpha",), quote="beta concept text")
    report = _assemble([a, b], tmp_path)
    assert report.ok, report.errors
    assert (tmp_path / "concepts" / "alpha.md").is_file()
    assert (tmp_path / "references" / "src.md").is_file()
    assert (tmp_path / "index.md").is_file()
    assert report.atomic_notes == 2
    assert report.coverage == 1.0


def test_code_inserts_reciprocal_backlink(tmp_path: Path):
    # alpha -> beta, but beta declares no related; the assembler must add the backlink.
    a = _note("alpha", related=("beta",), quote="alpha concept text")
    b = _note("beta", related=(), quote="beta concept text")
    report = _assemble([a, b], tmp_path)
    assert report.ok, report.errors
    beta = (tmp_path / "concepts" / "beta.md").read_text(encoding="utf-8")
    assert "/concepts/alpha.md" in beta  # reciprocal link inserted by code


def test_dedupe_merges_same_slug_across_chunks(tmp_path: Path):
    first = _note("alpha", related=(), quote="alpha concept text")
    second = _note("alpha", related=(), quote="concept text appears")  # same slug, new citation
    report = _assemble([first, second], tmp_path)
    assert report.ok, report.errors
    assert report.atomic_notes == 1  # one canonical note, not two
    alpha = (tmp_path / "concepts" / "alpha.md").read_text(encoding="utf-8")
    citation_lines = [ln for ln in alpha.splitlines() if ln.startswith("[")]
    assert len(citation_lines) == 2  # both sources accrued on the one note


def test_gate_flags_an_uncited_note(tmp_path: Path):
    uncited = Note(
        type="Concept",
        slug="orphan",
        title="Orphan",
        description="No citation.",
        tags=(),
        aliases=(),
        confidence="high",
        status="established",
        body="Body.",
        related=(),
        citations=(),
    )
    report = _assemble([uncited], tmp_path)
    assert not report.ok  # the lint gate catches the missing citation
