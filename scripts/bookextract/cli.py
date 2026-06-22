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
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, NoReturn, cast

from bookextract import __version__, deps
from bookextract.deps import OfferContext, normalize_install_mode
from bookextract.formats import (
    FormatSpec,
    sniff_extension,
    spec_for_extension,
    supported_formats_message,
)
from bookextract.metadata import MetadataInputs, build_metadata
from bookextract.pipeline import Attempt, ChainResult, run_chain
from bookextract.progress import page_progress
from bookextract.structure import detect_structure
from bookextract.types import ExtractionMode, set_debug
from bookextract.upgrade import (
    MANIFEST_NAME,
    SOURCE_DIR_NAME,
    ApplyResult,
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
    ctx = OfferContext(mode=mode, has_pdftotext=shutil.which("pdftotext") is not None)
    for offer in spec.deps:
        if offer.applies(ctx):
            deps.run_install_flow(offer, install_mode)


def _guard_calibre(spec: FormatSpec) -> None:
    """Exit early with guidance if a Calibre format needs ``ebook-convert``."""
    if spec.name == "ebook" and shutil.which("ebook-convert") is None:
        _die(
            "MOBI/AZW/AZW3 extraction requires Calibre's ebook-convert command. "
            "Install Calibre and ensure ebook-convert is on PATH, then rerun this command."
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
        )
    )
    output_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    _print_summary(metadata, job)


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
    _report_apply(apply_plan(skill_dir, plan, __version__))


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
