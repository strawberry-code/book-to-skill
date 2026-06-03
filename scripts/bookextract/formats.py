"""The single source of truth binding each document format to its behavior.

A :class:`FormatSpec` ties an extension set to its ordered extractor chain, its
page-count strategy + dynamic metadata key, and its dependency offers. The
registry and the magic-byte sniffer below let the CLI resolve any input to one
spec — collapsing what used to be four parallel ``if ext`` ladders into one
table.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from bookextract import extractors as ex
from bookextract.deps import DepOffer, OfferContext
from bookextract.extractors import Extractor
from bookextract.types import log_debug

_PDFINFO_TIMEOUT: Final[int] = 15
_MAGIC_HEADER_BYTES: Final[int] = 8


def _no_pages(_path: str) -> int:
    return 0


def count_pages(path: str) -> int:
    """PDF page count via pdfinfo, falling back to a pypdf reader length."""
    pages = _count_pages_pdfinfo(path)
    if pages is not None:
        return pages
    reader_cls = ex._pdf_reader_cls()
    if reader_cls is None:
        return 0
    try:
        with Path(path).open("rb") as handle:
            return len(reader_cls(handle).pages)
    except (OSError, ValueError) as exc:
        log_debug(f"pypdf page count failed: {exc}")
        return 0


def _count_pages_pdfinfo(path: str) -> int | None:
    if not shutil.which("pdfinfo"):
        return None
    try:
        result = subprocess.run(
            ["pdfinfo", path],
            capture_output=True,
            text=True,
            timeout=_PDFINFO_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log_debug(f"pdfinfo failed: {exc}")
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return None


def count_epub_chapters(path: str) -> int:
    """Approximate chapter count = number of spine itemrefs in the OPF."""
    import re

    try:
        with zipfile.ZipFile(path) as zf:
            opf_files = [n for n in zf.namelist() if n.endswith(".opf")]
            if not opf_files:
                return 0
            opf_text = zf.read(opf_files[0]).decode("utf-8", errors="replace")
            return len(re.findall(r"<itemref\b", opf_text))
    except (OSError, zipfile.BadZipFile) as exc:
        log_debug(f"count_epub_chapters failed: {exc}")
        return 0


@dataclass(frozen=True)
class FormatSpec:
    """How one document format is detected, extracted, counted, and supported."""

    name: str
    extensions: frozenset[str]
    extractors: tuple[Extractor, ...]
    count_key: str = "sections"
    count_pages: Callable[[str], int] = field(default=_no_pages)
    deps: tuple[DepOffer, ...] = ()
    install_hint: str | None = None  # shown on stderr when the whole chain fails


# --------------------------------------------------------------------------- #
# Dependency-offer predicates (runtime-conditional, data-driven)
# --------------------------------------------------------------------------- #


def _is_technical(ctx: OfferContext) -> bool:
    return ctx.mode == "technical"


def _no_pdftotext(ctx: OfferContext) -> bool:
    return not ctx.has_pdftotext


# --------------------------------------------------------------------------- #
# The format table
# --------------------------------------------------------------------------- #

_TEXT_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".txt", ".text", ".md", ".markdown", ".rst", ".adoc", ".asciidoc"}
)
_HTML_EXTENSIONS: Final[frozenset[str]] = frozenset({".html", ".htm", ".xhtml"})
_CALIBRE_EXTENSIONS: Final[frozenset[str]] = frozenset({".mobi", ".azw", ".azw3"})

_SPECS: Final[tuple[FormatSpec, ...]] = (
    FormatSpec(
        name="pdf",
        extensions=frozenset({".pdf"}),
        extractors=(
            ex.DoclingExtractor(),
            ex.PdftotextExtractor(),
            ex.PypdfExtractor(),
            ex.PdfminerExtractor(),
        ),
        count_key="pages",
        count_pages=count_pages,
        deps=(
            DepOffer(
                "Technical PDF extraction",
                ("docling",),
                "the PDF text fallback chain",
                applies=_is_technical,
            ),
            DepOffer(
                "PDF text extraction",
                ("pypdf", "pdfminer"),
                "any installed Python PDF parser; extraction fails if none are available",
                applies=_no_pdftotext,
            ),
        ),
        install_hint=(
            "Install one of: poppler-utils (pdftotext), pypdf, or pdfminer.six\n"
            "  sudo apt install poppler-utils\n"
            "  pip3 install pypdf\n"
            "  pip3 install pdfminer.six"
        ),
    ),
    FormatSpec(
        name="epub",
        extensions=frozenset({".epub"}),
        extractors=(ex.EbooklibExtractor(), ex.ZipfileEpubExtractor()),
        count_key="spine_items",
        count_pages=count_epub_chapters,
        deps=(DepOffer("EPUB extraction", ("ebooklib", "bs4"), "a stdlib ZIP/HTML parser"),),
        install_hint=(
            "Install ebooklib + beautifulsoup4 for best results:\n"
            "  pip3 install ebooklib beautifulsoup4"
        ),
    ),
    FormatSpec(
        name="docx",
        extensions=frozenset({".docx"}),
        extractors=(ex.PythonDocxExtractor(), ex.ZipfileDocxExtractor()),
        deps=(DepOffer("DOCX extraction", ("docx",), "a stdlib ZIP/XML parser"),),
        install_hint="Install python-docx for best results:\n  pip3 install python-docx",
    ),
    FormatSpec(
        name="rtf",
        extensions=frozenset({".rtf"}),
        extractors=(ex.StriprtfExtractor(), ex.RtfRegexExtractor()),
        deps=(DepOffer("RTF extraction", ("striprtf",), "a basic regex cleanup fallback"),),
    ),
    FormatSpec(
        name="html",
        extensions=_HTML_EXTENSIONS,
        extractors=(ex.HtmlExtractor(),),
        deps=(DepOffer("HTML extraction", ("bs4",), "a stdlib HTML parser"),),
    ),
    FormatSpec(
        name="text",
        extensions=_TEXT_EXTENSIONS,
        extractors=(ex.PlainTextExtractor(),),
    ),
    FormatSpec(
        name="ebook",
        extensions=_CALIBRE_EXTENSIONS,
        extractors=(ex.EbookConvertExtractor(),),
        install_hint="Install Calibre and ensure ebook-convert is on PATH.",
    ),
)

_BY_EXTENSION: Final[dict[str, FormatSpec]] = {
    extension: spec for spec in _SPECS for extension in spec.extensions
}

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(_BY_EXTENSION)
CALIBRE_EXTENSIONS: Final[frozenset[str]] = _CALIBRE_EXTENSIONS

#: ``format`` value to expose when a Calibre ebook is detected, etc. The metadata
#: ``format`` field uses the extension stem (historical), not ``spec.name``.


def spec_for_extension(ext: str) -> FormatSpec | None:
    return _BY_EXTENSION.get(ext.lower())


def all_specs() -> tuple[FormatSpec, ...]:
    return _SPECS


def supported_formats_message() -> str:
    return ", ".join(sorted(SUPPORTED_EXTENSIONS))


def sniff_extension(path: str) -> str | None:
    """Guess a supported extension from magic bytes for mis-named files.

    Returns ``.pdf`` / ``.epub`` / ``.docx`` when recognized, or ``None`` if the
    header is unknown or the ZIP container is an unsupported type.
    """
    with Path(path).open("rb") as handle:
        header = handle.read(_MAGIC_HEADER_BYTES)
    if header[:4] == b"%PDF":
        return ".pdf"
    if header[:2] == b"PK":
        return _sniff_zip_container(path)
    return None


def _sniff_zip_container(path: str) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "mimetype" in names and zf.read("mimetype").startswith(b"application/epub"):
                return ".epub"
            if "word/document.xml" in names:
                return ".docx"
    except (zipfile.BadZipFile, KeyError, OSError):
        return None
    return None
