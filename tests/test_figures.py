"""Tests for diagram/figure capture (#8): extractor → chain → sidecar."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract.cli import _write_figures  # noqa: E402
from bookextract.extractors import docling_figures  # noqa: E402
from bookextract.pipeline import run_chain  # noqa: E402
from bookextract.types import Figure  # noqa: E402

# --- chain wiring ----------------------------------------------------------


class _Ext:
    """Minimal extractor; optionally exposes pop_figures (a figure-capable strategy)."""

    modes = ("technical", "text")

    def __init__(self, name: str, text: str, figures: list[Figure] | None = None) -> None:
        self.name = name
        self._text = text
        self._figures = figures

    def available(self) -> bool:
        return True

    def extract(self, path: str, reporter: object = None) -> str:
        return self._text

    # only present when figures were supplied
    def pop_figures(self) -> list[Figure]:
        return self._figures or []


class _PlainExt(_Ext):
    pop_figures = None  # type: ignore[assignment]  # not a figure-capable extractor


def _spec(*extractors: object) -> object:
    return types.SimpleNamespace(extractors=extractors)


def test_chain_surfaces_winning_extractor_figures():
    figs = [Figure(page=34, caption="Figure 3.1 The value chain", kind="flowchart")]
    result = run_chain(_spec(_Ext("docling", "body text", figs)), "x.pdf", "technical")
    assert result.figures == tuple(figs)


def test_chain_figures_empty_for_plain_extractor():
    result = run_chain(_spec(_PlainExt("pdftotext", "body text")), "x.pdf", "text")
    assert result.figures == ()


# --- docling document walk (mocked, no real PDF) ---------------------------


def _picture(caption: str, page: int, cls: str | None = None, *, raise_cap: bool = False) -> object:
    annotations = (
        [types.SimpleNamespace(predicted_classes=[types.SimpleNamespace(class_name=cls)])]
        if cls
        else []
    )

    def caption_text(_doc: object) -> str:
        if raise_cap:
            raise ValueError("boom")
        return caption

    return types.SimpleNamespace(
        prov=[types.SimpleNamespace(page_no=page)],
        annotations=annotations,
        caption_text=caption_text,
    )


def test_docling_figures_captures_caption_page_kind():
    doc = types.SimpleNamespace(
        pictures=[_picture("Figure 1.1 Topology", 12, "diagram")]
    )
    figs = docling_figures(doc)
    assert figs == [Figure(page=12, caption="Figure 1.1 Topology", kind="diagram")]


def test_docling_figures_skips_uncaptioned_and_raising():
    doc = types.SimpleNamespace(
        pictures=[
            _picture("", 5),  # no caption → skip
            _picture("Figure 2.1 OK", 20),  # kept
            _picture("boom", 99, raise_cap=True),  # raises → skipped defensively
        ]
    )
    figs = docling_figures(doc)
    assert figs == [Figure(page=20, caption="Figure 2.1 OK", kind=None)]


def test_docling_figures_no_pictures_attr():
    assert docling_figures(types.SimpleNamespace()) == []


# --- sidecar writing -------------------------------------------------------


def test_write_figures_writes_sidecar(tmp_path: Path):
    figs = (
        Figure(page=34, caption="Figure 3.1 Value chain", kind="flowchart"),
        Figure(page=40, caption="Figure 3.2 Private API", kind=None),
    )
    n = _write_figures(tmp_path, figs)
    assert n == 2
    payload = json.loads((tmp_path / "figures.json").read_text())
    assert payload[0] == {"page": 34, "caption": "Figure 3.1 Value chain", "kind": "flowchart"}
    assert payload[1]["kind"] is None


def test_write_figures_no_file_when_empty(tmp_path: Path):
    assert _write_figures(tmp_path, ()) == 0
    assert not (tmp_path / "figures.json").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
