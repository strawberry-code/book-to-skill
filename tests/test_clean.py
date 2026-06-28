"""Tests for the deterministic raw-text cleaner (Fase E)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.clean import clean_text  # noqa: E402


def test_removes_bare_page_number_lines():
    text = "real prose line\n14\nmore real prose\n322\n"
    cleaned, removed = clean_text(text)
    assert removed == 2
    assert "14" not in cleaned.split("\n")
    assert "real prose line" in cleaned
    assert "more real prose" in cleaned


def test_removes_repeated_all_caps_running_header():
    # The running header repeats on many pages (with varying page numbers); body is kept.
    body = "\n".join(f"body sentence number {i} here" for i in range(6))
    pages = "\n".join(f"{i} ALGEBRAIC CODING THEORY" for i in range(6))  # 6 repeats
    cleaned, removed = clean_text(body + "\n" + pages + "\n")
    assert removed == 6
    assert "ALGEBRAIC CODING THEORY" not in cleaned
    assert "body sentence number 3 here" in cleaned


def test_keeps_one_off_all_caps_heading():
    # A single ALL-CAPS line (not repeated) is a real heading — must be kept.
    text = "intro prose\nINTRODUCTION\nmore prose about the topic at hand\n"
    cleaned, removed = clean_text(text)
    assert removed == 0
    assert "INTRODUCTION" in cleaned


def test_never_touches_lowercase_prose():
    text = "The binary symmetric channel is a model.\nIt flips bits with probability epsilon.\n"
    cleaned, removed = clean_text(text)
    assert removed == 0
    assert cleaned == text


def test_preserves_form_feeds_for_page_counting():
    # Form-feeds must survive so physical-page/folio counting stays exact.
    text = "prose\n\f\n7\nmore prose\n\f\n8\nyet more\n"
    cleaned, removed = clean_text(text)
    assert cleaned.count("\f") == 2  # both page boundaries kept
    assert removed == 2  # the two bare page numbers dropped
