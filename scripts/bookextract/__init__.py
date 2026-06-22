"""book-to-skill text-extraction package.

Imported by the sibling ``scripts/extract.py`` entrypoint (which puts this
directory on ``sys.path`` when run as a file). This module is intentionally
empty: no side effects, no environment reads, no optional third-party imports —
so that importing the package never fails and never does work.

``__version__`` is the single source of truth for the generator version. It is
stamped into each extraction's ``metadata.json`` (``generator_version``) and from
there into a generated skill's ``.book-to-skill.json`` manifest, which the
upgrade flow reads to decide what is stale.
"""

from __future__ import annotations

from typing import Final

__version__: Final[str] = "1.2.0"
