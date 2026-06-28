"""Tests for the deterministic OKF v0.1 bundle linter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.okf_lint import (  # noqa: E402
    CAT_COVERAGE,
    CAT_LINK,
    CAT_LOG,
    CAT_RECIPROCITY,
    CAT_RESERVED,
    CAT_TYPE,
    format_report,
    lint_bundle,
    parse_frontmatter,
)


def _atom(title: str, type_: str, related: list[tuple[str, str]], *, cited: bool = True) -> str:
    """A grounded atomic note with a `## Related` section and a `# Citations` section."""
    rel = "\n".join(f"- [{text}]({path}) — x" for text, path in related)
    cite = '[Ch 1, p.10] "verbatim"' if cited else "see the source"
    return (
        f"---\ntype: {type_}\ntitle: {title}\n---\n\n"
        f"# {title}\n\nDefinition.\n\n"
        f"## Related\n{rel}\n\n"
        f"# Citations\n[1] {cite} — [Src](/references/book.md)\n"
    )


def _bundle(tmp_path: Path) -> Path:
    """A minimal valid OKF vault: root index, log, a Source note, two reciprocal atoms."""
    (tmp_path / "index.md").write_text(
        '---\nokf_version: "0.1"\n---\n\n# Vault\n\n[alpha](/concepts/alpha.md)\n', encoding="utf-8"
    )
    (tmp_path / "log.md").write_text(
        "# Log\n\n## 2026-06-28\nlatest\n\n## 2026-06-01\nolder\n", encoding="utf-8"
    )
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "book.md").write_text(
        "---\ntype: Source\ntitle: Book\n---\n\n# Book\n\nThe source.\n", encoding="utf-8"
    )
    (tmp_path / "concepts").mkdir()
    (tmp_path / "concepts" / "alpha.md").write_text(
        _atom("Alpha", "Concept", [("Beta", "/concepts/beta.md")]), encoding="utf-8"
    )
    (tmp_path / "concepts" / "beta.md").write_text(
        _atom("Beta", "Concept", [("Alpha", "/concepts/alpha.md")]), encoding="utf-8"
    )
    return tmp_path


# --- frontmatter parsing ----------------------------------------------------


def test_parse_frontmatter_extracts_scalars():
    fields = parse_frontmatter('---\ntype: concept\nokf_version: "0.1"\n---\nbody\n')
    assert fields == {"type": "concept", "okf_version": "0.1"}


def test_parse_frontmatter_none_without_block():
    assert parse_frontmatter("# Just a heading\n") is None


def test_parse_frontmatter_none_when_unterminated():
    assert parse_frontmatter("---\ntype: concept\nbody with no close\n") is None


# --- valid bundle -----------------------------------------------------------


def test_clean_bundle_has_no_errors(tmp_path: Path):
    report = lint_bundle(_bundle(tmp_path))
    assert report.ok
    assert report.errors == ()
    assert report.warnings == ()
    assert report.md_files == 5
    assert report.concept_notes == 3  # alpha, beta, book (Source)
    assert report.atomic_notes == 2  # only alpha + beta; the Source is exempt
    assert report.cited_atomic == 2
    assert report.coverage == 1.0
    assert report.dangling_links == 0


def test_root_index_may_carry_okf_version(tmp_path: Path):
    assert lint_bundle(_bundle(tmp_path)).ok  # the root index carries okf_version already


# --- structural findings ----------------------------------------------------


def test_catches_missing_type_dangling_and_log_order(tmp_path: Path):
    _bundle(tmp_path)
    (tmp_path / "concepts" / "gamma.md").write_text(
        "no frontmatter here\n\n[gone](./missing.md)\n", encoding="utf-8"
    )
    (tmp_path / "log.md").write_text(
        "# Log\n\n## 2026-06-01\nolder\n\n## 2026-06-28\nlatest\n", encoding="utf-8"
    )

    report = lint_bundle(tmp_path)

    assert not report.ok
    categories = {f.category for f in report.errors}
    assert {CAT_TYPE, CAT_LINK, CAT_LOG} <= categories
    link_err = next(f for f in report.errors if f.category == CAT_LINK)
    assert link_err.path == "concepts/gamma.md"
    assert "missing.md" in link_err.message
    assert link_err.line == 3


def test_non_root_index_frontmatter_is_flagged(tmp_path: Path):
    _bundle(tmp_path)
    (tmp_path / "concepts" / "index.md").write_text(
        '---\nokf_version: "0.1"\n---\n# sub index\n', encoding="utf-8"
    )
    report = lint_bundle(tmp_path)
    assert not report.ok
    assert any(f.category == CAT_RESERVED for f in report.errors)


def test_malformed_log_date_is_flagged(tmp_path: Path):
    _bundle(tmp_path)
    (tmp_path / "log.md").write_text("# Log\n\n## 2026-13-45\nbad date\n", encoding="utf-8")
    report = lint_bundle(tmp_path)
    assert any(f.category == CAT_LOG and "malformed" in f.message for f in report.errors)


def test_allow_dangling_downgrades_to_warning(tmp_path: Path):
    _bundle(tmp_path)
    (tmp_path / "concepts" / "alpha.md").write_text(
        _atom("Alpha", "Concept", [("Beta", "/concepts/beta.md"), ("Nope", "/concepts/nope.md")]),
        encoding="utf-8",
    )
    strict = lint_bundle(tmp_path)
    lenient = lint_bundle(tmp_path, allow_dangling=True)
    assert not strict.ok and any(f.category == CAT_LINK for f in strict.errors)
    assert any(f.category == CAT_LINK for f in lenient.warnings)
    assert lenient.dangling_links == 1


def test_external_and_non_md_links_are_ignored(tmp_path: Path):
    _bundle(tmp_path)
    body = _atom("Alpha", "Concept", [("Beta", "/concepts/beta.md")])
    body += "\n[web](https://example.com) [img](./pic.png) [a](#anchor)\n"
    (tmp_path / "concepts" / "alpha.md").write_text(body, encoding="utf-8")
    assert lint_bundle(tmp_path).ok


# --- citation coverage ------------------------------------------------------


def test_uncited_atomic_note_is_error_and_drops_coverage(tmp_path: Path):
    _bundle(tmp_path)
    # beta loses its chapter ref → 1/2 atomic notes cited (50%), below the 80% default.
    (tmp_path / "concepts" / "beta.md").write_text(
        _atom("Beta", "Concept", [("Alpha", "/concepts/alpha.md")], cited=False), encoding="utf-8"
    )
    report = lint_bundle(tmp_path)

    assert not report.ok
    assert report.cited_atomic == 1 and report.atomic_notes == 2
    # the uncited note has its own error...
    note_err = next(
        f for f in report.errors if f.category == CAT_COVERAGE and f.path == "concepts/beta.md"
    )
    assert "chapter-ref" in note_err.message
    # ...and the aggregate gate fires once, scoped to the bundle root ".".
    assert any(f.category == CAT_COVERAGE and f.path == "." for f in report.errors)


def test_min_coverage_flag_silences_only_the_aggregate_gate(tmp_path: Path):
    _bundle(tmp_path)
    (tmp_path / "concepts" / "beta.md").write_text(
        _atom("Beta", "Concept", [("Alpha", "/concepts/alpha.md")], cited=False), encoding="utf-8"
    )
    relaxed = lint_bundle(tmp_path, min_coverage=0.5)  # 50% coverage clears a 50% floor
    # the bundle-level gate no longer fires...
    assert not any(f.category == CAT_COVERAGE and f.path == "." for f in relaxed.errors)
    # ...but the uncited note is still its own error.
    assert any(f.category == CAT_COVERAGE and f.path == "concepts/beta.md" for f in relaxed.errors)


def test_citations_without_chapter_ref_does_not_count_as_covered(tmp_path: Path):
    _bundle(tmp_path)
    # Both atoms have a `# Citations` section but no `[Ch …]` → 0% coverage.
    for slug, other in (("alpha", "beta"), ("beta", "alpha")):
        (tmp_path / "concepts" / f"{slug}.md").write_text(
            _atom(slug.title(), "Concept", [(other.title(), f"/concepts/{other}.md")], cited=False),
            encoding="utf-8",
        )
    report = lint_bundle(tmp_path)
    assert report.cited_atomic == 0
    assert report.notes_with_citations >= 2  # they DO have a Citations heading, just no [Ch]


# --- reciprocal Related links -----------------------------------------------


def test_missing_reciprocal_related_is_warning_then_error_under_strict(tmp_path: Path):
    _bundle(tmp_path)
    # alpha drops its backlink to beta; beta still links alpha → not reciprocated.
    (tmp_path / "concepts" / "alpha.md").write_text(
        _atom("Alpha", "Concept", []), encoding="utf-8"
    )
    lenient = lint_bundle(tmp_path)
    strict = lint_bundle(tmp_path, strict_links=True)

    assert lenient.ok  # reciprocity is a warning by default
    recip = next(f for f in lenient.warnings if f.category == CAT_RECIPROCITY)
    assert recip.path == "concepts/beta.md"  # beta is the note whose link is unreciprocated
    assert "concepts/alpha.md" in recip.message
    assert not strict.ok
    assert any(f.category == CAT_RECIPROCITY for f in strict.errors)


def test_related_links_to_exempt_notes_need_no_backlink(tmp_path: Path):
    _bundle(tmp_path)
    # alpha additionally relates to the Source note; a Source need not link back.
    (tmp_path / "concepts" / "alpha.md").write_text(
        _atom("Alpha", "Concept", [("Beta", "/concepts/beta.md"), ("Book", "/references/book.md")]),
        encoding="utf-8",
    )
    report = lint_bundle(tmp_path, strict_links=True)
    assert report.ok  # the Source link raises no reciprocity finding


def test_relative_related_links_resolve_and_reciprocate(tmp_path: Path):
    _bundle(tmp_path)
    # Use `../` relative links both ways; reciprocity must normalize them to the same key.
    (tmp_path / "concepts" / "alpha.md").write_text(
        _atom("Alpha", "Concept", [("Beta", "../concepts/beta.md")]), encoding="utf-8"
    )
    (tmp_path / "concepts" / "beta.md").write_text(
        _atom("Beta", "Concept", [("Alpha", "../concepts/alpha.md")]), encoding="utf-8"
    )
    assert lint_bundle(tmp_path, strict_links=True).ok


# --- formatting -------------------------------------------------------------


def test_format_report_summarizes(tmp_path: Path):
    report = lint_bundle(_bundle(tmp_path))
    out = format_report(report)
    assert "Linted 5 .md file(s): 0 error(s), 0 warning(s)." in out
    assert "Atomic notes: 2 cited 2/2 (100%)." in out
    assert "Reciprocity: 0 missing backlink(s)." in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
