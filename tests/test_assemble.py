"""Tests for the deterministic note→OKF-bundle assembler."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.assemble import AssembleInputs, Source, SourceDoc, assemble  # noqa: E402
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
    inputs = AssembleInputs.single(
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


def test_acronym_folds_into_expansion(tmp_path: Path):
    raw = "binary symmetric channel definition here\nthe bsc model is described here\n"
    expansion = Note(
        type="Concept",
        slug="binary-symmetric-channel",
        title="Binary Symmetric Channel",
        description="A channel model.",
        tags=(),
        aliases=(),
        confidence="high",
        status="established",
        body="The canonical, spelled-out note.",
        related=(),
        citations=(Citation(1, "binary symmetric channel definition", "src"),),
    )
    acronym = Note(
        type="Concept",
        slug="bsc",
        title="BSC",
        description="Short form.",
        tags=(),
        aliases=(),
        confidence="high",
        status="established",
        body="x",
        related=(),
        citations=(Citation(1, "the bsc model is described", "src"),),
    )
    # acronym occurrence FIRST: the expansion's identity must still win.
    inputs = AssembleInputs.single(
        notes=[acronym, expansion], source=_SOURCE, raw_text=raw, timestamp="2026-06-28T00:00:00Z"
    )
    report = assemble(inputs, tmp_path)
    assert report.ok, report.errors
    assert report.atomic_notes == 1
    assert not (tmp_path / "concepts" / "bsc.md").exists()
    note = (tmp_path / "concepts" / "binary-symmetric-channel.md").read_text(encoding="utf-8")
    assert "title: \"Binary Symmetric Channel\"" in note  # expansion identity won
    assert "aliases: [bsc]" in note  # folded slug kept as alias
    citation_lines = [ln for ln in note.splitlines() if ln.startswith("[")]
    assert len(citation_lines) == 2  # both citations accrued


def test_plural_folds_into_singular(tmp_path: Path):
    raw = "an encoder maps messages\nseveral encoders are compared\n"
    singular = _note("encoder", related=(), quote="an encoder maps messages")
    plural = _note("encoders", related=(), quote="several encoders are compared")
    inputs = AssembleInputs.single(
        notes=[singular, plural], source=_SOURCE, raw_text=raw, timestamp="2026-06-28T00:00:00Z"
    )
    report = assemble(inputs, tmp_path)
    assert report.ok, report.errors
    assert report.atomic_notes == 1
    assert (tmp_path / "concepts" / "encoder.md").is_file()
    assert not (tmp_path / "concepts" / "encoders.md").exists()


def test_ungroundable_citation_is_dropped_not_fatal(tmp_path: Path):
    # One note cites a quote absent from raw; assemble must drop it, keep the rest.
    good = _note("alpha", related=(), quote="alpha concept text")
    bad = _note("beta", related=(), quote="this phrase is not in the source at all")
    report = _assemble([good, bad], tmp_path)
    assert report.ok, report.errors
    assert (tmp_path / "concepts" / "alpha.md").is_file()
    assert not (tmp_path / "concepts" / "beta.md").exists()  # dropped (no groundable citation)
    manifest = json.loads((tmp_path / ".mycelia.json").read_text(encoding="utf-8"))
    assert manifest["dropped"]["notes"] == 1
    log = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "uncited note" in log  # the drop is reported, not silent


def _src(slug: str) -> Source:
    return Source(
        slug=slug, title=slug.upper(), authors=("Auth",), extraction_method="plain-text",
        source_sha256="h", source_filename=f"{slug}.md", raw_rel=f"raw/{slug}/full_text.txt",
        page_offset=None,
    )


def test_same_concept_across_books_merges_with_cross_book_citations(tmp_path: Path):
    # The crux of multi-book: one concept seen in two books → one canonical note,
    # accruing a citation from each source, and a per-book reference + MOC.
    doc_a = SourceDoc(_src("book-a"), "alpha appears in book a\n")
    doc_b = SourceDoc(_src("book-b"), "alpha appears in book b\n")
    note_a = Note(
        type="Concept", slug="alpha", title="Alpha", description="The alpha.",
        tags=(), aliases=(), confidence="high", status="established",
        body="From book A.", related=(),
        citations=(Citation(1, "alpha appears in book a", "book-a"),),
    )
    note_b = Note(
        type="Concept", slug="alpha", title="Alpha", description="The alpha.",
        tags=(), aliases=(), confidence="high", status="established",
        body="From book B.", related=(),
        citations=(Citation(1, "alpha appears in book b", "book-b"),),
    )
    inputs = AssembleInputs(
        notes=[note_a, note_b], sources=(doc_a, doc_b), timestamp="2026-06-29T00:00:00Z"
    )
    report = assemble(inputs, tmp_path)
    assert report.ok, report.errors
    assert report.atomic_notes == 1  # merged across books, not duplicated
    note = (tmp_path / "concepts" / "alpha.md").read_text(encoding="utf-8")
    assert "/references/book-a.md" in note and "/references/book-b.md" in note  # both cited
    assert (tmp_path / "references" / "book-a.md").is_file()
    assert (tmp_path / "references" / "book-b.md").is_file()
    assert (tmp_path / "moc" / "book-a.md").is_file()
    assert (tmp_path / "moc" / "book-b.md").is_file()
    root = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "/references/book-a.md" in root and "/references/book-b.md" in root


def test_uncited_note_is_dropped_and_reported(tmp_path: Path):
    # A note with no groundable citation is dropped (it can't satisfy coverage) and
    # the drop is recorded — alongside a cited note that survives.
    good = _note("alpha", related=(), quote="alpha concept text")
    uncited = Note(
        type="Concept", slug="orphan", title="Orphan", description="No citation.",
        tags=(), aliases=(), confidence="high", status="established",
        body="Body.", related=(), citations=(),
    )
    report = _assemble([good, uncited], tmp_path)
    assert report.ok, report.errors
    assert not (tmp_path / "concepts" / "orphan.md").exists()
    manifest = json.loads((tmp_path / ".mycelia.json").read_text(encoding="utf-8"))
    assert manifest["dropped"]["notes"] == 1
