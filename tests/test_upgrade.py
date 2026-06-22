"""Tests for the deterministic skill-upgrade planner (bookextract.upgrade).

Plain assert-style functions, mirroring tests/test_extract.py. Fixtures are built
in-process: a synthetic CHANGELOG plus a fabricated skill directory (manifest +
archived .source). No model calls — the planner is fully deterministic.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract import __version__  # noqa: E402
from bookextract.upgrade import (  # noqa: E402
    apply_plan,
    build_plan,
    compute_delta,
    load_manifest,
    parse_changelog,
    parse_version,
    render_plan,
    verify_source,
)

_REPO = Path(__file__).resolve().parents[1]

# A synthetic changelog exercising every class, multi-line bullets, a subheader,
# an HTML-comment template that must be ignored, and a trailing link reference.
_CHANGELOG = """# Changelog

## Migration classes
| additive | new file | low |

## [1.2.0] — 2026-07-01
### Added
- Cues index: cues.md mapping triggers. (#2) [additive; steps 8]
### Changed
- Reshape SKILL.md header into a single line that wraps
  across two physical lines but is one logical bullet. [transform]

## [1.1.0] — 2026-06-25
### Added
- Grounding: every item carries a citation and the bullet
  wraps onto a second line. (#3) [regenerate; steps 7,8,9]
- Internal plumbing only. [infra]

<!--
## [9.9.9] — never
- Template example that must be ignored. (#99) [additive; steps 1]
-->

[1.1.0]: https://example.com/v1.1.0
"""


def _make_skill(tmp_path: Path, *, version: str, sha: str = "hash123") -> Path:
    skill = tmp_path / "skill"
    (skill / ".source").mkdir(parents=True)
    (skill / ".book-to-skill.json").write_text(
        json.dumps({"generator_version": version, "source_sha256": sha, "generated": "2026-01-01"})
    )
    (skill / ".source" / "metadata.json").write_text(json.dumps({"source_sha256": sha}))
    (skill / ".source" / "full_text.txt").write_text("body")
    return skill


# --------------------------------------------------------------------------- #
# parse_version / parse_changelog
# --------------------------------------------------------------------------- #


def test_parse_version_triple():
    assert parse_version(" 1.2.3 ") == (1, 2, 3)


def test_parse_version_rejects_non_semver():
    for bad in ("1.2", "1.2.3.4", "x.y.z"):
        try:
            parse_version(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_changelog_ignores_comment_template():
    entries = parse_changelog(_CHANGELOG)
    assert all(e.issue != "99" for e in entries), "template bullet inside <!-- --> leaked"
    assert {e.version for e in entries} == {(1, 2, 0), (1, 1, 0)}


def test_changelog_parses_class_steps_issue():
    by_issue = {e.issue: e for e in parse_changelog(_CHANGELOG) if e.issue}
    grounding = by_issue["3"]
    assert grounding.cls == "regenerate"
    assert grounding.steps == ("7", "8", "9")
    assert grounding.issue == "3"
    # Description keeps the prose but drops the trailing [tag] and the (#N) marker.
    assert "(#3)" not in grounding.description
    assert "[regenerate" not in grounding.description
    assert "wraps onto a second line" in grounding.description


def test_changelog_multiline_transform_bullet():
    transform = next(e for e in parse_changelog(_CHANGELOG) if e.cls == "transform")
    assert "wraps" in transform.description
    assert transform.steps == ()


def test_infra_entry_not_applicable_to_skill():
    infra = next(e for e in parse_changelog(_CHANGELOG) if e.cls == "infra")
    assert infra.applies_to_skill is False


# --------------------------------------------------------------------------- #
# compute_delta — half-open low, closed high
# --------------------------------------------------------------------------- #


def test_delta_excludes_from_includes_to():
    entries = parse_changelog(_CHANGELOG)
    delta = compute_delta((1, 1, 0), (1, 2, 0), entries)
    versions = {e.version for e in delta}
    assert (1, 1, 0) not in versions, "from-version must be exclusive"
    assert (1, 2, 0) in versions, "to-version must be inclusive"


def test_delta_empty_when_current():
    entries = parse_changelog(_CHANGELOG)
    assert compute_delta((1, 2, 0), (1, 2, 0), entries) == []


# --------------------------------------------------------------------------- #
# verify_source
# --------------------------------------------------------------------------- #


def test_verify_source_matches(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0", sha="deadbeef")
    manifest = load_manifest(skill)
    assert manifest is not None
    assert verify_source(skill, manifest) is True


def test_verify_source_mismatch(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0", sha="aaaa")
    (skill / ".source" / "metadata.json").write_text(json.dumps({"source_sha256": "bbbb"}))
    manifest = load_manifest(skill)
    assert manifest is not None
    assert verify_source(skill, manifest) is False


def test_verify_source_missing_archive(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0")
    (skill / ".source" / "full_text.txt").unlink()
    manifest = load_manifest(skill)
    assert manifest is not None
    assert verify_source(skill, manifest) is False


# --------------------------------------------------------------------------- #
# build_plan / render_plan
# --------------------------------------------------------------------------- #


def test_plan_groups_by_class(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0")
    plan = build_plan(skill, "1.2.0", _CHANGELOG)
    assert not plan.up_to_date
    assert {e.issue for e in plan.additive} == {"2"}
    assert {e.issue for e in plan.regenerate} == {"3"}
    assert len(plan.transform) == 1
    assert any(e.cls == "infra" for e in plan.skipped)
    assert plan.needs_source is True
    assert plan.source_ok is True


def test_plan_up_to_date_is_noop(tmp_path):
    skill = _make_skill(tmp_path, version="1.2.0")
    plan = build_plan(skill, "1.2.0", _CHANGELOG)
    assert plan.up_to_date is True
    assert plan.is_noop is True
    assert "already current" in render_plan(plan)


def test_build_plan_no_manifest_raises(tmp_path):
    (tmp_path / "empty").mkdir()
    try:
        build_plan(tmp_path / "empty", "1.2.0", _CHANGELOG)
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for a skill without a manifest")


# --------------------------------------------------------------------------- #
# apply_plan — mechanical transforms vs. model-backed remainder + manifest bump
# --------------------------------------------------------------------------- #


def test_apply_without_registry_leaves_remaining_and_no_bump(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0")
    plan = build_plan(skill, "1.2.0", _CHANGELOG)
    result = apply_plan(skill, plan, "1.2.0")
    assert result.bumped is False
    assert {e.issue for e in result.remaining} >= {"2", "3"}
    assert load_manifest(skill).version == (1, 0, 0)  # untouched


def test_apply_registered_transforms_bumps_when_nothing_remains(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0")
    # A delta with only mechanical (additive/transform) entries, all registered.
    changelog = """# Changelog

## [1.1.0] — 2026-06-25
### Added
- Cues index. (#2) [additive; steps 8]
"""
    plan = build_plan(skill, "1.1.0", changelog)
    applied: list[str] = []

    def fake_transform(skill_dir: Path, source_dir: Path) -> list[str]:
        (skill_dir / "cues.md").write_text("generated")
        applied.append(str(source_dir))
        return ["cues.md"]

    result = apply_plan(skill, plan, "1.1.0", registry={"2": fake_transform})
    assert result.changed_files == ["cues.md"]
    assert result.remaining == []
    assert result.bumped is True
    assert applied, "transform was not invoked"
    assert load_manifest(skill).version == (1, 1, 0)  # bumped


def test_apply_is_idempotent_when_current(tmp_path):
    skill = _make_skill(tmp_path, version="1.2.0")
    plan = build_plan(skill, "1.2.0", _CHANGELOG)
    result = apply_plan(skill, plan, "1.2.0")
    assert result.changed_files == []
    assert result.remaining == []
    assert result.bumped is False


# --------------------------------------------------------------------------- #
# Real repo CHANGELOG + CLI dry-run end-to-end
# --------------------------------------------------------------------------- #


def test_repo_changelog_parses_grounding_entry():
    text = (_REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    entries = parse_changelog(text)
    grounding = next(e for e in entries if e.issue == "3")
    assert grounding.cls == "regenerate"
    assert grounding.steps == ("7", "8", "8.5", "9")
    # The current generator version must be a real, parseable changelog version.
    assert parse_version(__version__) in {e.version for e in entries}


def test_cli_dry_run_prints_plan_without_mutating(tmp_path):
    skill = _make_skill(tmp_path, version="0.9.0")
    before = (skill / ".book-to-skill.json").read_text()
    script = _REPO / "scripts" / "extract.py"
    proc = subprocess.run(
        [
            sys.executable, str(script), "upgrade", str(skill),
            "--dry-run", "--changelog", str(_REPO / "CHANGELOG.md"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Upgrade plan:" in proc.stdout
    assert (skill / ".book-to-skill.json").read_text() == before, "dry-run mutated the manifest"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    script = _REPO / "scripts" / "extract.py"
    return subprocess.run(
        [sys.executable, str(script), "upgrade", *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_backfill_creates_manifest_and_source(tmp_path):
    # A pre-provenance skill (no manifest) plus its original source.
    skill = tmp_path / "preprov"
    (skill / "chapters").mkdir(parents=True)
    (skill / "chapters" / "ch01.md").write_text("# Chapter 1\nBody.\n")
    source = tmp_path / "book.txt"
    source.write_text("Chapter 1\nThe core idea is simple.\nChapter 2\nMore.\n")

    proc = _run_cli(str(skill), "--backfill", "--source", str(source), "--pin", "0.0.0")
    assert proc.returncode == 0, proc.stderr

    manifest = json.loads((skill / ".book-to-skill.json").read_text())
    assert manifest["generator_version"] == "0.0.0"
    assert manifest["backfilled"] is True
    assert len(manifest["source_sha256"]) == 64  # sha-256 hex
    assert (skill / ".source" / "full_text.txt").is_file()
    assert (skill / ".source" / "metadata.json").is_file()
    # The archived hash must match the manifest, so verify_source passes.
    src_meta = json.loads((skill / ".source" / "metadata.json").read_text())
    assert src_meta["source_sha256"] == manifest["source_sha256"]


def test_cli_backfill_refuses_existing_manifest_without_force(tmp_path):
    skill = _make_skill(tmp_path, version="1.0.0")  # already has a manifest
    source = tmp_path / "book.txt"
    source.write_text("Chapter 1\nText.\n")
    proc = _run_cli(str(skill), "--backfill", "--source", str(source))
    assert proc.returncode != 0
    assert "already has a manifest" in (proc.stderr + proc.stdout)


def test_cli_backfill_then_plan_is_actionable(tmp_path):
    skill = tmp_path / "preprov"
    (skill / "chapters").mkdir(parents=True)
    (skill / "chapters" / "ch01.md").write_text("# Chapter 1\nBody.\n")
    source = tmp_path / "book.txt"
    source.write_text("Chapter 1\nText.\nChapter 2\nMore.\n")
    assert _run_cli(str(skill), "--backfill", "--source", str(source)).returncode == 0
    # Pinned at 0.0.0, a real upgrade against the repo changelog must surface #3.
    proc = _run_cli(str(skill), "--dry-run", "--changelog", str(_REPO / "CHANGELOG.md"))
    assert proc.returncode == 0, proc.stderr
    assert "regenerate" in proc.stdout
    assert "(#3)" in proc.stdout
