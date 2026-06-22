"""Tests for the batch backfill matcher (bookextract.batch) and its CLI dry-run."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.batch import match_sources  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]

# Filenames shaped like the real ~/Downloads/shredded-books archive.
_FILES = [
    "Concurrency The Works of Leslie Lamport (Dahlia Malkhi).pdf",
    "Specifying Systems The TLA+ Language and Tools (Leslie Lamport).pdf",
    "Geopolitics A Guide to the Issues (Bert Chapman).pdf",
    "Designing Hexagonal Architecture with Java (Davi Vieira).pdf",
    "Getting Started with OAuth 2.0 (Ryan Boyd).pdf",
]


def _by_slug(slugs):
    return {m.slug: m for m in match_sources(slugs, _FILES)}


def test_shared_author_token_is_disambiguated():
    # Both Lamport books share "lamport"; the other slug tokens must break the tie.
    res = _by_slug(["concurrency-lamport-works", "specifying-systems-tlaplus"])
    assert "Concurrency" in res["concurrency-lamport-works"].source
    assert "Specifying Systems" in res["specifying-systems-tlaplus"].source


def test_author_surname_slug_matches():
    res = _by_slug(["geopolitics-chapman"])["geopolitics-chapman"]
    assert res.source is not None
    assert "Chapman" in res.source
    assert res.score >= 0.6


def test_confident_match_has_source_and_score():
    res = _by_slug(["hexagonal-architecture-java"])["hexagonal-architecture-java"]
    assert "Hexagonal" in res.source
    assert res.score == 1.0
    assert res.ambiguous is False


def test_unmatched_slug_yields_no_source():
    # No archive file is about this; best score stays below threshold.
    res = _by_slug(["quantum-thermodynamics-xyz"])["quantum-thermodynamics-xyz"]
    assert res.source is None
    assert res.ambiguous is False


def test_tie_is_flagged_ambiguous_not_guessed():
    files = ["Bash Cookbook (Albing).pdf", "Bash Cookbook (Newham).pdf"]
    res = {m.slug: m for m in match_sources(["bash-cookbook"], files)}["bash-cookbook"]
    assert res.source is None  # never guess between equally-scored sources
    assert res.ambiguous is True


def test_cli_backfill_batch_dry_run(tmp_path):
    skills = tmp_path / "skills"
    (skills / "oauth2-getting-started").mkdir(parents=True)
    # A skill that already has a manifest must be skipped (not pre-provenance).
    done = skills / "already-done"
    done.mkdir()
    (done / ".book-to-skill.json").write_text(json.dumps({"generator_version": "1.0.0"}))
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "Getting Started with OAuth 2.0 (Ryan Boyd).pdf").write_bytes(b"%PDF-1.4 stub")

    proc = subprocess.run(
        [sys.executable, str(_REPO / "scripts" / "extract.py"),
         "backfill-batch", str(skills), str(archive)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "oauth2-getting-started" in proc.stdout
    assert "already-done" not in proc.stdout  # has a manifest → not listed
    assert "dry-run" in proc.stdout
    # Dry-run must not create provenance.
    assert not (skills / "oauth2-getting-started" / ".book-to-skill.json").exists()
