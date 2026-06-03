"""Sphinx configuration for the book-to-skill documentation.

The ``bookextract`` package is not pip-installed; it lives under ``scripts/`` and
is run as a file. We add that directory to ``sys.path`` so autodoc can import the
modules directly. Optional extractor libraries (docling, ebooklib, …) are imported
lazily inside functions, so importing the package for autodoc never requires them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

# -- Project information ----------------------------------------------------- #
project = "book-to-skill"
author = "book-to-skill contributors"
release = "0.1.0"

# -- General configuration --------------------------------------------------- #
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- autodoc / napoleon ------------------------------------------------------ #
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
    "private-members": True,  # the package's _helpers carry real design intent
    "member-order": "bysource",
}
autodoc_typehints = "description"  # render type hints in the body, not the signature
autodoc_typehints_description_target = "documented"
always_document_param_types = True

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_private_with_doc = True
napoleon_use_rtype = True
napoleon_use_param = True

intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# -- HTML output ------------------------------------------------------------- #
html_theme = "sphinx_rtd_theme"
html_title = "book-to-skill"
