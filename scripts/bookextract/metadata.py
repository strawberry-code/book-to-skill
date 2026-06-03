"""Pure metadata assembly for metadata.json.

Format-agnostic: it receives the already-computed dynamic count key/value and
never imports a parser library. One frozen-dataclass argument keeps the call
within the project's strict argument-count limit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

_WORDS_PER_TOKEN: Final[float] = 0.75  # approximate
_TOKENS_PER_K: Final[int] = 1000


def estimate_tokens(text: str) -> int:
    """Estimate the LLM token count from a word count.

    Args:
        text: The text to measure.

    Returns:
        Approximate token count (words divided by an empirical ratio).
    """
    return int(len(text.split()) / _WORDS_PER_TOKEN)


@dataclass(frozen=True)
class MetadataInputs:
    """Everything ``build_metadata`` needs, grouped to keep arity low."""

    input_path: str
    document_format: str
    method: str
    extraction_mode: str
    text: str
    count_key: str
    count_value: int
    output_text_path: str
    file_size_mb: float
    structure: dict[str, object]


def build_metadata(mi: MetadataInputs) -> dict[str, object]:
    """Assemble the ``metadata.json`` payload. Pure: derives only from ``mi``.

    The dynamic ``count_key`` (``pages`` / ``spine_items`` / ``sections``) is
    spliced in by name so the schema matches the historical contract exactly.

    Args:
        mi: The grouped inputs (text, format, method, counts, paths, structure).

    Returns:
        The metadata mapping ready to serialize to JSON.
    """
    tokens = estimate_tokens(mi.text)
    return {
        "source_file": str(Path(mi.input_path).resolve()),
        "filename": Path(mi.input_path).name,
        "format": mi.document_format,
        "extraction_method": mi.method,
        "extraction_mode": mi.extraction_mode,
        "file_size_mb": round(mi.file_size_mb, 2),
        mi.count_key: mi.count_value,
        "chars": len(mi.text),
        "words": len(mi.text.split()),
        "estimated_tokens": tokens,
        "estimated_tokens_human": f"~{tokens // _TOKENS_PER_K}K",
        "output_text": mi.output_text_path,
        **mi.structure,
    }
