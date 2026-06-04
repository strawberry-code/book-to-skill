"""Generic Chain-of-Responsibility runner over a format's extractor list.

``run_chain`` is pure with respect to console output: it tries each in-mode,
available extractor in order, returns the first non-empty result, and records an
``Attempt`` per strategy so the CLI can render the familiar "Trying X… OK"
narration without the core ever printing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bookextract.formats import FormatSpec
from bookextract.types import ExtractionMode, PageReporter

#: Per-strategy result. ``ok`` short-circuits the chain.
Outcome = Literal["ok", "unavailable", "empty"]


@dataclass(frozen=True)
class Attempt:
    name: str
    outcome: Outcome


@dataclass(frozen=True)
class ChainResult:
    text: str | None
    method: str | None
    attempts: tuple[Attempt, ...]

    @property
    def succeeded(self) -> bool:
        return self.text is not None


def run_chain(
    spec: FormatSpec,
    path: str,
    mode: ExtractionMode,
    reporter: PageReporter | None = None,
) -> ChainResult:
    """Try each in-mode extractor in order; return the first that yields text.

    Args:
        spec: The format whose extractor chain to run.
        path: Filesystem path to the document.
        mode: Active extraction mode; extractors not serving this mode are
            skipped entirely (e.g. Docling outside ``technical``).
        reporter: Optional progress callback forwarded to each extractor.

    Returns:
        A :class:`ChainResult` with the winning text and method, plus an
        :class:`Attempt` record per strategy tried. ``text``/``method`` are
        ``None`` when every strategy was unavailable or produced no text.
    """
    attempts: list[Attempt] = []
    for extractor in spec.extractors:
        if mode not in extractor.modes:
            continue
        if not extractor.available():
            attempts.append(Attempt(extractor.name, "unavailable"))
            continue
        text = extractor.extract(path, reporter)
        if text and text.strip():
            attempts.append(Attempt(extractor.name, "ok"))
            return ChainResult(text, extractor.name, tuple(attempts))
        attempts.append(Attempt(extractor.name, "empty"))
    return ChainResult(None, None, tuple(attempts))
