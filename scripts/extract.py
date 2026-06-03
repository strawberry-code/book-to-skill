#!/usr/bin/env python3
"""Entrypoint for book-to-skill text extraction.

Thin shell: makes the sibling ``bookextract`` package importable when this file
is run directly (``python3 scripts/extract.py``), then delegates to the package
CLI. All logic lives in ``bookextract`` next to this file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bookextract.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
