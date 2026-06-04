"""Tests for scripts/extract.py.

Plain assert-style functions: run with `pytest tests/` or `python -m pytest`.
No pytest-specific API is used, so the same file also runs under any collector.
Fixtures (EPUB/DOCX/HTML/RTF) are built synthetically in-process — no binary
assets checked into the repo.
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from bookextract import deps, extractors, formats, structure  # noqa: E402
from bookextract.deps import InstallDecision, decide_install  # noqa: E402
from bookextract.extractors import (  # noqa: E402
    Extractor,
    ZipfileEpubExtractor,
    _resolve_zip_entry,
)
from bookextract.formats import all_specs, spec_for_extension  # noqa: E402
from bookextract.metadata import MetadataInputs, build_metadata  # noqa: E402
from bookextract.pipeline import run_chain  # noqa: E402
from bookextract.types import LEGAL_METHOD_NAMES  # noqa: E402

# --------------------------------------------------------------------------- #
# Fixtures builders
# --------------------------------------------------------------------------- #


def _write_epub(path: Path, opf_dir: str = "OEBPS") -> None:
    """Build a minimal valid-enough EPUB with the OPF in a subdirectory.

    This reproduces the spine-href bug: hrefs in the manifest are relative to
    the OPF directory (``OEBPS``), not the ZIP root. A naive ``zf.read(href)``
    raises KeyError and the chapter is lost.
    """
    opf_path = f"{opf_dir}/content.opf" if opf_dir else "content.opf"
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>
    <item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>"""
    ch1 = "<html><body><h1>Chapter One</h1><p>ALPHA_BODY_TEXT</p></body></html>"
    ch2 = "<html><body><h1>Chapter Two</h1><p>BETA_BODY_TEXT</p></body></html>"

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            f'<?xml version="1.0"?><container><rootfiles>'
            f'<rootfile full-path="{opf_path}"/></rootfiles></container>',
        )
        z.writestr(opf_path, opf)
        prefix = f"{opf_dir}/" if opf_dir else ""
        z.writestr(f"{prefix}chapter1.xhtml", ch1)
        z.writestr(f"{prefix}chapter2.xhtml", ch2)


def _write_pdf(path: Path, body: str = "GOLDEN_PDF_TEXT") -> None:
    """Build a minimal valid single-page PDF with extractable text.

    Object byte-offsets are computed programmatically so the xref table is
    correct — pdftotext / pypdf / pdfinfo all read it.
    """
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 24 Tf 72 700 Td (" + body.encode() + b") Tj ET"
    objs.append(
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
    )
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objs) + 1
    out += b"xref\n0 " + str(n).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(n).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    path.write_bytes(out)


def _write_docx(path: Path, body: str = "GOLDEN_DOCX_TEXT") -> None:
    ct = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    doc = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


def _write_html(path: Path, body: str = "GOLDEN_HTML_TEXT") -> None:
    path.write_text(f"<html><body><h1>Title</h1><p>{body}</p></body></html>", encoding="utf-8")


def _write_rtf(path: Path, body: str = "GOLDEN_RTF_TEXT") -> None:
    path.write_text(r"{\rtf1\ansi " + body + r"\par}", encoding="utf-8")


def _write_txt(path: Path, body: str = "GOLDEN_TXT_TEXT") -> None:
    path.write_text(f"{body}\nmore lines\n", encoding="utf-8")


# Fields always present in metadata.json, independent of format. The 15th key is
# the dynamic count key (pages / spine_items / sections). This is the contract.
_FIXED_META_KEYS = frozenset(
    {
        "source_file",
        "filename",
        "format",
        "extraction_method",
        "extraction_mode",
        "file_size_mb",
        "chars",
        "words",
        "estimated_tokens",
        "estimated_tokens_human",
        "output_text",
        "chapters_detected",
        "chapter_headings_sample",
        "has_toc",
    }
)


def _run_extract(fixture: Path, workdir: Path) -> dict:
    """Run the real CLI on a fixture and return the parsed metadata.json."""
    import json

    env = dict(os.environ, BOOK_SKILL_WORKDIR=str(workdir))
    script = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"
    result = subprocess.run(
        [sys.executable, str(script), str(fixture), "--no-install-missing"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return json.loads((workdir / "metadata.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# normalize_install_mode (argparse-fed resolution)
# --------------------------------------------------------------------------- #


def test_install_mode_default_ask(monkeypatch=None):
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    assert deps.normalize_install_mode(None, False) == "ask"


def test_install_mode_no_flag_wins():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    # --no-install-missing overrides an explicit --install-missing yes
    assert deps.normalize_install_mode("yes", True) == "no"


def test_install_mode_bare_flag_is_yes():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    # argparse passes const="yes" for the bare flag
    assert deps.normalize_install_mode("yes", False) == "yes"


def test_install_mode_value_no():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    assert deps.normalize_install_mode("no", False) == "no"
    assert deps.normalize_install_mode("fallback", False) == "no"


def test_install_mode_env_var():
    os.environ["BOOK_SKILL_INSTALL_MISSING"] = "yes"
    try:
        assert deps.normalize_install_mode(None, False) == "yes"
        # explicit flag still overrides env
        assert deps.normalize_install_mode("no", False) == "no"
    finally:
        os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)


# --------------------------------------------------------------------------- #
# detect_structure
# --------------------------------------------------------------------------- #


def test_detect_structure_strong_headings():
    text = "Chapter 1\nbody\nCHAPTER 2\nmore\nCapitolo 3\n"
    result = structure.detect_structure(text)
    assert result["chapters_detected"] == 3


def test_detect_structure_numbered_list_not_counted():
    # Numbered list items inside prose must NOT register as chapters.
    text = (
        "1. The quick brown fox jumped over the lazy dog and kept running.\n"
        "2. Another long sentence that clearly is a list item, not a heading.\n"
    )
    result = structure.detect_structure(text)
    assert result["chapters_detected"] == 0


def test_detect_structure_numbered_heading_counted():
    text = "1. Introduction\n2. Methods\n3. Results\n"
    result = structure.detect_structure(text)
    assert result["chapters_detected"] == 3


def test_detect_structure_scans_past_50k():
    # A chapter heading far past the old 50k-char window must still be found.
    text = ("filler line\n" * 6000) + "Chapter 99\n"
    assert len(text) > 50000
    result = structure.detect_structure(text)
    assert result["chapters_detected"] == 1


def test_detect_structure_toc():
    assert structure.detect_structure("Table of Contents\n...")["has_toc"] is True
    assert structure.detect_structure("the contents of this book")["has_toc"] is False


# --------------------------------------------------------------------------- #
# strip_rtf_fallback
# --------------------------------------------------------------------------- #


def test_strip_rtf_fallback():
    raw = r"{\rtf1\ansi Hello\par World\tab end}"
    out = extractors.strip_rtf_fallback(raw)
    assert "Hello" in out
    assert "World" in out
    assert "\\rtf" not in out
    assert "{" not in out and "}" not in out


# --------------------------------------------------------------------------- #
# _resolve_zip_entry (spine href resolution)
# --------------------------------------------------------------------------- #


def test_resolve_zip_entry_subdir():
    names = {"OEBPS/chapter1.xhtml", "OEBPS/content.opf"}
    assert _resolve_zip_entry("chapter1.xhtml", "OEBPS", names) == "OEBPS/chapter1.xhtml"


def test_resolve_zip_entry_anchor_and_encoding():
    names = {"OEBPS/ch 1.xhtml"}
    # fragment stripped + percent-decoded
    assert _resolve_zip_entry("ch%201.xhtml#sec2", "OEBPS", names) == "OEBPS/ch 1.xhtml"


def test_resolve_zip_entry_basename_fallback():
    names = {"text/chapter1.xhtml"}
    # href resolves nowhere directly, basename match saves it
    assert _resolve_zip_entry("chapter1.xhtml", "OEBPS", names) == "text/chapter1.xhtml"


def test_resolve_zip_entry_miss():
    assert _resolve_zip_entry("nope.xhtml", "OEBPS", {"OEBPS/other.xhtml"}) is None


# --------------------------------------------------------------------------- #
# EPUB stdlib extractor — the spine bug end to end
# --------------------------------------------------------------------------- #


def test_extract_with_zipfile_opf_in_subdir(tmp_path):
    epub = tmp_path / "book.epub"
    _write_epub(epub, opf_dir="OEBPS")
    text = ZipfileEpubExtractor().extract(str(epub))
    assert text is not None
    assert "ALPHA_BODY_TEXT" in text
    assert "BETA_BODY_TEXT" in text


def test_count_epub_chapters(tmp_path):
    epub = tmp_path / "book.epub"
    _write_epub(epub)
    assert formats.count_epub_chapters(str(epub)) == 2


# --------------------------------------------------------------------------- #
# Magic-byte sniffing — EPUB with a non-epub extension, end to end via CLI
# --------------------------------------------------------------------------- #


def test_magic_byte_sniff_epub(tmp_path):
    disguised = tmp_path / "book.dat"  # wrong extension on purpose
    _write_epub(disguised, opf_dir="OEBPS")
    workdir = tmp_path / "work"
    env = dict(os.environ, BOOK_SKILL_WORKDIR=str(workdir))
    script = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"

    result = subprocess.run(
        [sys.executable, str(script), str(disguised), "--no-install-missing"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    full_text = (workdir / "full_text.txt").read_text(encoding="utf-8")
    assert "ALPHA_BODY_TEXT" in full_text


# --------------------------------------------------------------------------- #
# Contract guards (Step 0 safety net) — golden metadata + CLI bootstrap
# --------------------------------------------------------------------------- #


def _golden_case(tmp_path, name, writer, expected_key):
    fixture = tmp_path / f"book.{name}"
    writer(fixture)
    meta = _run_extract(fixture, tmp_path / f"work_{name}")
    assert set(meta) == _FIXED_META_KEYS | {expected_key}, (
        f"metadata key set drifted for {name}: {sorted(meta)}"
    )
    assert expected_key in meta


def test_golden_metadata_epub(tmp_path):
    fixture = tmp_path / "book.epub"
    _write_epub(fixture)
    meta = _run_extract(fixture, tmp_path / "work")
    assert set(meta) == _FIXED_META_KEYS | {"spine_items"}


def test_golden_metadata_pdf(tmp_path):
    _golden_case(tmp_path, "pdf", _write_pdf, "pages")


def test_golden_metadata_txt(tmp_path):
    _golden_case(tmp_path, "txt", _write_txt, "sections")


def test_golden_metadata_html(tmp_path):
    _golden_case(tmp_path, "html", _write_html, "sections")


def test_golden_metadata_rtf(tmp_path):
    _golden_case(tmp_path, "rtf", _write_rtf, "sections")


def test_golden_metadata_docx(tmp_path):
    _golden_case(tmp_path, "docx", _write_docx, "sections")


def test_cli_help_from_other_cwd(tmp_path):
    # Guards the sys.path bootstrap: extract.py must import its package no matter
    # the working directory it is launched from.
    script = Path(__file__).resolve().parents[1] / "scripts" / "extract.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


# --------------------------------------------------------------------------- #
# New seams unlocked by the refactor: protocol / pipeline / metadata / deps
# --------------------------------------------------------------------------- #


class _FakeExtractor:
    """Minimal Extractor for exercising run_chain without real files."""

    def __init__(self, name, *, text, available=True, modes=("technical", "text")):
        self.name = name
        self.modes = modes
        self._text = text
        self._available = available

    def available(self):
        return self._available

    def extract(self, path, reporter=None):  # noqa: ARG002 - parity with the protocol
        if reporter is not None and self._text:
            reporter(1)
        return self._text


def _spec_with(extractors_tuple):
    return formats.FormatSpec(
        name="fake", extensions=frozenset({".fake"}), extractors=extractors_tuple
    )


def test_registered_extractor_names_are_legal():
    for spec in all_specs():
        for extractor in spec.extractors:
            assert isinstance(extractor, Extractor)
            assert extractor.name in LEGAL_METHOD_NAMES


def test_format_default_count_key_is_sections():
    assert spec_for_extension(".txt").count_key == "sections"
    assert spec_for_extension(".pdf").count_key == "pages"
    assert spec_for_extension(".epub").count_key == "spine_items"


def test_run_chain_order_and_short_circuit():
    spec = _spec_with(
        (
            _FakeExtractor("a", text=None, available=False),
            _FakeExtractor("b", text=""),
            _FakeExtractor("c", text="WON"),
            _FakeExtractor("d", text="never reached"),
        )
    )
    result = run_chain(spec, "x", "text")
    assert result.text == "WON"
    assert result.method == "c"
    assert [a.name for a in result.attempts] == ["a", "b", "c"]
    assert [a.outcome for a in result.attempts] == ["unavailable", "empty", "ok"]


def test_run_chain_all_fail_returns_none():
    spec = _spec_with((_FakeExtractor("a", text=None, available=False),))
    result = run_chain(spec, "x", "text")
    assert result.text is None
    assert result.method is None
    assert result.succeeded is False


def test_run_chain_skips_out_of_mode():
    spec = _spec_with(
        (
            _FakeExtractor("tech-only", text="T", modes=("technical",)),
            _FakeExtractor("text-ok", text="X"),
        )
    )
    # In text mode the technical-only extractor must be skipped entirely.
    result = run_chain(spec, "x", "text")
    assert result.method == "text-ok"
    assert [a.name for a in result.attempts] == ["text-ok"]


def test_decide_install_matrix():
    yes = deps.decide_install("yes", is_tty=False, has_missing=True)
    assert yes is InstallDecision.INSTALL
    ask = deps.decide_install("ask", is_tty=True, has_missing=True)
    assert ask is InstallDecision.ASK_USER
    ask_no_tty = deps.decide_install("ask", is_tty=False, has_missing=True)
    assert ask_no_tty is InstallDecision.USE_FALLBACK
    nothing = deps.decide_install("yes", is_tty=True, has_missing=False)
    assert nothing is InstallDecision.USE_FALLBACK


def test_build_metadata_is_pure():
    mi = MetadataInputs(
        input_path="/tmp/sample.pdf",
        document_format="pdf",
        method="pdftotext",
        extraction_mode="text",
        text="alpha beta gamma",
        count_key="pages",
        count_value=7,
        output_text_path="/work/full_text.txt",
        file_size_mb=1.234,
        structure={"chapters_detected": 2, "chapter_headings_sample": [], "has_toc": True},
    )
    meta = build_metadata(mi)
    assert meta["filename"] == "sample.pdf"
    assert meta["format"] == "pdf"
    assert meta["pages"] == 7
    assert meta["words"] == 3
    assert meta["file_size_mb"] == 1.23
    assert meta["has_toc"] is True
    assert set(meta) == _FIXED_META_KEYS | {"pages"}


def test_run_chain_forwards_reporter():
    spec = _spec_with((_FakeExtractor("c", text="WON"),))
    ticks = []
    run_chain(spec, "x", "text", lambda n: ticks.append(n))
    assert ticks == [1]


def test_page_progress_disabled_is_noop():
    from bookextract.progress import page_progress

    with page_progress(10, "x", enabled=False) as reporter:
        reporter(5)  # must not raise, renders nothing
    assert callable(reporter)


def test_pypdf_extractor_ticks_per_page(tmp_path):
    from bookextract.extractors import PypdfExtractor

    pdf = tmp_path / "p.pdf"
    _write_pdf(pdf)
    extractor = PypdfExtractor()
    if not extractor.available():
        return  # pypdf not installed in this environment
    ticks = []
    text = extractor.extract(str(pdf), lambda n: ticks.append(n))
    assert text is not None
    assert sum(ticks) >= 1  # at least one page reported


def test_decide_install_via_imported_symbol():
    # decide_install is also importable directly (used by run_install_flow).
    assert decide_install("no", is_tty=True, has_missing=True) is InstallDecision.USE_FALLBACK


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
