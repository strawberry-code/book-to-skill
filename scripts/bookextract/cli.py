"""Command-line entrypoint: argument parsing, orchestration, and all I/O.

This is the imperative shell — the only module that reads argv/env, prints to the
console, writes files, and exits the process. Everything it calls is pure or
side-effect-isolated, which keeps the rest of the package testable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Final, NoReturn, cast

from bookextract import __version__, deps
from bookextract.assemble import AssembleInputs, Source, assemble
from bookextract.batch import Match, match_sources
from bookextract.chunking import chunk_sections
from bookextract.deps import OfferContext, normalize_install_mode
from bookextract.formats import (
    FormatSpec,
    sniff_extension,
    spec_for_extension,
    supported_formats_message,
)
from bookextract.metadata import MetadataInputs, build_metadata
from bookextract.notes import Note, NoteValidationError, validate_note
from bookextract.okf_lint import DEFAULT_MIN_COVERAGE, format_report, lint_bundle
from bookextract.pageoffset import detect_page_offset, remap_citations
from bookextract.pipeline import Attempt, ChainResult, run_chain
from bookextract.progress import page_progress
from bookextract.structure import detect_structure
from bookextract.types import ExtractionMode, Figure, set_debug
from bookextract.upgrade import (
    MANIFEST_NAME,
    SOURCE_DIR_NAME,
    ApplyResult,
    TransformFn,
    apply_plan,
    build_plan,
    render_plan,
)

_DEFAULT_MODE: Final[ExtractionMode] = "text"
_VALID_MODES: Final[frozenset[str]] = frozenset({"technical", "text"})
_BYTES_PER_MB: Final[int] = 1024 * 1024
_TOKENS_PER_K: Final[int] = 1000
_OUTCOME_LABEL: Final[dict[str, str]] = {
    "ok": "OK",
    "unavailable": "not available",
    "empty": "empty",
}
_COUNT_LABEL: Final[dict[str, str]] = {
    "pages": "Pages",
    "spine_items": "Spine items",
    "sections": "Sections",
}
_NO_TOC_WARNING: Final[str] = (
    "   WARN    : No table of contents detected — chapter mapping in Step 3 "
    "will rely on heading scan only, which may miss or duplicate sections."
)


@dataclass(frozen=True)
class _Job:
    """Resolved per-run context, grouped to keep function arity small."""

    spec: FormatSpec
    input_path: str
    document_format: str
    mode: ExtractionMode
    workdir: Path
    count_value: int  # pages / spine_items / sections, computed once


@dataclass(frozen=True)
class _ExtractRequest:
    """Inputs for one extraction run, grouped to keep ``_extract_to_workdir`` arity low."""

    input_path: str
    mode: str
    install_mode: str
    workdir: Path
    debug: bool


def resolve_workdir() -> Path:
    """Return the output directory, honoring ``BOOK_SKILL_WORKDIR``.

    Returns:
        The configured workdir, or a ``book_skill_work`` folder under the system
        temp directory by default.
    """
    default = str(Path(tempfile.gettempdir()) / "book_skill_work")
    return Path(os.environ.get("BOOK_SKILL_WORKDIR", default))


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser.

    Returns:
        A parser accepting the input path and the ``--mode`` / ``--install-missing``
        / ``--no-install-missing`` / ``--debug`` options.
    """
    parser = argparse.ArgumentParser(
        prog="extract.py",
        description="Extract text from a document for book-to-skill processing.",
        epilog=f"Supported formats: {supported_formats_message()}",
    )
    parser.add_argument("input_path", help="path to the document to extract")
    parser.add_argument(
        "--mode",
        default=_DEFAULT_MODE,
        help="extraction mode for PDF: 'technical' (Docling, layout-aware) "
        "or 'text' (pdftotext chain). Default: text.",
    )
    _add_install_args(parser)
    return parser


def _add_install_args(parser: argparse.ArgumentParser) -> None:
    """Register the dependency-install and debug options on ``parser``."""
    parser.add_argument(
        "--install-missing",
        nargs="?",
        const="yes",
        default=None,
        metavar="ask|yes|no",
        help="install missing Python packages instead of using fallbacks. "
        "Bare flag means 'yes'. Also via BOOK_SKILL_INSTALL_MISSING env var.",
    )
    parser.add_argument(
        "--no-install-missing",
        action="store_true",
        help="never install; always use fallbacks (overrides --install-missing).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="log extractor fallbacks and swallowed errors to stderr. "
        "Also via BOOK_SKILL_DEBUG env var.",
    )


def _die(message: str, hint: str | None = None) -> NoReturn:
    """Print an error (and optional hint) to stderr and exit with status 1."""
    print(f"ERROR: {message}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    raise SystemExit(1)


def _coerce_mode(raw: str) -> ExtractionMode:
    """Normalize a raw ``--mode`` value, defaulting unknown values to ``text``."""
    mode = raw.lower()
    return mode if mode in _VALID_MODES else _DEFAULT_MODE  # type: ignore[return-value]


def _resolve_format(input_path: str) -> tuple[str, str]:
    """Return (extension, document_format), sniffing magic bytes if needed."""
    ext = Path(input_path).suffix.lower()
    if spec_for_extension(ext) is None:
        sniffed = sniff_extension(input_path)
        if sniffed is not None:
            ext = sniffed
    return ext, ext.lstrip(".")


def _offer_dependencies(spec: FormatSpec, mode: ExtractionMode, install_mode: str) -> None:
    """Run the applicable dependency offers for ``spec`` under the given modes."""
    ctx = OfferContext(
        mode=mode,
        has_pdftotext=shutil.which("pdftotext") is not None,
        has_ebook_convert=shutil.which("ebook-convert") is not None,
    )
    for offer in spec.deps:
        if offer.applies(ctx):
            deps.run_install_flow(offer, install_mode)


def _guard_calibre(spec: FormatSpec) -> None:
    """Exit early if a MOBI/AZW format has neither extraction backend available.

    Either Calibre's ``ebook-convert`` or the pure-Python ``mobi`` package works;
    only bail when both are missing (after the dependency offer has run).
    """
    if spec.name != "ebook":
        return
    import importlib.util

    if shutil.which("ebook-convert") is not None:
        return
    if importlib.util.find_spec("mobi") is not None:
        return
    _die(
        "MOBI/AZW/AZW3 extraction needs either Calibre's ebook-convert command "
        "or the 'mobi' Python package; neither is available.",
        "install one, then rerun: Calibre (ebook-convert on PATH), or `pip3 install mobi`",
    )


def _render_attempts(attempts: tuple[Attempt, ...]) -> None:
    """Print the per-extractor "Trying X… OK" narration."""
    for attempt in attempts:
        print(f"Trying {attempt.name}... {_OUTCOME_LABEL[attempt.outcome]}")


def _recorded_mode(spec: FormatSpec, requested: ExtractionMode, method: str) -> str:
    """Return the mode to record in metadata, reflecting the path actually taken.

    A technical PDF that fell back to the text chain is recorded as ``text`` so
    the metadata mirrors what really happened, not what was requested.

    Args:
        spec: The resolved format.
        requested: The mode the user asked for.
        method: The winning extractor's name.

    Returns:
        ``"technical"`` only when Docling actually produced the text, else
        ``requested`` (which is ``"text"`` for the PDF fallback case).
    """
    if spec.name == "pdf" and requested == "technical" and method != "docling":
        return "text"
    return requested


def _sha256(path: str) -> str:
    """Hex SHA-256 of the source file, streamed so large books stay off-heap.

    Recorded in metadata.json (and the skill manifest) so the upgrade flow can
    confirm a skill is being regenerated from the same source bytes.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finish(job: _Job, result: ChainResult) -> None:
    """Write outputs and print the summary for a successful extraction.

    Args:
        job: The resolved per-run context.
        result: The successful chain result (text and method are non-``None``).
    """
    assert result.text is not None and result.method is not None  # guaranteed by caller
    output_text = job.workdir / "full_text.txt"
    output_meta = job.workdir / "metadata.json"
    output_text.write_text(result.text, encoding="utf-8")
    figure_count = _write_figures(job.workdir, result.figures)

    metadata = build_metadata(
        MetadataInputs(
            input_path=job.input_path,
            document_format=job.document_format,
            method=result.method,
            extraction_mode=_recorded_mode(job.spec, job.mode, result.method),
            text=result.text,
            count_key=job.spec.count_key,
            count_value=job.count_value,
            output_text_path=str(output_text),
            file_size_mb=Path(job.input_path).stat().st_size / _BYTES_PER_MB,
            structure=detect_structure(result.text),
            generator_version=__version__,
            source_sha256=_sha256(job.input_path),
            page_offset=detect_page_offset(result.text),
            figure_count=figure_count,
        )
    )
    output_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    _print_summary(metadata, job)


def _write_figures(workdir: Path, figures: tuple[Figure, ...]) -> int:
    """Write captured figures (#8) to ``figures.json``; return how many. None → no file."""
    if not figures:
        return 0
    payload = [{"page": f.page, "caption": f.caption, "kind": f.kind} for f in figures]
    (workdir / "figures.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(figures)


def _print_summary(metadata: dict[str, object], job: _Job) -> None:
    """Print the human-facing "Extraction complete" summary block."""
    count_key = job.spec.count_key
    label = _COUNT_LABEL.get(count_key, count_key)
    tokens = cast(int, metadata["estimated_tokens"])
    words = cast(int, metadata["words"])
    fmt = cast(str, metadata["format"])
    print("\nExtraction complete:")
    print(f"   Format  : {fmt.upper()}")
    print(f"   Method  : {metadata['extraction_method']}")
    print(f"   {label}: {metadata[count_key]}")
    print(f"   Words   : {words:,}")
    print(f"   Tokens  : ~{tokens // _TOKENS_PER_K}K")
    print(f"   Chapters: {metadata['chapters_detected']} detected")
    figures = cast(int, metadata["figure_count"])
    if figures:
        print(f"   Figures : {figures} captured")
    print(f"   ToC     : {'yes' if metadata['has_toc'] else 'not detected'}")
    if not metadata["has_toc"]:
        print(_NO_TOC_WARNING)
    print(f"\n   Text -> {job.workdir / 'full_text.txt'}")
    print(f"   Meta -> {job.workdir / 'metadata.json'}")


def _is_docling_run(job: _Job) -> bool:
    # Docling can't report per-page progress, so technical PDF gets a spinner.
    return job.spec.name == "pdf" and job.mode == "technical"


def _progress_description(job: _Job) -> str:
    if _is_docling_run(job):
        return f"Extracting {job.count_value} pages with Docling"
    if job.count_value:
        unit = job.spec.count_key.replace("_", " ")  # pages / spine items
        return f"Extracting {job.count_value} {unit}"
    return f"Extracting {job.document_format.upper()}"


def _extract(job: _Job, *, debug: bool) -> ChainResult:
    """Run the chain, quantifying progress by each format's natural unit.

    A determinate bar is shown whenever the unit count is known and the backend
    can tick it (PDF pages via pypdf, EPUB chapters); Docling can't report
    per-page, so technical PDF shows an elapsed spinner instead. Formats without
    a count (HTML/RTF/plain text) extract too fast to warrant a display.

    Args:
        job: The resolved per-run context.
        debug: When ``True``, suppress the display (debug logging takes over).

    Returns:
        The chain result.
    """
    determinate = job.count_value > 0 and not _is_docling_run(job)
    enabled = sys.stdout.isatty() and not debug and (determinate or _is_docling_run(job))
    total = job.count_value if determinate else None
    with page_progress(total, _progress_description(job), enabled=enabled) as reporter:
        return run_chain(job.spec, job.input_path, job.mode, reporter)


def _resolve_spec(input_path: str) -> tuple[str, FormatSpec]:
    """Resolve the input path to its document format and :class:`FormatSpec`.

    Args:
        input_path: Path to the document (validated to exist by the caller).

    Returns:
        The ``(document_format, spec)`` pair. Exits the process if the format is
        unsupported even after magic-byte sniffing.
    """
    ext, document_format = _resolve_format(input_path)
    spec = spec_for_extension(ext)
    if spec is None:
        _die(f"Unsupported format '{ext or '<none>'}'. Supported: {supported_formats_message()}")
    return document_format, spec


def _default_changelog() -> Path:
    """Repo ``CHANGELOG.md`` resolved relative to this package (root/scripts/bookextract)."""
    return Path(__file__).resolve().parents[2] / "CHANGELOG.md"


def _report_apply(result: ApplyResult) -> None:
    """Print what an upgrade applied mechanically and what the model still owes."""
    if result.changed_files:
        print("Applied (mechanical):")
        for name in result.changed_files:
            print(f"   {name}")
    if result.remaining:
        print("\nModel-backed regeneration still required — run book-to-skill for:")
        for entry in result.remaining:
            issue = f" (#{entry.issue})" if entry.issue else ""
            steps = f" — steps {', '.join(entry.steps)}" if entry.steps else ""
            print(f"   {entry.description}{issue}{steps}")
        print("Manifest NOT bumped until these are regenerated.")
    elif result.bumped:
        print("\nManifest bumped — skill fully upgraded.")


# Skill files that may carry `[Ch N, p.PP]` grounding citations (chapters/*.md added
# dynamically). Used by the #11 mechanical transform.
_CITED_FILES: Final[tuple[str, ...]] = (
    "SKILL.md",
    "glossary.md",
    "patterns.md",
    "cheatsheet.md",
    "cues.md",
    "review-rules.md",
)


def _resolve_offset(source_dir: Path) -> int | None:
    """Page offset for a skill: archived ``metadata.json`` if present, else detect from text.

    Pre-#11 backfills wrote no ``page_offset`` key — fall back to detecting it from the
    archived ``full_text.txt`` so old skills can still be remapped deterministically.
    """
    meta = source_dir / "metadata.json"
    if meta.is_file():
        data = json.loads(meta.read_text(encoding="utf-8"))
        if "page_offset" in data:
            value = data["page_offset"]
            return value if isinstance(value, int) else None
    text_path = source_dir / "full_text.txt"
    if text_path.is_file():
        return detect_page_offset(text_path.read_text(encoding="utf-8", errors="replace"))
    return None


def _remap_file(path: Path, offset: int | None) -> bool:
    """Remap citations in one file in place; return whether it changed."""
    if not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    updated, changed = remap_citations(original, offset)
    if changed and updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _record_offset(skill_dir: Path, offset: int | None) -> None:
    """Persist the resolved offset into the skill manifest for self-documentation."""
    manifest = skill_dir / MANIFEST_NAME
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["page_offset"] = offset
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _page_offset_transform(skill_dir: Path, source_dir: Path) -> list[str]:
    """#11 mechanical transform: remap physical-page citations to printed folios.

    Resolves the front-matter offset deterministically, rewrites every ``[Ch N, p.PP]``
    page across the skill's content files (printed folio when known, ``(pdf)`` label when
    not), and records the offset in the manifest. No model, no source re-read.
    """
    offset = _resolve_offset(source_dir)
    targets = [skill_dir / name for name in _CITED_FILES]
    targets += sorted((skill_dir / "chapters").glob("*.md"))
    changed = [
        path.relative_to(skill_dir).as_posix() for path in targets if _remap_file(path, offset)
    ]
    _record_offset(skill_dir, offset)
    return changed


# Feature #9 — the stack-personalization capability injected into a code skill's SKILL.md.
# Static and generic: the per-query re-rendering is done by the agent at use time from the
# skill's own chapters, so the instruction is the feature.
_PERSONALIZE_HEADING: Final[str] = "## Adapting examples to your stack"
_SCOPE_HEADING: Final[str] = "## Scope & Limits"
_PERSONALIZE_SECTION: Final[str] = f"""{_PERSONALIZE_HEADING}

Ask for any concept "in <your stack>" — e.g. "the Specification pattern in TypeScript",
"show this in Go", "Spring instead of Quarkus". I re-express the book's example in your
language/framework while preserving its intent, and I keep the original:

1. Read the cited example from the relevant `chapters/chNN-*.md` (with its `[Ch N]` citation).
2. Re-render it in your stack idiomatically — same behaviour and invariants, your syntax.
3. Show the original (or its citation) alongside, so the mapping is auditable; the book
   stays the source of truth. I never present a translation as if it were the book's text.

If a construct has no faithful equivalent in your stack, I say so rather than forcing it.
"""
_ARG_HINT: Final[re.Pattern[str]] = re.compile(r"^(argument-hint:\s*\[)(.*?)(\]\s*)$", re.MULTILINE)


def _inject_personalize(text: str) -> str:
    """Insert the personalize section before ``## Scope & Limits``, else append it. Idempotent."""
    if _PERSONALIZE_HEADING in text:
        return text
    if _SCOPE_HEADING in text:
        return text.replace(_SCOPE_HEADING, f"{_PERSONALIZE_SECTION}\n---\n\n{_SCOPE_HEADING}", 1)
    return f"{text.rstrip()}\n\n---\n\n{_PERSONALIZE_SECTION}"


def _widen_arg_hint(text: str) -> str:
    """Add a ``"<topic> in <stack>"`` cue to a ``[…]``-form argument-hint, once, if missing."""

    def repl(match: re.Match[str]) -> str:
        inner = str(match.group(2))
        if "stack" in inner.lower():
            return str(match.group(0))
        return f'{match.group(1)}{inner}, or "<topic> in <stack>"{match.group(3)}'

    return _ARG_HINT.sub(repl, text, count=1)


def _personalize_transform(skill_dir: Path, _source_dir: Path) -> list[str]:
    """#9 mechanical transform: add the stack-personalization capability to code skills.

    Gated on the manifest ``reviewable`` flag (a book worth review rules has code examples
    to re-render); non-code skills get ``personalizable: false`` and no SKILL.md change.
    No model, no source re-read.
    """
    manifest_path = skill_dir / MANIFEST_NAME
    data = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
    )
    reviewable = bool(data.get("reviewable")) if data else False
    changed: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if reviewable and skill_md.is_file():
        original = skill_md.read_text(encoding="utf-8")
        updated = _widen_arg_hint(_inject_personalize(original))
        if updated != original:
            skill_md.write_text(updated, encoding="utf-8")
            changed.append("SKILL.md")
    if data is not None:
        data["personalizable"] = reviewable
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        manifest_path.write_text(payload, encoding="utf-8")
    return changed


# Issue-number → mechanical transform. The upgrade flow applies these in place without
# a model call (the payoff of the ``transform`` migration class).
_UPGRADE_TRANSFORMS: Final[dict[str | None, TransformFn]] = {
    "9": _personalize_transform,
    "11": _page_offset_transform,
}


def run_upgrade(argv: list[str]) -> None:
    """Deterministic ``upgrade`` subcommand: plan the skill update, optionally apply it.

    Reads the skill's manifest, diffs it against ``CHANGELOG.md``, and prints the
    plan. ``--dry-run`` stops there. Otherwise mechanical transforms are applied and
    any model-backed steps are reported; the manifest is bumped only when none remain.
    """
    parser = argparse.ArgumentParser(
        prog="extract.py upgrade",
        description="Plan/apply an upgrade of a generated skill to the current generator version.",
    )
    parser.add_argument("skill_dir", help="path to the generated skill directory")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and exit without writing"
    )
    parser.add_argument(
        "--changelog", default=None, help="override path to CHANGELOG.md (default: repo root)"
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="reconstruct provenance for a pre-provenance skill (requires --source)",
    )
    parser.add_argument("--source", default=None, help="original document path (with --backfill)")
    parser.add_argument(
        "--pin", default="0.0.0", help="version to pin the backfilled manifest at (default 0.0.0)"
    )
    parser.add_argument(
        "--mode", default="text", help="extraction mode for --backfill: text|technical"
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing manifest on --backfill"
    )
    parser.add_argument("--debug", action="store_true", help="verbose extractor logging")
    args = parser.parse_args(argv)

    skill_dir = Path(args.skill_dir)
    if not skill_dir.is_dir():
        _die(f"Not a directory: {skill_dir}")
    if args.backfill:
        run_backfill(skill_dir, args)
        return
    changelog = Path(args.changelog) if args.changelog else _default_changelog()
    if not changelog.is_file():
        _die(f"CHANGELOG not found: {changelog}", "pass --changelog <path>")

    try:
        plan = build_plan(skill_dir, __version__, changelog.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _die(
            f"No {skill_dir.name}/.book-to-skill.json manifest.",
            "skill predates provenance — regenerate it from the original source.",
        )

    print(render_plan(plan))
    if args.dry_run or plan.is_noop:
        return
    _report_apply(apply_plan(skill_dir, plan, __version__, _UPGRADE_TRANSFORMS))


def _extract_to_workdir(req: _ExtractRequest) -> dict[str, object]:
    """Run the extractor chain for ``req.input_path`` into ``req.workdir``; return its metadata.

    Shared by ``main`` (default extract) and ``run_backfill`` (provenance reconstruction):
    resolves the format, offers/declines optional deps per ``install_mode``, extracts, and
    writes ``full_text.txt`` + ``metadata.json``. Exits non-zero on unsupported format or a
    fully failed chain.
    """
    document_format, spec = _resolve_spec(req.input_path)
    req.workdir.mkdir(parents=True, exist_ok=True)
    coerced = _coerce_mode(req.mode)
    _offer_dependencies(spec, coerced, req.install_mode)
    _guard_calibre(spec)
    print(f"Extracting {document_format.upper()}: {req.input_path}")
    job = _Job(
        spec, req.input_path, document_format, coerced, req.workdir,
        spec.count_pages(req.input_path),
    )
    result = _extract(job, debug=req.debug)
    _render_attempts(result.attempts)
    if not result.succeeded:
        _die(f"Could not extract text from {document_format.upper()}.", spec.install_hint)
    _finish(job, result)
    return cast("dict[str, object]", json.loads((req.workdir / "metadata.json").read_text()))


def run_backfill(skill_dir: Path, args: argparse.Namespace) -> None:
    """Reconstruct provenance for a pre-provenance skill: extract source → ``.source/`` + manifest.

    Pre-provenance skills (generated before manifests existed) cannot be upgraded until
    they carry a manifest and an archived extraction. This extracts the original document
    into ``<skill>/.source/`` and writes ``.book-to-skill.json`` pinned at ``--pin`` (default
    ``0.0.0``) so a subsequent ``upgrade`` sees every content feature as applicable.
    """
    if not args.source:
        _die("--backfill requires --source <original document>")
    source = Path(args.source)
    if not source.is_file():
        _die(f"Source not found: {source}")
    manifest_path = skill_dir / MANIFEST_NAME
    if manifest_path.exists() and not args.force:
        _die(f"{skill_dir.name} already has a manifest.", "pass --force to overwrite")

    tmp = Path(tempfile.mkdtemp(prefix="book_skill_backfill_"))
    try:
        meta = _extract_to_workdir(
            _ExtractRequest(
                input_path=str(source),
                mode=args.mode,
                install_mode="no",
                workdir=tmp,
                debug=args.debug,
            )
        )
        source_dir = skill_dir / SOURCE_DIR_NAME
        source_dir.mkdir(parents=True, exist_ok=True)
        for name in ("full_text.txt", "metadata.json"):
            shutil.copy2(tmp / name, source_dir / name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    manifest = {
        "generator_version": args.pin,
        "source_sha256": meta["source_sha256"],
        "source_filename": meta["filename"],
        "book_type": "technical" if args.mode == "technical" else "text",
        "extraction_method": meta["extraction_method"],
        "generated": date.today().isoformat(),
        "steps_run": [],
        "artifacts": sorted(p.name for p in skill_dir.iterdir() if p.is_file()),
        "backfilled": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Backfilled {skill_dir.name}: manifest pinned v{args.pin}, "
        f".source/ archived via {meta['extraction_method']}. Run 'upgrade' to apply features."
    )


def _print_match_report(matches: list[Match]) -> list[Match]:
    """Print the confident/ambiguous/unmatched breakdown; return the confident ones."""
    confident = [m for m in matches if m.source]
    ambiguous = [m for m in matches if m.ambiguous]
    unmatched = [m for m in matches if not m.source and not m.ambiguous]
    print(
        f"Pre-provenance skills: {len(matches)} | confident: {len(confident)} | "
        f"ambiguous: {len(ambiguous)} | unmatched: {len(unmatched)}"
    )
    for m in confident:
        print(f"  OK   {m.slug}  <-  {(m.source or '')[:55]}  (score {m.score})")
    for m in ambiguous:
        print(f"  ??   {m.slug}  ambiguous (score {m.score}) — backfill manually with --source")
    for m in unmatched:
        print(f"  --   {m.slug}  no confident source (best {m.score})")
    return confident


def run_backfill_batch(argv: list[str]) -> None:
    """Batch-backfill every pre-provenance skill in a directory by fuzzy-matching sources.

    Scans ``skills_dir`` for skills lacking a manifest, matches each to a file in
    ``archive_dir`` by title-token overlap, and (with ``--apply``) backfills the
    confident matches. Ambiguous/unmatched skills are reported for manual handling
    rather than guessed. Dry-run by default.
    """
    parser = argparse.ArgumentParser(
        prog="extract.py backfill-batch",
        description="Fuzzy-match pre-provenance skills to archived sources and backfill them.",
    )
    parser.add_argument("skills_dir", help="directory of generated skills")
    parser.add_argument("archive_dir", help="directory of original source documents")
    parser.add_argument(
        "--apply", action="store_true", help="backfill confident matches (else dry-run)"
    )
    parser.add_argument("--pin", default="0.0.0", help="version to pin backfilled manifests at")
    parser.add_argument("--mode", default="text", help="extraction mode: text|technical")
    parser.add_argument("--threshold", type=float, default=0.6, help="min token-overlap to accept")
    parser.add_argument("--debug", action="store_true", help="verbose extractor logging")
    args = parser.parse_args(argv)

    skills_dir, archive = Path(args.skills_dir), Path(args.archive_dir)
    if not skills_dir.is_dir():
        _die(f"Not a directory: {skills_dir}")
    if not archive.is_dir():
        _die(f"Not a directory: {archive}")

    pre = [
        d.name
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and not (d / MANIFEST_NAME).exists()
    ]
    files = [p.name for p in archive.iterdir() if p.is_file()]
    confident = _print_match_report(match_sources(pre, files, threshold=args.threshold))
    if not args.apply:
        print("\n(dry-run — pass --apply to backfill the confident matches)")
        return

    done, failed = 0, []
    for m in confident:
        assert m.source is not None  # confident matches always carry a source
        namespace = argparse.Namespace(
            source=str(archive / m.source),
            pin=args.pin,
            mode=args.mode,
            force=False,
            debug=args.debug,
        )
        try:
            run_backfill(skills_dir / m.slug, namespace)
            done += 1
        except SystemExit:  # _die raises SystemExit on a single failure; keep the batch going
            failed.append(m.slug)
    print(f"\nBackfilled {done} | failed {len(failed)}: {failed}")


def run_lint(argv: list[str]) -> None:
    """Deterministic ``lint`` subcommand: validate an OKF bundle and exit by severity.

    Parses the bundle directory, runs :func:`~bookextract.okf_lint.lint_bundle`, prints
    the formatted report, and exits non-zero when there are error-level findings. Dangling
    links are errors by default; ``--allow-dangling`` downgrades them to warnings (OKF
    tolerates broken links, but zero-dangling is this project's default success criterion).
    ``--min-coverage`` sets the citation-coverage floor for atomic notes; ``--strict``
    promotes missing reciprocal ``## Related`` backlinks from warnings to errors.
    """
    parser = argparse.ArgumentParser(
        prog="extract.py lint",
        description="Validate an OKF v0.1 knowledge bundle (frontmatter, reserved files, links).",
    )
    parser.add_argument("bundle_dir", help="path to the OKF bundle directory")
    parser.add_argument(
        "--allow-dangling",
        action="store_true",
        help="report dangling links as warnings instead of errors",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=DEFAULT_MIN_COVERAGE,
        metavar="FRACTION",
        help="minimum share of atomic notes that must carry a chapter-ref citation "
        f"(default {DEFAULT_MIN_COVERAGE}); below it is an error",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat missing reciprocal '## Related' links as errors instead of warnings",
    )
    args = parser.parse_args(argv)

    bundle_dir = Path(args.bundle_dir)
    if not bundle_dir.is_dir():
        _die(f"Not a directory: {bundle_dir}")

    report = lint_bundle(
        bundle_dir,
        allow_dangling=args.allow_dangling,
        min_coverage=args.min_coverage,
        strict_links=args.strict,
    )
    print(format_report(report))
    sys.exit(0 if report.ok else 1)


def _slugify(value: str) -> str:
    """Lowercase kebab-case slug from an arbitrary filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "source"


def run_build_plan(argv: list[str]) -> None:
    """``build-plan`` subcommand: chunk an extraction into an orchestrated-build plan.

    Reads ``full_text.txt`` + ``metadata.json`` from the extraction dir, archives them
    into the bundle's ``raw/<slug>/``, and writes ``.mycelia/{plan,journal,source}.json``.
    The agent then fills ``source.json`` (title/authors), emits one Note-JSON file per
    chunk under ``.mycelia/chunks/``, and runs ``assemble``.
    """
    parser = argparse.ArgumentParser(
        prog="extract.py build-plan",
        description="Chunk an extracted document into an orchestrated-build plan.",
    )
    parser.add_argument("raw_dir", help="directory containing full_text.txt + metadata.json")
    parser.add_argument("--out", required=True, help="bundle directory to initialise")
    parser.add_argument("--slug", help="source slug (default: derived from the filename)")
    parser.add_argument("--target-words", type=int, default=8000, metavar="N")
    args = parser.parse_args(argv)

    raw_dir = Path(args.raw_dir)
    text_path, meta_path = raw_dir / "full_text.txt", raw_dir / "metadata.json"
    if not text_path.is_file() or not meta_path.is_file():
        _die(f"need full_text.txt + metadata.json in {raw_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    text = text_path.read_text(encoding="utf-8", errors="replace")
    slug = args.slug or _slugify(Path(meta.get("filename", raw_dir.name)).stem)

    bundle = Path(args.out)
    myc = bundle / ".mycelia"
    raw_dest = bundle / "raw" / slug
    raw_dest.mkdir(parents=True, exist_ok=True)
    (myc / "chunks").mkdir(parents=True, exist_ok=True)
    shutil.copy2(text_path, raw_dest / "full_text.txt")
    shutil.copy2(meta_path, raw_dest / "metadata.json")

    chunks = chunk_sections(text, target_words=args.target_words)
    plan = [
        {
            "id": chunk.index,
            "label": chunk.label,
            "chapter": chunk.chapter,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "words": chunk.words,
        }
        for chunk in chunks
    ]
    source = {
        "slug": slug,
        "title": Path(meta.get("filename", slug)).stem,
        "authors": [],
        "extraction_method": meta.get("extraction_method", "unknown"),
        "source_sha256": meta.get("source_sha256", ""),
        "source_filename": meta.get("filename", ""),
        "raw_rel": f"raw/{slug}/full_text.txt",
        "page_offset": meta.get("page_offset"),
    }
    (myc / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (myc / "journal.json").write_text(json.dumps({"done": []}, indent=2) + "\n", encoding="utf-8")
    (myc / "source.json").write_text(json.dumps(source, indent=2) + "\n", encoding="utf-8")
    print(f"Plan: {len(chunks)} chunk(s) -> {myc / 'plan.json'}")
    print(
        f"Next: fill {myc / 'source.json'} (title/authors), emit {myc / 'chunks'}/<id>.json "
        f"per chunk, then: book-extract assemble {bundle}"
    )


def _load_source(path: Path) -> Source:
    """Load the ``source.json`` written by ``build-plan`` into a :class:`Source`."""
    if not path.is_file():
        _die(f"missing {path} (run build-plan first)")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Source(
        slug=data["slug"],
        title=data["title"],
        authors=tuple(data.get("authors", [])),
        extraction_method=data.get("extraction_method", "unknown"),
        source_sha256=data.get("source_sha256", ""),
        source_filename=data.get("source_filename", ""),
        raw_rel=data["raw_rel"],
        page_offset=data.get("page_offset"),
    )


def _load_notes(chunks_dir: Path) -> list[Note]:
    """Load + validate every Note-JSON file the agent emitted under ``chunks/``."""
    notes: list[Note] = []
    for path in sorted(chunks_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("notes", []) if isinstance(payload, dict) else payload
        notes.extend(validate_note(obj) for obj in items)
    return notes


def run_assemble(argv: list[str]) -> None:
    """``assemble`` subcommand: validate chunk notes into an OKF bundle, then lint it."""
    parser = argparse.ArgumentParser(
        prog="extract.py assemble",
        description="Assemble validated Note JSON into an OKF bundle and lint it.",
    )
    parser.add_argument("bundle_dir", help="bundle directory initialised by build-plan")
    parser.add_argument("--timestamp", help="ISO timestamp (default: now)")
    args = parser.parse_args(argv)

    bundle = Path(args.bundle_dir)
    myc = bundle / ".mycelia"
    source = _load_source(myc / "source.json")
    raw_path = bundle / source.raw_rel
    if not raw_path.is_file():
        _die(f"missing raw text at {raw_path}")
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    timestamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        notes = _load_notes(myc / "chunks")
        if not notes:
            _die(f"no notes found in {myc / 'chunks'}")
        inputs = AssembleInputs(
            notes=notes, source=source, raw_text=raw_text, timestamp=timestamp
        )
        report = assemble(inputs, bundle)
    except NoteValidationError as exc:
        _die(str(exc), exc.hint)
    print(format_report(report))
    sys.exit(0 if report.ok else 1)


def main() -> None:
    """CLI entrypoint: parse args, extract, write outputs, or exit with an error.

    Resolves the input to a :class:`~bookextract.formats.FormatSpec`, offers any
    missing optional dependencies, runs the extractor chain, and writes
    ``full_text.txt`` + ``metadata.json``. Exits non-zero on unsupported formats,
    missing files, or a fully failed extraction chain.

    The ``upgrade`` subcommand (``extract.py upgrade <skill-dir>``) is dispatched
    before extraction parsing so the default positional path stays backward-compatible.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "upgrade":
        run_upgrade(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "backfill-batch":
        run_backfill_batch(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "lint":
        run_lint(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "build-plan":
        run_build_plan(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] == "assemble":
        run_assemble(sys.argv[2:])
        return
    args = build_arg_parser().parse_args()
    if args.debug:
        set_debug(True)
    if not Path(args.input_path).exists():
        _die(f"File not found: {args.input_path}")

    _extract_to_workdir(
        _ExtractRequest(
            input_path=args.input_path,
            mode=args.mode,
            install_mode=normalize_install_mode(args.install_missing, args.no_install_missing),
            workdir=resolve_workdir(),
            debug=args.debug,
        )
    )
