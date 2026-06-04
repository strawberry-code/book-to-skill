"""Optional CLI progress display, backed by ``rich``.

A shell-side concern: extractors stay display-agnostic and merely call a
:data:`~bookextract.types.PageReporter`. This module turns that callback into a
spinner + bar when a TTY is present and ``rich`` is installed, and into a silent
no-op otherwise (non-interactive runs, ``--debug``, or ``rich`` missing) so it
never pollutes machine-read output.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import TYPE_CHECKING

from bookextract.types import PageReporter

if TYPE_CHECKING:
    from rich.progress import ProgressColumn


def _noop(_advance: int = 1) -> None:
    """A reporter that discards progress updates."""


@contextlib.contextmanager
def page_progress(
    total: int | None,
    description: str,
    *,
    enabled: bool,
) -> Iterator[PageReporter]:
    """Yield a :data:`~bookextract.types.PageReporter` driving a live display.

    Args:
        total: Expected number of pages, or ``None`` for an indeterminate
            spinner (used when the backend can't report per-page progress).
        description: Label shown next to the spinner/bar.
        enabled: When ``False`` (or ``rich`` is unavailable) a no-op reporter is
            yielded and nothing is rendered.

    Yields:
        A callable that advances the display by N pages.
    """
    if not enabled:
        yield _noop
        return
    try:
        from rich.progress import Progress
    except ImportError:
        yield _noop
        return

    with Progress(*_columns(total), transient=True) as progress:
        task = progress.add_task(description, total=total)

        def advance(pages: int = 1) -> None:
            progress.advance(task, pages)

        yield advance
        if total:
            progress.update(task, completed=total)


def _columns(total: int | None) -> list[ProgressColumn]:
    """Build the rich columns: spinner + label, a bar when ``total`` is known."""
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    label = TextColumn("[progress.description]{task.description}")
    columns: list[ProgressColumn] = [SpinnerColumn(), label]
    if total:
        columns += [BarColumn(), MofNCompleteColumn(), TextColumn("pages")]
    columns.append(TimeElapsedColumn())
    return columns
