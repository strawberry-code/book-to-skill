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

import extract  # noqa: E402


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


# --------------------------------------------------------------------------- #
# normalize_install_mode (argparse-fed resolution)
# --------------------------------------------------------------------------- #

def test_install_mode_default_ask(monkeypatch=None):
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    assert extract.normalize_install_mode(None, False) == "ask"


def test_install_mode_no_flag_wins():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    # --no-install-missing overrides an explicit --install-missing yes
    assert extract.normalize_install_mode("yes", True) == "no"


def test_install_mode_bare_flag_is_yes():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    # argparse passes const="yes" for the bare flag
    assert extract.normalize_install_mode("yes", False) == "yes"


def test_install_mode_value_no():
    os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)
    assert extract.normalize_install_mode("no", False) == "no"
    assert extract.normalize_install_mode("fallback", False) == "no"


def test_install_mode_env_var():
    os.environ["BOOK_SKILL_INSTALL_MISSING"] = "yes"
    try:
        assert extract.normalize_install_mode(None, False) == "yes"
        # explicit flag still overrides env
        assert extract.normalize_install_mode("no", False) == "no"
    finally:
        os.environ.pop("BOOK_SKILL_INSTALL_MISSING", None)


# --------------------------------------------------------------------------- #
# detect_structure
# --------------------------------------------------------------------------- #

def test_detect_structure_strong_headings():
    text = "Chapter 1\nbody\nCHAPTER 2\nmore\nCapitolo 3\n"
    result = extract.detect_structure(text)
    assert result["chapters_detected"] == 3


def test_detect_structure_numbered_list_not_counted():
    # Numbered list items inside prose must NOT register as chapters.
    text = (
        "1. The quick brown fox jumped over the lazy dog and kept running.\n"
        "2. Another long sentence that clearly is a list item, not a heading.\n"
    )
    result = extract.detect_structure(text)
    assert result["chapters_detected"] == 0


def test_detect_structure_numbered_heading_counted():
    text = "1. Introduction\n2. Methods\n3. Results\n"
    result = extract.detect_structure(text)
    assert result["chapters_detected"] == 3


def test_detect_structure_scans_past_50k():
    # A chapter heading far past the old 50k-char window must still be found.
    text = ("filler line\n" * 6000) + "Chapter 99\n"
    assert len(text) > 50000
    result = extract.detect_structure(text)
    assert result["chapters_detected"] == 1


def test_detect_structure_toc():
    assert extract.detect_structure("Table of Contents\n...")["has_toc"] is True
    assert extract.detect_structure("the contents of this book")["has_toc"] is False


# --------------------------------------------------------------------------- #
# strip_rtf_fallback
# --------------------------------------------------------------------------- #

def test_strip_rtf_fallback():
    raw = r"{\rtf1\ansi Hello\par World\tab end}"
    out = extract.strip_rtf_fallback(raw)
    assert "Hello" in out
    assert "World" in out
    assert "\\rtf" not in out
    assert "{" not in out and "}" not in out


# --------------------------------------------------------------------------- #
# _resolve_zip_entry (spine href resolution)
# --------------------------------------------------------------------------- #

def test_resolve_zip_entry_subdir():
    names = {"OEBPS/chapter1.xhtml", "OEBPS/content.opf"}
    assert extract._resolve_zip_entry("chapter1.xhtml", "OEBPS", names) == "OEBPS/chapter1.xhtml"


def test_resolve_zip_entry_anchor_and_encoding():
    names = {"OEBPS/ch 1.xhtml"}
    # fragment stripped + percent-decoded
    assert extract._resolve_zip_entry("ch%201.xhtml#sec2", "OEBPS", names) == "OEBPS/ch 1.xhtml"


def test_resolve_zip_entry_basename_fallback():
    names = {"text/chapter1.xhtml"}
    # href resolves nowhere directly, basename match saves it
    assert extract._resolve_zip_entry("chapter1.xhtml", "OEBPS", names) == "text/chapter1.xhtml"


def test_resolve_zip_entry_miss():
    assert extract._resolve_zip_entry("nope.xhtml", "OEBPS", {"OEBPS/other.xhtml"}) is None


# --------------------------------------------------------------------------- #
# EPUB stdlib extractor — the spine bug end to end
# --------------------------------------------------------------------------- #

def test_extract_with_zipfile_opf_in_subdir(tmp_path):
    epub = tmp_path / "book.epub"
    _write_epub(epub, opf_dir="OEBPS")
    text = extract.extract_with_zipfile(str(epub))
    assert text is not None
    assert "ALPHA_BODY_TEXT" in text
    assert "BETA_BODY_TEXT" in text


def test_count_epub_chapters(tmp_path):
    epub = tmp_path / "book.epub"
    _write_epub(epub)
    assert extract.count_epub_chapters(str(epub)) == 2


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
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    full_text = (workdir / "full_text.txt").read_text(encoding="utf-8")
    assert "ALPHA_BODY_TEXT" in full_text


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
