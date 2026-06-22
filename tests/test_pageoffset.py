"""Tests for front-matter page-offset detection and citation remapping (#11)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.pageoffset import detect_page_offset, remap_citations  # noqa: E402


def _doc(anchors: dict[int, str], total: int) -> str:
    """Build a form-feed-delimited document with ``anchors`` at 1-based page indices."""
    pages = [""] * total
    for index, text in anchors.items():
        pages[index - 1] = text
    return "\f".join(pages)


def _chapter_page(number: int, folio: int) -> str:
    """A physical page whose first line is a chapter heading and footer prints the folio."""
    return f"Chapter {number}\nlorem ipsum body text\n{folio}"


# --- detection -------------------------------------------------------------


def test_detects_unanimous_offset():
    # Folios 10/20/30 printed at physical pages 14/24/34 → offset 4, three agreeing anchors.
    text = _doc({14: _chapter_page(1, 10), 24: _chapter_page(2, 20), 34: _chapter_page(3, 30)}, 40)
    assert detect_page_offset(text) == 4


def test_no_form_feed_returns_none():
    assert detect_page_offset("Chapter 1\nbody\n10 plain text, no page breaks") is None


def test_chapter_number_not_mistaken_for_folio():
    # The "3" in "Chapter 3" must not vote as a folio (offset would be phys-3, wrong).
    text = _doc({34: _chapter_page(3, 30), 44: _chapter_page(4, 40), 54: _chapter_page(5, 50)}, 60)
    assert detect_page_offset(text) == 4


def test_toc_and_preface_pages_are_not_anchors():
    # A ToC page lists many "Chapter N ... folio" lines but is not a chapter start;
    # anchoring on the *first* line (here "Table of Contents") excludes it.
    toc = "Table of Contents\nChapter 1 .... 1\nChapter 2 .... 11\nChapter 3 .... 21\n5"
    preface = "Preface\nChapter 2, Wrapping Rules, describes Domain Entities\nxvii"
    text = _doc(
        {
            6: toc,
            7: preface,
            14: _chapter_page(1, 10),
            24: _chapter_page(2, 20),
            34: _chapter_page(3, 30),
        },
        40,
    )
    assert detect_page_offset(text) == 4  # only the three real anchors vote


def test_too_few_anchors_returns_none():
    text = _doc({14: _chapter_page(1, 10), 24: _chapter_page(2, 20)}, 30)
    assert detect_page_offset(text) is None  # 2 anchors < _MIN_AGREE


def test_disagreeing_anchors_return_none():
    # No strict majority: offsets 4, 4, 9, 9 → modal count 2 of 4, not a majority.
    text = _doc(
        {
            14: _chapter_page(1, 10),
            24: _chapter_page(2, 20),
            34: _chapter_page(3, 25),
            44: _chapter_page(4, 35),
        },
        50,
    )
    assert detect_page_offset(text) is None


def test_negative_offset_rejected():
    # Folio greater than the physical index → negative offset → not trustworthy.
    text = _doc({4: _chapter_page(1, 10), 5: _chapter_page(2, 11), 6: _chapter_page(3, 12)}, 10)
    assert detect_page_offset(text) is None


# --- remapping -------------------------------------------------------------


def test_remap_known_offset_subtracts():
    out, n = remap_citations('See [Ch 1, p.21] "quote" and [Ch 3, p.41] "x".', 12)
    assert out == 'See [Ch 1, p.9] "quote" and [Ch 3, p.29] "x".'
    assert n == 2


def test_remap_floors_at_one():
    out, _ = remap_citations("[Ch 1, p.3]", 12)  # 3 - 12 would be negative
    assert out == "[Ch 1, p.1]"


def test_remap_none_labels_physical_and_is_idempotent():
    once, n = remap_citations("[Ch 2, p.34]", None)
    assert once == "[Ch 2, p.34 (pdf)]"
    assert n == 1
    twice, n2 = remap_citations(once, None)
    assert twice == once  # already labelled → no double "(pdf)"
    assert n2 == 0


def test_remap_leaves_prose_pages_untouched():
    # A bare "p.21" outside a [Ch …] bracket must not be rewritten.
    out, n = remap_citations("turn to p.21 of the manual", 12)
    assert out == "turn to p.21 of the manual"
    assert n == 0


def test_remap_chapter_only_citation_untouched():
    out, n = remap_citations('[Ch 5] "SQL injection"', 12)
    assert out == '[Ch 5] "SQL injection"'
    assert n == 0


# --- transform integration -------------------------------------------------


def test_page_offset_transform_rewrites_and_records(tmp_path: Path):
    from bookextract.cli import _page_offset_transform

    skill = tmp_path / "demo-skill"
    (skill / "chapters").mkdir(parents=True)
    (skill / ".source").mkdir()
    (skill / "chapters" / "ch01-intro.md").write_text('A [Ch 1, p.21] "q".\n', encoding="utf-8")
    (skill / "glossary.md").write_text('Term [Ch 1, p.23] "d".\n', encoding="utf-8")
    (skill / ".source" / "metadata.json").write_text(json.dumps({"page_offset": 12}))
    (skill / ".book-to-skill.json").write_text(json.dumps({"generator_version": "1.2.0"}))

    changed = _page_offset_transform(skill, skill / ".source")

    assert sorted(changed) == ["chapters/ch01-intro.md", "glossary.md"]
    assert "p.9" in (skill / "chapters" / "ch01-intro.md").read_text()
    assert "p.11" in (skill / "glossary.md").read_text()
    manifest = json.loads((skill / ".book-to-skill.json").read_text())
    assert manifest["page_offset"] == 12


def test_page_offset_transform_labels_when_offset_unknown(tmp_path: Path):
    from bookextract.cli import _page_offset_transform

    skill = tmp_path / "demo-skill"
    (skill / "chapters").mkdir(parents=True)
    (skill / ".source").mkdir()
    (skill / "chapters" / "ch01.md").write_text('[Ch 1, p.21] "q"\n', encoding="utf-8")
    # No metadata page_offset and no full_text.txt → offset unresolvable → physical label.
    (skill / ".source" / "metadata.json").write_text(json.dumps({}))
    (skill / ".book-to-skill.json").write_text(json.dumps({"generator_version": "1.2.0"}))

    changed = _page_offset_transform(skill, skill / ".source")

    assert changed == ["chapters/ch01.md"]
    assert "p.21 (pdf)" in (skill / "chapters" / "ch01.md").read_text()
    assert json.loads((skill / ".book-to-skill.json").read_text())["page_offset"] is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
