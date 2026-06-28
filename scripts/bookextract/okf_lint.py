"""Deterministic linter for OKF (Open Knowledge Format) v0.1 bundles.

An OKF bundle is a directory of Markdown files. This module validates it with no
model and no third-party dependencies (stdlib only), reporting these classes of issue:

1. **type required** — every non-reserved ``.md`` note must carry a YAML frontmatter
   block (``---`` … ``---`` at the very top) with a non-empty ``type:`` field. The
   frontmatter is parsed with a minimal line-based scanner, not a YAML library: for
   linting we only need top-level ``key: value`` scalars (``type`` presence, and
   ``okf_version`` on the root index).
2. **reserved files** — ``index.md`` and ``log.md`` are reserved. An ``index.md`` must
   carry no frontmatter, except the bundle-root ``index.md`` which may carry a single
   ``okf_version`` key. A ``log.md``'s date headings must be ISO-8601 ``YYYY-MM-DD`` and
   ordered most-recent-first.
3. **links resolve** — Markdown links to ``.md`` targets (absolute bundle-relative
   ``/path.md`` or relative ``./`` / ``../``) must point at an existing file. Dangling
   links are errors by default, downgradable to warnings via ``allow_dangling``.
4. **citation coverage** — every *atomic* note (a non-reserved, non-exempt note —
   Source/MOC/Schema are exempt) must carry a ``# Citations`` section with at least one
   chapter-ref entry (``[Ch …]``). An uncited atomic note is an error, and the fraction
   of atomic notes that are cited must also meet ``min_coverage`` (default 0.8) or that
   is one further bundle-level error.
5. **reciprocal Related links** — when an atomic note's ``## Related`` section links to
   another atomic note, that note's ``## Related`` should link back. A missing backlink
   is a warning by default, an error under ``strict_links`` (Source/MOC/Schema/index
   exempt).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

RESERVED_INDEX: Final[str] = "index.md"
RESERVED_LOG: Final[str] = "log.md"
OKF_VERSION_KEY: Final[str] = "okf_version"
DEFAULT_MIN_COVERAGE: Final[float] = 0.8

# Note types that are navigation/provenance, not graph peers: exempt from the citation
# coverage and Related-reciprocity checks (compared case-insensitively).
_EXEMPT_TYPES: Final[frozenset[str]] = frozenset({"source", "moc", "schema"})

CAT_TYPE: Final[str] = "missing-type"
CAT_RESERVED: Final[str] = "reserved-file"
CAT_LOG: Final[str] = "log-format"
CAT_LINK: Final[str] = "dangling-link"
CAT_COVERAGE: Final[str] = "coverage"
CAT_RECIPROCITY: Final[str] = "reciprocity"

_BUNDLE_SCOPE: Final[str] = "."  # finding path for bundle-level (non-file) findings
_COVERAGE_EPS: Final[float] = 1e-9  # tolerance so 0.80 coverage clears a 0.80 threshold

_INDEX_FM_MSG: Final[str] = (
    "index.md is reserved and must not contain frontmatter "
    f"(only the bundle-root index.md may carry a single '{OKF_VERSION_KEY}' key)"
)

# A Markdown inline link: the target is captured; a `(url "title")` form is split later.
_LINK: Final[re.Pattern[str]] = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Log date heading at level ## or ###. Anything starting `YYYY-` is treated as a date
# heading attempt so malformed dates are caught rather than silently ignored.
_LOG_HEADING: Final[re.Pattern[str]] = re.compile(r"^#{2,3}\s+(\d{4}-\S*)\s*$")
_ISO_DATE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A `# Citations` section heading (any level), case-insensitive.
_CITATIONS: Final[re.Pattern[str]] = re.compile(
    r"^#{1,6}\s+citations\b", re.IGNORECASE | re.MULTILINE
)
# A grounding chapter-ref token, e.g. `[Ch 12, p.340]` or `[Ch 5]`.
_CHAPTER_REF: Final[re.Pattern[str]] = re.compile(r"\[Ch\b")
# Section boundaries inside a note: any h1/h2 heading. `## Related` opens the backlink fabric.
_SECTION_HEADING: Final[re.Pattern[str]] = re.compile(r"^#{1,2}\s")
_RELATED_HEADING: Final[re.Pattern[str]] = re.compile(r"^##\s+Related\b", re.IGNORECASE)

_EXTERNAL_PREFIXES: Final[tuple[str, ...]] = ("http://", "https://", "mailto:", "#")


@dataclass(frozen=True)
class Finding:
    """A single lint finding: where it is, what class it is, and what's wrong."""

    path: str  # bundle-relative posix path
    line: int | None
    category: str
    message: str


@dataclass(frozen=True)
class LintReport:
    """Result of linting a bundle: findings plus informational summary counts."""

    errors: tuple[Finding, ...]
    warnings: tuple[Finding, ...]
    md_files: int
    concept_notes: int
    notes_with_citations: int
    dangling_links: int
    atomic_notes: int
    cited_atomic: int

    @property
    def ok(self) -> bool:
        """True when there are no error-level findings."""
        return not self.errors

    @property
    def coverage(self) -> float:
        """Fraction of atomic notes carrying a chapter-ref citation (1.0 when none)."""
        if self.atomic_notes == 0:
            return 1.0
        return self.cited_atomic / self.atomic_notes


@dataclass(frozen=True)
class _Ctx:
    """Run-level config, grouped to keep per-check arity small."""

    bundle_dir: Path
    allow_dangling: bool
    min_coverage: float
    strict_links: bool


@dataclass(frozen=True)
class _File:
    """One Markdown file's resolved identity and contents."""

    path: Path
    rel: str
    text: str


@dataclass
class _Acc:
    """Mutable accumulator threaded through the per-file checks."""

    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    concept_notes: int = 0
    notes_with_citations: int = 0
    dangling: int = 0
    atomic_total: int = 0
    atomic_cited: int = 0
    # Reciprocity bookkeeping, resolved after every file is seen.
    is_atomic_by_rel: dict[str, bool] = field(default_factory=dict)
    related_by_rel: dict[str, list[tuple[str, int]]] = field(default_factory=dict)


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return the top-level scalar key/values of a leading YAML frontmatter block.

    Returns ``None`` when the text has no frontmatter or the block is unterminated.
    Only flat ``key: value`` lines at column 0 are collected — enough to detect
    ``type`` and ``okf_version`` for linting without pulling in a YAML library.
    """
    lines = text.splitlines()
    if not _has_frontmatter(text):
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        _collect_scalar(fields, line)
    return None  # no closing delimiter → malformed, treated as absent


def _has_frontmatter(text: str) -> bool:
    """True when the text opens with a ``---`` frontmatter delimiter line."""
    lines = text.splitlines()
    return bool(lines) and lines[0].strip() == "---"


def _collect_scalar(fields: dict[str, str], line: str) -> None:
    """Record a top-level ``key: value`` scalar; skip indented or non-key lines."""
    if not line or line[0].isspace() or ":" not in line:
        return
    key, _, value = line.partition(":")
    fields[key.strip()] = value.strip().strip("\"'")


def _is_atomic(note_type: str) -> bool:
    """True for a graph note (typed, and not an exempt Source/MOC/Schema)."""
    return bool(note_type) and note_type.lower() not in _EXEMPT_TYPES


def _is_cited(text: str) -> bool:
    """True when a ``# Citations`` heading is followed by an entry carrying a ``[Ch`` ref."""
    in_citations = False
    for line in text.splitlines():
        if _CITATIONS.match(line):
            in_citations = True
            continue
        if in_citations and _CHAPTER_REF.search(line):
            return True
    return False


def _check_coverage(acc: _Acc, file: _File) -> None:
    """Tally an atomic note's citation coverage; an uncited atomic note is an error."""
    acc.atomic_total += 1
    if _is_cited(file.text):
        acc.atomic_cited += 1
    else:
        acc.errors.append(Finding(file.rel, None, CAT_COVERAGE, "no chapter-ref citation"))


def _check_concept(acc: _Acc, ctx: _Ctx, file: _File) -> None:
    """A non-reserved note must declare a non-empty ``type``; gather coverage + Related."""
    acc.concept_notes += 1
    fields = parse_frontmatter(file.text)
    note_type = (fields or {}).get("type", "").strip()
    if not note_type:
        acc.errors.append(Finding(file.rel, 1, CAT_TYPE, "missing or empty 'type:' in frontmatter"))
    if _CITATIONS.search(file.text):
        acc.notes_with_citations += 1
    atomic = _is_atomic(note_type)
    acc.is_atomic_by_rel[file.rel] = atomic
    if atomic:
        _check_coverage(acc, file)
        acc.related_by_rel[file.rel] = _related_targets(ctx, file)


def _check_index(acc: _Acc, file: _File, *, is_root: bool) -> None:
    """``index.md`` carries no frontmatter, save a root index with only ``okf_version``."""
    if not _has_frontmatter(file.text):
        return
    fields = parse_frontmatter(file.text)
    if is_root and fields is not None and set(fields) == {OKF_VERSION_KEY}:
        return
    acc.errors.append(Finding(file.rel, 1, CAT_RESERVED, _INDEX_FM_MSG))


def _iso_date(value: str) -> date | None:
    """Parse a strict ``YYYY-MM-DD`` value into a date, or ``None`` if invalid."""
    if not _ISO_DATE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _log_dates(acc: _Acc, file: _File) -> list[tuple[int, date]]:
    """Collect valid (line, date) headings; flag malformed date headings as errors."""
    dated: list[tuple[int, date]] = []
    for lineno, line in enumerate(file.text.splitlines(), 1):
        match = _LOG_HEADING.match(line)
        if not match:
            continue
        parsed = _iso_date(match.group(1))
        if parsed is None:
            acc.errors.append(
                Finding(file.rel, lineno, CAT_LOG, f"malformed date heading: {match.group(1)!r}")
            )
        else:
            dated.append((lineno, parsed))
    return dated


def _check_log(acc: _Acc, file: _File) -> None:
    """``log.md`` date headings must be ISO-8601 and ordered most-recent-first."""
    dated = _log_dates(acc, file)
    for (_, earlier), (line, later) in zip(dated, dated[1:], strict=False):
        if later > earlier:
            acc.errors.append(
                Finding(file.rel, line, CAT_LOG, "date headings not ordered most-recent-first")
            )


def _link_target(raw: str) -> str | None:
    """Return the ``.md`` path a link points at, or ``None`` to ignore it.

    Drops external links (http/https/mailto/in-page anchors) and non-``.md`` targets,
    and strips any ``#fragment`` or ``"title"`` suffix.
    """
    parts = raw.split()
    url = parts[0] if parts else ""
    if not url or url.startswith(_EXTERNAL_PREFIXES):
        return None
    url = url.split("#", 1)[0]
    if not url.endswith(".md"):
        return None
    return url


def _candidate(ctx: _Ctx, file: _File, target: str) -> Path:
    """Resolve a link target to a filesystem path (absolute bundle-relative or local)."""
    if target.startswith("/"):
        return ctx.bundle_dir / target.lstrip("/")
    return file.path.parent / target


def _resolve_rel(ctx: _Ctx, file: _File, target: str) -> str | None:
    """Bundle-relative posix path of an existing in-bundle ``.md`` target, else ``None``."""
    candidate = _candidate(ctx, file, target)
    if not candidate.exists():
        return None
    try:
        rel = candidate.resolve().relative_to(ctx.bundle_dir.resolve())
    except ValueError:
        return None  # link escapes the bundle root
    return rel.as_posix()


def _check_links(acc: _Acc, ctx: _Ctx, file: _File) -> None:
    """Report every ``.md`` link in the file that does not resolve to a real file."""
    for lineno, line in enumerate(file.text.splitlines(), 1):
        for match in _LINK.finditer(line):
            target = _link_target(match.group(1))
            if target is None or _candidate(ctx, file, target).exists():
                continue
            acc.dangling += 1
            finding = Finding(file.rel, lineno, CAT_LINK, f"dangling link -> {target}")
            bucket = acc.warnings if ctx.allow_dangling else acc.errors
            bucket.append(finding)


def _related_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line_no, line)`` for the lines inside the note's ``## Related`` section."""
    in_section = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if _SECTION_HEADING.match(line):
            in_section = bool(_RELATED_HEADING.match(line))
            continue
        if in_section:
            yield lineno, line


def _related_targets(ctx: _Ctx, file: _File) -> list[tuple[str, int]]:
    """Resolved in-bundle ``.md`` targets linked from the note's ``## Related`` section."""
    out: list[tuple[str, int]] = []
    for lineno, line in _related_lines(file.text):
        for match in _LINK.finditer(line):
            target = _link_target(match.group(1))
            if target is None:
                continue
            resolved = _resolve_rel(ctx, file, target)
            if resolved is not None:
                out.append((resolved, lineno))
    return out


def _check_file(acc: _Acc, ctx: _Ctx, file: _File) -> None:
    """Dispatch the structural check for one file, then check its links."""
    name = file.path.name
    if name == RESERVED_INDEX:
        acc.is_atomic_by_rel[file.rel] = False
        _check_index(acc, file, is_root=file.path.parent == ctx.bundle_dir)
    elif name == RESERVED_LOG:
        acc.is_atomic_by_rel[file.rel] = False
        _check_log(acc, file)
    else:
        _check_concept(acc, ctx, file)
    _check_links(acc, ctx, file)


def _check_coverage_gate(acc: _Acc, ctx: _Ctx) -> None:
    """Error when the share of atomic notes carrying a chapter ref is below the threshold."""
    if acc.atomic_total == 0:
        return
    coverage = acc.atomic_cited / acc.atomic_total
    if coverage < ctx.min_coverage - _COVERAGE_EPS:
        acc.errors.append(
            Finding(
                _BUNDLE_SCOPE,
                None,
                CAT_COVERAGE,
                f"citation coverage {coverage:.0%} below required {ctx.min_coverage:.0%} "
                f"({acc.atomic_cited}/{acc.atomic_total} atomic notes cited)",
            )
        )


def _check_reciprocity(acc: _Acc, ctx: _Ctx) -> None:
    """Flag atomic→atomic ``## Related`` links the target note does not link back."""
    for src_rel, links in acc.related_by_rel.items():
        for tgt_rel, line in links:
            if not acc.is_atomic_by_rel.get(tgt_rel, False):
                continue  # target is exempt/reserved → no reciprocity required
            back = acc.related_by_rel.get(tgt_rel, [])
            if any(target == src_rel for target, _ in back):
                continue
            finding = Finding(
                src_rel, line, CAT_RECIPROCITY, f"no reciprocal Related link from {tgt_rel}"
            )
            (acc.errors if ctx.strict_links else acc.warnings).append(finding)


def lint_bundle(
    bundle_dir: Path,
    *,
    allow_dangling: bool = False,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    strict_links: bool = False,
) -> LintReport:
    """Validate an OKF v0.1 bundle directory and return its :class:`LintReport`.

    Args:
        bundle_dir: The bundle root (a directory of Markdown files).
        allow_dangling: When True, dangling links are warnings rather than errors.
        min_coverage: Minimum fraction of atomic notes that must carry a chapter-ref
            citation; below it is an error.
        strict_links: When True, missing reciprocal ``## Related`` links are errors,
            not warnings.

    Returns:
        A report carrying error/warning findings and informational summary counts.
    """
    ctx = _Ctx(
        bundle_dir=bundle_dir,
        allow_dangling=allow_dangling,
        min_coverage=min_coverage,
        strict_links=strict_links,
    )
    acc = _Acc()
    md_files = sorted(bundle_dir.rglob("*.md"))
    for path in md_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        file = _File(path=path, rel=path.relative_to(bundle_dir).as_posix(), text=text)
        _check_file(acc, ctx, file)
    _check_coverage_gate(acc, ctx)
    _check_reciprocity(acc, ctx)
    return LintReport(
        errors=tuple(acc.errors),
        warnings=tuple(acc.warnings),
        md_files=len(md_files),
        concept_notes=acc.concept_notes,
        notes_with_citations=acc.notes_with_citations,
        dangling_links=acc.dangling,
        atomic_notes=acc.atomic_total,
        cited_atomic=acc.atomic_cited,
    )


def _format_finding(level: str, finding: Finding) -> str:
    """Render one finding as ``LEVEL [category] path:line: message``."""
    loc = f"{finding.path}:{finding.line}" if finding.line is not None else finding.path
    return f"{level} [{finding.category}] {loc}: {finding.message}"


def format_report(report: LintReport) -> str:
    """Render a :class:`LintReport` as human-readable text."""
    lines = [_format_finding("ERROR", f) for f in report.errors]
    lines += [_format_finding("WARN", f) for f in report.warnings]
    if lines:
        lines.append("")
    lines.append(
        f"Linted {report.md_files} .md file(s): "
        f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)."
    )
    lines.append(
        f"Concept notes: {report.concept_notes} "
        f"({report.notes_with_citations} with a Citations section). "
        f"Dangling links: {report.dangling_links}."
    )
    lines.append(
        f"Atomic notes: {report.atomic_notes} cited "
        f"{report.cited_atomic}/{report.atomic_notes} ({report.coverage:.0%})."
    )
    reciprocity = sum(
        1 for f in (*report.errors, *report.warnings) if f.category == CAT_RECIPROCITY
    )
    lines.append(f"Reciprocity: {reciprocity} missing backlink(s).")
    return "\n".join(lines)
