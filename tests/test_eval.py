"""Tests for the deterministic bundle-vs-gold evaluation harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.assemble import AssembleInputs, Source, assemble  # noqa: E402
from bookextract.eval import (  # noqa: E402
    BundleNote,
    Gold,
    GoldConcept,
    evaluate,
    load_gold,
    read_notes,
)
from bookextract.notes import Citation, Note  # noqa: E402

_RAW = "alpha concept text appears here\nbeta concept text appears here\n"
_SOURCE = Source(
    slug="src",
    title="Test Source",
    authors=("Tester",),
    extraction_method="plain-text",
    source_sha256="abc",
    source_filename="t.md",
    raw_rel="raw/src/full_text.txt",
    page_offset=None,
)


def _note(
    slug: str, *, related: tuple[str, ...], quote: str, aliases: tuple[str, ...] = ()
) -> Note:
    return Note(
        type="Concept",
        slug=slug,
        title=slug.title(),
        description=f"The {slug}.",
        tags=("t",),
        aliases=aliases,
        confidence="high",
        status="established",
        body=f"Body about {slug}.",
        related=related,
        citations=(Citation(1, quote, "src"),),
    )


def _build(notes: list[Note], tmp_path: Path) -> list[BundleNote]:
    inputs = AssembleInputs.single(
        notes=notes, source=_SOURCE, raw_text=_RAW, timestamp="2026-06-28T00:00:00Z"
    )
    report = assemble(inputs, tmp_path)
    assert report.ok, report.errors
    return read_notes(tmp_path)


def test_perfect_recall_and_links(tmp_path: Path):
    a = _note("alpha", related=("beta",), quote="alpha concept text")
    b = _note("beta", related=("alpha",), quote="beta concept text")
    gold = Gold(
        concepts=(GoldConcept("alpha", (), None), GoldConcept("beta", (), None)),
        links=(("alpha", "beta"),),
    )
    report = evaluate(_build([a, b], tmp_path), gold)
    assert report.concept_recall == 1.0
    assert report.link_recall == 1.0
    assert report.ok(1.0)


def test_missing_concept_lowers_recall(tmp_path: Path):
    a = _note("alpha", related=(), quote="alpha concept text")
    gold = Gold(
        concepts=(GoldConcept("alpha", (), None), GoldConcept("gamma", (), None)),
        links=(),
    )
    report = evaluate(_build([a], tmp_path), gold)
    assert report.concept_recall == 0.5
    assert report.missing_concepts == ("gamma",)
    assert not report.ok(0.8)


def test_alias_match_counts_as_found(tmp_path: Path):
    # The gold names the acronym; the bundle note carries it as an alias.
    a = _note("alpha", related=(), quote="alpha concept text", aliases=("ax",))
    gold = Gold(concepts=(GoldConcept("ax", (), None),), links=())
    report = evaluate(_build([a], tmp_path), gold)
    assert report.concept_recall == 1.0


def test_fact_anchor_coverage(tmp_path: Path):
    a = _note("alpha", related=(), quote="alpha concept text")
    gold = Gold(
        concepts=(
            GoldConcept("alpha", (), "Body about alpha"),  # present in the note body
            GoldConcept("alpha", (), "nonexistent phrase"),  # absent
        ),
        links=(),
    )
    report = evaluate(_build([a], tmp_path), gold)
    assert report.facts_total == 2
    assert report.facts_found == 1
    assert report.fact_coverage == 0.5


def test_link_recall_is_direction_agnostic(tmp_path: Path):
    # Only alpha declares the link; reciprocity is inserted, so the edge still counts.
    a = _note("alpha", related=("beta",), quote="alpha concept text")
    b = _note("beta", related=(), quote="beta concept text")
    gold = Gold(concepts=(), links=(("beta", "alpha"),))
    report = evaluate(_build([a, b], tmp_path), gold)
    assert report.link_recall == 1.0


def test_load_gold_round_trips(tmp_path: Path):
    spec = {
        "concepts": [{"slug": "alpha", "aliases": ["ax"], "fact_anchor": "x"}],
        "links": [["alpha", "beta"]],
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    gold = load_gold(path)
    assert gold.concepts[0].slug == "alpha"
    assert gold.concepts[0].aliases == ("ax",)
    assert gold.links == (("alpha", "beta"),)
