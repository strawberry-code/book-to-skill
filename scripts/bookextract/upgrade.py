"""Deterministic upgrade planner for generated skills.

A generated skill is a derived artifact of ``(source + generator version)``. When
the generator gains features, existing skills go stale. This module computes —
deterministically and without any model call — *what* must change to bring a skill
up to the current generator version, by diffing the skill's ``.book-to-skill.json``
manifest against the repo ``CHANGELOG.md``.

The actual content regeneration for ``regenerate``-class changes is model-backed
and stays in the SKILL.md flow; this module decides and verifies, the agent (or a
registered mechanical transform) applies. Keeping the decision here makes upgrades
reproducible, dry-runnable, and unit-testable.

No third-party imports, no environment reads: pure functions over text and files.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

# A mechanical transform rewrites a skill in place from already-archived data.
# It receives (skill_dir, source_dir) and returns the list of changed file names.
TransformFn = Callable[[Path, Path], list[str]]

MANIFEST_NAME: Final[str] = ".book-to-skill.json"
SOURCE_DIR_NAME: Final[str] = ".source"

# Content classes are applicable to an existing skill; the rest are generator-only.
_CONTENT_CLASSES: Final[frozenset[str]] = frozenset({"additive", "transform", "regenerate"})

# A version section: its header line, then everything up to the next version header.
_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^##\s*\[(\d+\.\d+\.\d+)\][^\n]*\n(.*?)(?=^##\s*\[|\Z)", re.DOTALL | re.MULTILINE
)
# A bullet within a section: a "- " line plus its wrapped continuation, stopping at
# the next bullet, any heading ("###"/"##"), or a blank line — so subheaders and
# trailing link-reference lines never bleed into the bullet (which would break its tag).
_BULLET: Final[re.Pattern[str]] = re.compile(
    r"^-\s+(.*?)(?=^[-#]|^[ \t]*$|\Z)", re.DOTALL | re.MULTILINE
)
_ENTRY_TAG: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]\s*$")
_ENTRY_ISSUE: Final[re.Pattern[str]] = re.compile(r"\(#(\d+)\)")
_STEPS_IN_TAG: Final[re.Pattern[str]] = re.compile(r"steps\s+([0-9.,\s]+)")
_VERSION_PARTS: Final[int] = 3

Version = tuple[int, int, int]


def parse_version(text: str) -> Version:
    """Parse ``"1.2.3"`` into a comparable ``(1, 2, 3)`` tuple.

    Args:
        text: A dotted semantic version string.

    Returns:
        The major/minor/patch triple.

    Raises:
        ValueError: If ``text`` is not three dot-separated integers.
    """
    parts = text.strip().split(".")
    if len(parts) != _VERSION_PARTS:
        raise ValueError(f"not a semver: {text!r}")
    major, minor, patch = (int(p) for p in parts)
    return (major, minor, patch)


@dataclass(frozen=True)
class ChangeEntry:
    """One CHANGELOG bullet: a single change with its migration class."""

    version: Version
    cls: str
    steps: tuple[str, ...]
    description: str
    issue: str | None

    @property
    def applies_to_skill(self) -> bool:
        """True when this change alters generated skill content (not generator-only)."""
        return self.cls in _CONTENT_CLASSES


def _parse_tag(tag: str) -> tuple[str, tuple[str, ...]]:
    """Split a ``[class; steps a,b,c]`` tag into its class and step ids."""
    head, _, _ = tag.partition(";")
    cls = head.strip().lower()
    steps: tuple[str, ...] = ()
    match = _STEPS_IN_TAG.search(tag)
    if match:
        steps = tuple(s.strip() for s in match.group(1).split(",") if s.strip())
    return cls, steps


_HTML_COMMENT: Final[re.Pattern[str]] = re.compile(r"<!--.*?-->", re.DOTALL)


def _parse_entry_text(text: str, version: Version) -> ChangeEntry | None:
    """Parse a joined bullet ``description (#N) [class; steps …]``, or None if untagged."""
    tag_match = _ENTRY_TAG.search(text)
    if not tag_match:
        return None
    cls, steps = _parse_tag(tag_match.group(1))
    issue_match = _ENTRY_ISSUE.search(text)
    # Description = the bullet minus its trailing [tag] and (#N) marker (both rendered separately).
    stripped = _ENTRY_ISSUE.sub("", _ENTRY_TAG.sub("", text))
    description = re.sub(r"\s+", " ", stripped).strip()
    return ChangeEntry(
        version=version,
        cls=cls,
        steps=steps,
        description=description,
        issue=issue_match.group(1) if issue_match else None,
    )


def parse_changelog(text: str) -> list[ChangeEntry]:
    """Extract tagged change entries grouped under their version headers.

    HTML comments (``<!-- … -->``, the next-release template) are stripped first so
    example entries never count. A bullet may wrap across lines — continuation lines
    (indented, no leading ``-``) are joined onto it before the ``[class; steps …]``
    tag is parsed. Untagged bullets and table rows are ignored. Order is preserved
    (newest first).

    Args:
        text: The full ``CHANGELOG.md`` contents.

    Returns:
        The list of parsed :class:`ChangeEntry`.
    """
    body = _HTML_COMMENT.sub("", text)
    entries: list[ChangeEntry] = []
    for section in _SECTION.finditer(body):
        version = parse_version(section.group(1))
        for bullet in _BULLET.finditer(section.group(2)):
            entry = _parse_entry_text(bullet.group(1), version)
            if entry is not None:
                entries.append(entry)
    return entries


def compute_delta(from_v: Version, to_v: Version, entries: list[ChangeEntry]) -> list[ChangeEntry]:
    """Entries newer than the skill's version and no newer than the generator's.

    Half-open on the low end (``from_v`` exclusive — the skill already has it) and
    closed on the high end (``to_v`` inclusive).
    """
    return [e for e in entries if from_v < e.version <= to_v]


@dataclass
class Manifest:
    """A generated skill's ``.book-to-skill.json``, kept as raw data plus its path."""

    path: Path
    data: dict[str, object]

    @property
    def version(self) -> Version:
        return parse_version(str(self.data["generator_version"]))

    @property
    def source_sha256(self) -> str:
        return str(self.data.get("source_sha256", ""))

    def bump(self, to_version: str, *, today: str | None = None) -> None:
        """Set the generator version (and regenerate the ``generated`` date) and save."""
        self.data["generator_version"] = to_version
        self.data["generated"] = today or date.today().isoformat()
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")


def load_manifest(skill_dir: Path) -> Manifest | None:
    """Load ``<skill_dir>/.book-to-skill.json``, or None if the skill predates manifests."""
    path = skill_dir / MANIFEST_NAME
    if not path.is_file():
        return None
    return Manifest(path=path, data=json.loads(path.read_text(encoding="utf-8")))


def verify_source(skill_dir: Path, manifest: Manifest) -> bool:
    """True when the archived ``.source/`` matches the manifest's source hash.

    The original document is not needed: ``.source/metadata.json`` carries the
    ``source_sha256`` recorded at extraction time, which must equal the manifest's.
    """
    src_meta = skill_dir / SOURCE_DIR_NAME / "metadata.json"
    full_text = skill_dir / SOURCE_DIR_NAME / "full_text.txt"
    if not src_meta.is_file() or not full_text.is_file():
        return False
    data = json.loads(src_meta.read_text(encoding="utf-8"))
    return str(data.get("source_sha256", "")) == manifest.source_sha256 != ""


@dataclass
class UpgradePlan:
    """The deterministic decision: which changes apply and whether source is ready."""

    from_version: str
    to_version: str
    up_to_date: bool
    additive: list[ChangeEntry] = field(default_factory=list)
    transform: list[ChangeEntry] = field(default_factory=list)
    regenerate: list[ChangeEntry] = field(default_factory=list)
    skipped: list[ChangeEntry] = field(default_factory=list)
    source_ok: bool = False

    @property
    def needs_source(self) -> bool:
        return bool(self.regenerate)

    @property
    def is_noop(self) -> bool:
        return self.up_to_date or not (self.additive or self.transform or self.regenerate)


def build_plan(skill_dir: Path, current_version: str, changelog_text: str) -> UpgradePlan:
    """Diff a skill's manifest against the changelog into an :class:`UpgradePlan`.

    Args:
        skill_dir: The generated skill directory (must contain a manifest).
        current_version: The generator's current ``__version__``.
        changelog_text: The repo ``CHANGELOG.md`` contents.

    Returns:
        The grouped, source-checked upgrade plan.

    Raises:
        FileNotFoundError: If the skill has no manifest (caller handles fallback).
    """
    manifest = load_manifest(skill_dir)
    if manifest is None:
        raise FileNotFoundError(skill_dir / MANIFEST_NAME)
    from_v, to_v = manifest.version, parse_version(current_version)
    plan = UpgradePlan(
        from_version=".".join(map(str, from_v)),
        to_version=current_version,
        up_to_date=from_v >= to_v,
    )
    for entry in compute_delta(from_v, to_v, parse_changelog(changelog_text)):
        bucket = {
            "additive": plan.additive,
            "transform": plan.transform,
            "regenerate": plan.regenerate,
        }.get(entry.cls, plan.skipped)
        bucket.append(entry)
    plan.source_ok = verify_source(skill_dir, manifest)
    return plan


@dataclass
class ApplyResult:
    """Outcome of applying a plan: what changed mechanically and what the model still owes."""

    changed_files: list[str]
    remaining: list[ChangeEntry]
    bumped: bool


def apply_plan(
    skill_dir: Path,
    plan: UpgradePlan,
    current_version: str,
    registry: dict[str | None, TransformFn] | None = None,
) -> ApplyResult:
    """Run mechanical transforms; report what still needs model-backed regeneration.

    Additive/transform entries with a registered mechanical transform are applied in
    place. Everything else (no registered transform, or any ``regenerate`` entry) is
    returned as ``remaining`` for the SKILL.md flow to generate. The manifest is
    bumped **only** when nothing remains — so version reflects a fully upgraded skill.
    """
    registry = registry or {}
    source_dir = skill_dir / SOURCE_DIR_NAME
    changed: list[str] = []
    remaining: list[ChangeEntry] = list(plan.regenerate)
    for entry in [*plan.transform, *plan.additive]:
        transform = registry.get(entry.issue)
        if transform is None:
            remaining.append(entry)
            continue
        changed.extend(transform(skill_dir, source_dir))
    bumped = False
    manifest = load_manifest(skill_dir)
    if manifest is not None and not remaining and not plan.up_to_date:
        manifest.bump(current_version)
        bumped = True
    return ApplyResult(changed_files=changed, remaining=remaining, bumped=bumped)


def _fmt_entry(entry: ChangeEntry) -> str:
    issue = f" (#{entry.issue})" if entry.issue else ""
    steps = f" — steps {', '.join(entry.steps)}" if entry.steps else ""
    return f"    - {entry.description}{issue}{steps}"


def render_plan(plan: UpgradePlan) -> str:
    """Human-readable plan for ``--dry-run`` and pre-apply confirmation."""
    if plan.up_to_date:
        return f"Skill is already current (v{plan.from_version}). Nothing to do."
    lines = [f"Upgrade plan: v{plan.from_version} → v{plan.to_version}"]
    groups = (
        ("additive (new files, cheap)", plan.additive),
        ("transform (rewrite in place)", plan.transform),
        ("regenerate (re-read source)", plan.regenerate),
        ("skipped (generator-only)", plan.skipped),
    )
    for title, items in groups:
        if items:
            lines.append(f"  {title}:")
            lines.extend(_fmt_entry(e) for e in items)
    if plan.needs_source:
        state = "OK" if plan.source_ok else "MISSING — re-extract needed"
        lines.append(f"  archived .source/: {state}")
    if plan.is_noop:
        lines.append("  (no applicable changes)")
    return "\n".join(lines)
