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


def test_multilevel_section_heading_with_hyphenated_title():
    # Regression: a hyphenated title token must still register (isalpha() rejects '-').
    text = "2.2.3 Parity-Check Matrix\n" + "\n".join(["body line here"] * 5)
    chunk = chunk_sections(text, target_words=5)[0]
    assert chunk.chapter == 2
    assert "Parity-Check" in chunk.label


def test_page_number_running_header_is_not_a_heading():
    # "322 ACRONYMS" is a page-number + ALL-CAPS running header, not chapter 322.
    text = "322 ACRONYMS\n" + "\n".join(["body line here"] * 5)
    assert chunk_sections(text, target_words=5)[0].chapter is None


def test_prose_starting_with_chapter_word_is_not_a_heading():
    # "Chapter 2 presents…" is body prose (lowercase continuation), not a heading.
    text = "Chapter 2 presents the classical algebraic coding approach to\n" + "\n".join(
        ["body line here"] * 5
    )
    assert chunk_sections(text, target_words=5)[0].chapter is None


def test_numbered_list_item_is_not_a_heading():
    # "1. All code words … are removed from" is a list item (sentence), not a heading.
    text = "1. All code words with the first component 0 are removed from\n" + "\n".join(
        ["body line here"] * 5
    )
    assert chunk_sections(text, target_words=5)[0].chapter is None


def test_a_six_word_title_still_registers():
    # Guard the word cap doesn't reject legitimately longer real headings.
    text = "3.2 Trellis Diagram and the Viterbi Algorithm\n" + "\n".join(["body line here"] * 5)
    chunk = chunk_sections(text, target_words=5)[0]
    assert chunk.chapter == 3
    assert "Viterbi" in chunk.label


def test_formula_line_starting_with_a_digit_is_not_a_heading():
    # "1 G1,k+1 (D)" (a matrix entry) and "2 Es" (an energy term) are formulas, not titles.
    for formula in ("1 G1,k+1 (D) G1,n (D)", "2 Es"):
        text = formula + "\n" + "\n".join(["body line here"] * 5)
        assert chunk_sections(text, target_words=5)[0].chapter is None


def test_physical_page_at_counts_form_feeds():
    text = "a\nb\fc\nd"  # one form-feed inside line 2
    assert physical_page_at(text, 1) == 1
    assert physical_page_at(text, 3) == 2


def test_folio_tags_pdf_without_offset_and_remaps_with_offset():
    assert folio(5, None) == "5 (pdf)"
    assert folio(5, 3) == "2"
    assert folio(1, 5) == "1"  # floored at 1
