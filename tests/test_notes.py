"""Tests for Note validation and normalize-then-match grounding."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.notes import (  # noqa: E402
    Citation,
    NoteValidationError,
    ground_citation,
    validate_note,
)

# Raw with a form-feed (so pages are derivable) and an "ﬁ" ligature in the source.
_RAW = "intro line\n\falpha beta gamma\ndelta epsilon\n\fthe ﬁnding here\n"


def _note(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "Concept",
        "slug": "alpha",
        "title": "Alpha",
        "description": "An alpha.",
        "body": "Body text.",
        "citations": [{"chapter": 1, "quote": "alpha beta", "source": "src"}],
    }
    base.update(over)
    return base


def test_validate_note_accepts_a_well_formed_note():
    note = validate_note(_note(tags=["t"], related=["beta"], aliases=["a"]))
    assert note.slug == "alpha"
    assert note.confidence == "medium"  # default applied
    assert note.related == ("beta",)


def test_validate_note_rejects_unknown_type():
    with pytest.raises(NoteValidationError):
        validate_note(_note(type="Glossary"))


def test_validate_note_rejects_non_kebab_slug():
    with pytest.raises(NoteValidationError):
        validate_note(_note(slug="Alpha Beta"))


def test_validate_note_requires_citations():
    with pytest.raises(NoteValidationError):
        validate_note(_note(citations=[]))


def test_grounding_matches_across_a_line_break():
    grounded = ground_citation(Citation(1, "beta gamma delta", "src"), _RAW, None)
    assert grounded.quote == "beta gamma delta"  # recovered span, whitespace collapsed
    assert grounded.folio == "2 (pdf)"  # one form-feed before it


def test_grounding_folds_ligatures_and_recovers_verbatim():
    # The agent writes plain "finding"; the source has the "ﬁ" ligature.
    grounded = ground_citation(Citation(1, "finding here", "src"), _RAW, None)
    assert grounded.quote == "ﬁnding here"  # verbatim source bytes recovered
    assert grounded.folio == "3 (pdf)"


def test_grounding_remaps_folio_with_offset():
    grounded = ground_citation(Citation(1, "beta gamma", "src"), _RAW, 1)
    assert grounded.folio == "1"  # physical page 2 minus offset 1


def test_grounding_raises_when_quote_absent():
    with pytest.raises(NoteValidationError):
        ground_citation(Citation(1, "this text is not in the source", "src"), _RAW, None)
