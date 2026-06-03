"""Foundational primitives shared across the package.

Holds the values that everything else depends on — the mode literal, the frozen
set of legal extraction-method names, the typed error the core raises instead of
calling ``sys.exit``, and the opt-in debug logger. Kept dependency-free so every
other module can import it without cycles.
"""

from __future__ import annotations

import sys
from typing import Final, Literal

#: PDF extraction mode selected by ``--mode``.
ExtractionMode = Literal["technical", "text"]

#: Every ``extraction_method`` string the project is allowed to emit into
#: metadata.json. A test asserts that each registered extractor's ``name`` is a
#: member of this set, so a typo cannot silently change the public contract.
#: Note the deliberate asymmetry: the stdlib EPUB path is ``"zipfile"`` while the
#: stdlib DOCX path is ``"zipfile-docx"`` — historical, do not "fix".
LEGAL_METHOD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "pdftotext",
        "pypdf",
        "pdfminer",
        "docling",
        "ebooklib",
        "zipfile",
        "python-docx",
        "zipfile-docx",
        "striprtf",
        "rtf-regex",
        "html-parser",
        "ebook-convert",
        "plain-text",
    }
)


class ExtractionError(Exception):
    """No extractor could produce text for the requested document.

    The pure core raises this; the CLI shell is the single place that turns it
    into a stderr message plus ``exit(1)``. This keeps ``sys.exit`` out of the
    extraction logic so it stays unit-testable.
    """

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


# Debug logging is opt-in and process-global. The flag defaults to off and is
# set once by the CLI from ``--debug`` / ``BOOK_SKILL_DEBUG`` — never read at
# import time, so tests that toggle it stay deterministic.
_DEBUG = False


def set_debug(enabled: bool) -> None:
    global _DEBUG
    _DEBUG = enabled


def log_debug(message: str) -> None:
    """Surface a swallowed-error cause on stderr, only when debugging is on."""
    if _DEBUG:
        print(f"[debug] {message}", file=sys.stderr)
