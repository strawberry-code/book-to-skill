"""Command-line entrypoint: argument parsing, orchestration, and all I/O.

This is the imperative shell — the only module that reads argv/env, prints to the
console, writes files, and exits the process. Everything it calls is pure or
side-effect-isolated, which keeps the rest of the package testable.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn, cast

from bookextract import deps
from bookextract.deps import OfferContext, normalize_install_mode
from bookextract.formats import (
    FormatSpec,
    sniff_extension,
    spec_for_extension,
    supported_formats_message,
)
from bookextract.metadata import MetadataInputs, build_metadata
from bookextract.pipeline import Attempt, ChainResult, run_chain
from bookextract.structure import detect_structure
from bookextract.types import ExtractionMode, set_debug

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


def resolve_workdir() -> Path:
    default = str(Path(tempfile.gettempdir()) / "book_skill_work")
    return Path(os.environ.get("BOOK_SKILL_WORKDIR", default))


def build_arg_parser() -> argparse.ArgumentParser:
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
    print(f"ERROR: {message}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    raise SystemExit(1)


def _coerce_mode(raw: str) -> ExtractionMode:
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
    ctx = OfferContext(mode=mode, has_pdftotext=shutil.which("pdftotext") is not None)
    for offer in spec.deps:
        if offer.applies(ctx):
            deps.run_install_flow(offer, install_mode)


def _guard_calibre(spec: FormatSpec) -> None:
    if spec.name == "ebook" and shutil.which("ebook-convert") is None:
        _die(
            "MOBI/AZW/AZW3 extraction requires Calibre's ebook-convert command. "
            "Install Calibre and ensure ebook-convert is on PATH, then rerun this command."
        )


def _render_attempts(attempts: tuple[Attempt, ...]) -> None:
    for attempt in attempts:
        print(f"Trying {attempt.name}... {_OUTCOME_LABEL[attempt.outcome]}")


def _recorded_mode(spec: FormatSpec, requested: ExtractionMode, method: str) -> str:
    # A technical PDF that fell back to the text chain is recorded as 'text', so
    # the metadata reflects the path actually taken (not the requested mode).
    if spec.name == "pdf" and requested == "technical" and method != "docling":
        return "text"
    return requested


def _finish(job: _Job, result: ChainResult) -> None:
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
            count_value=job.spec.count_pages(job.input_path),
            output_text_path=str(output_text),
            file_size_mb=Path(job.input_path).stat().st_size / _BYTES_PER_MB,
            structure=detect_structure(result.text),
        )
    )
    output_meta.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    _print_summary(metadata, job)


def _print_summary(metadata: dict[str, object], job: _Job) -> None:
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


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.debug:
        set_debug(True)
    if not Path(args.input_path).exists():
        _die(f"File not found: {args.input_path}")

    ext, document_format = _resolve_format(args.input_path)
    spec = spec_for_extension(ext)
    if spec is None:
        _die(f"Unsupported format '{ext or '<none>'}'. Supported: {supported_formats_message()}")

    workdir = resolve_workdir()
    workdir.mkdir(parents=True, exist_ok=True)
    mode = _coerce_mode(args.mode)
    _offer_dependencies(
        spec, mode, normalize_install_mode(args.install_missing, args.no_install_missing)
    )
    _guard_calibre(spec)

    print(f"Extracting {document_format.upper()}: {args.input_path}")
    result = run_chain(spec, args.input_path, mode)
    _render_attempts(result.attempts)
    if not result.succeeded:
        _die(f"Could not extract text from {document_format.upper()}.", spec.install_hint)

    _finish(_Job(spec, args.input_path, document_format, mode, workdir), result)
