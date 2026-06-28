"""Tests for the pure section chunker and folio helpers."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.chunking import chunk_sections, folio, physical_page_at  # noqa: E402


def test_chunks_cover_all_lines_contiguously():
    text = "\n".join(f"word{i} more text here" for i in range(100))  # 100 lines, ~400 words
    chunks = chunk_sections(text, target_words=50)
    assert len(chunks) > 1
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 100
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert nxt.start_line == prev.end_line + 1  # no gaps, no overlap


def test_chunk_indices_are_sequential():
    chunks = chunk_sections("\n".join(["a b c"] * 60), target_words=20)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_label_uses_strong_heading():
    text = "Chapter 3 Convolutional Codes\n" + "\n".join(["body line here"] * 5)
    chunk = chunk_sections(text, target_words=5)[0]
    assert chunk.chapter == 3
    assert "Convolutional" in chunk.label


def test_binary_string_is_not_a_heading():
    # A long digit run shaped like "N Title" must not register as a section heading.
    text = "010000011010111010111010 Decoder output\n" + "\n".join(["x y z"] * 4)
    chunk = chunk_sections(text, target_words=5)[0]
    assert chunk.chapter is None


def test_physical_page_at_counts_form_feeds():
    text = "a\nb\fc\nd"  # one form-feed inside line 2
    assert physical_page_at(text, 1) == 1
    assert physical_page_at(text, 3) == 2


def test_folio_tags_pdf_without_offset_and_remaps_with_offset():
    assert folio(5, None) == "5 (pdf)"
    assert folio(5, 3) == "2"
    assert folio(1, 5) == "1"  # floored at 1
