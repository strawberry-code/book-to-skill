"""Tests for deterministic, dependency-free slug reconciliation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.reconcile import reconcile_slugs  # noqa: E402


def test_acronym_folds_into_expansion():
    out = reconcile_slugs({"bsc", "binary-symmetric-channel"})
    assert out == {"bsc": "binary-symmetric-channel"}


def test_plural_folds_into_singular():
    out = reconcile_slugs({"encoder", "encoders"})
    assert out == {"encoders": "encoder"}


def test_no_false_merge_on_near_plurals():
    # "basis"/"bases" must NOT merge: basis+s != bases, bases-s != basis.
    assert reconcile_slugs({"basis", "bases"}) == {}
    # looser stemming is out of scope: "code"/"coding" stay distinct.
    assert reconcile_slugs({"code", "coding"}) == {}


def test_acronym_needs_a_multiword_expansion_present():
    # No expansion whose initials are "bsc" → nothing folds.
    assert reconcile_slugs({"bsc", "block-code"}) == {}


def test_singletons_and_unrelated_slugs_are_untouched():
    assert reconcile_slugs({"hamming-code", "linear-code"}) == {}


def test_deterministic_when_initials_collide():
    # Two expansions share initials "bc"; the sorted-first one wins, stably.
    slugs = {"bc", "binary-code", "block-cipher"}
    assert reconcile_slugs(slugs) == {"bc": "binary-code"}
