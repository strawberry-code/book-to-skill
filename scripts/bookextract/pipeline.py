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
from bookextract.types import ExtractionMode

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


def run_chain(spec: FormatSpec, path: str, mode: ExtractionMode) -> ChainResult:
    """Try each in-mode extractor in order; return the first that yields text."""
    attempts: list[Attempt] = []
    for extractor in spec.extractors:
        if mode not in extractor.modes:
            continue
        if not extractor.available():
            attempts.append(Attempt(extractor.name, "unavailable"))
            continue
        text = extractor.extract(path)
        if text and text.strip():
            attempts.append(Attempt(extractor.name, "ok"))
            return ChainResult(text, extractor.name, tuple(attempts))
        attempts.append(Attempt(extractor.name, "empty"))
    return ChainResult(None, None, tuple(attempts))
