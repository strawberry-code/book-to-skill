# Release checklist

`book-to-skill` follows [Semantic Versioning](https://semver.org/). The generator version is
the **single source of truth** in `scripts/bookextract/__init__.py` (`__version__`); the
packaging version (`pyproject.toml`) and Docker/CI read from it, and every generated skill
records the version that built it in `.book-to-skill.json`.

## Cutting a release

1. **Land all changes** on `master` (or via PR) and confirm the working tree is clean.
2. **Bump the version** in `scripts/bookextract/__init__.py`. `hatch`/`uv` pick it up
   automatically — do not duplicate the number in `pyproject.toml`.
3. **Update [`CHANGELOG.md`](CHANGELOG.md)**: move the `[Unreleased]` entries under a new
   `## [X.Y.Z] — YYYY-MM-DD` heading, keeping the migration-class tags. Add a fresh empty
   `[Unreleased]`.
4. **Run the quality gate green** (see README → Development):
   ```bash
   uv sync --extra dev --extra pdf
   uv run pytest -q
   uv run ruff check scripts/ tests/
   uv run mypy
   # informational (known debt — see CHANGELOG / issues):
   uv run lizard scripts/bookextract -T nloc=25 -C 8 -a 4 --warnings_only
   uv run xenon --max-absolute B --max-average A scripts/bookextract
   ```
5. **Build the artifacts** and sanity-check the wheel contains `bookextract/`:
   ```bash
   uv build
   ```
6. **Update [`ROADMAP.md`](ROADMAP.md)** — move shipped items into the released version.
7. **Tag and push**:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin master --tags
   ```
8. **Create the GitHub release** from the tag, pasting the changelog section. Only then add a
   "latest release" badge to the README (none exists until the first tag).
9. **Docs** — Read the Docs builds from `master` on push (`.readthedocs.yaml`,
   `fail_on_warning: true`); confirm the build is green.

## Notes

- The `/book-to-skill` slash command and `python3 scripts/extract.py` path must keep working
  after any packaging change — they are the primary interfaces.
- `mypy` is pinned to `1.19.x` in the `dev` extra; the gate is green only with an extractor
  present (`--extra pdf` is enough). See CHANGELOG → Unreleased for the rationale.
