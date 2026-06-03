"""Optional-dependency discovery, install-mode decision, and the install shell.

The decision (``normalize_install_mode``, ``decide_install``) is pure and fully
unit-tested. The effecting part (``run_install_flow``) is an explicitly
side-effecting shell function — it prompts, warns, and shells out to pip — and is
the only impure surface here, invoked by :mod:`bookextract.cli`.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

#: Importable module name -> pip distribution name.
PYTHON_DEPENDENCIES: Final[dict[str, str]] = {
    "docling": "docling",
    "pypdf": "pypdf",
    "pdfminer": "pdfminer.six",
    "ebooklib": "ebooklib",
    "bs4": "beautifulsoup4",
    "docx": "python-docx",
    "striprtf": "striprtf",
}

_INSTALL_TIMEOUT_SECONDS: Final[int] = 600
_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "y", "yes", "install"})
_FALSY: Final[frozenset[str]] = frozenset({"0", "false", "n", "no", "fallback", "skip"})


class InstallDecision(Enum):
    """What to do about missing optional packages."""

    INSTALL = "install"
    USE_FALLBACK = "fallback"
    ASK_USER = "ask"


@dataclass(frozen=True)
class OfferContext:
    """Runtime facts a :class:`DepOffer` may gate itself on."""

    mode: str
    has_pdftotext: bool


@dataclass(frozen=True)
class DepOffer:
    """A declarative offer to install the packages that improve one feature.

    ``applies`` makes an offer conditional on runtime context (e.g. Docling only
    in technical mode, the pypdf offer only when ``pdftotext`` is absent) so the
    format table stays data-driven instead of a hand-written ``if ext`` ladder.
    """

    feature: str
    module_names: tuple[str, ...]
    fallback: str | None
    applies: Callable[[OfferContext], bool] = field(default=lambda _ctx: True)


def python_module_available(module_name: str) -> bool:
    """Return whether ``module_name`` can be imported, without importing it.

    Args:
        module_name: The importable module name to probe.

    Returns:
        ``True`` if a spec is found, ``False`` otherwise.
    """
    return importlib.util.find_spec(module_name) is not None


def missing_python_packages(module_names: tuple[str, ...]) -> list[str]:
    """Return the pip names of the modules that are not importable.

    Args:
        module_names: Importable module names to probe (keys of
            :data:`PYTHON_DEPENDENCIES`).

    Returns:
        The pip distribution names for those modules that are missing, in input
        order; empty if all are present.
    """
    return [PYTHON_DEPENDENCIES[m] for m in module_names if not python_module_available(m)]


def normalize_install_mode(
    install_missing: str | None = None,
    no_install_missing: bool = False,
) -> str:
    """Resolve install behavior to one of ``'yes' | 'no' | 'ask'``.

    Precedence: ``--no-install-missing`` wins, then ``--install-missing <value>``,
    then the ``BOOK_SKILL_INSTALL_MISSING`` env var, defaulting to ``'ask'``.

    Args:
        install_missing: The ``--install-missing`` value, or ``None`` if the flag
            was absent. Accepts truthy/falsy spellings (``yes``, ``y``, ``no``,
            ``fallback``, …) for backward compatibility.
        no_install_missing: ``True`` when ``--no-install-missing`` was passed.

    Returns:
        The normalized mode: ``'yes'``, ``'no'``, or ``'ask'``.
    """
    mode = os.environ.get("BOOK_SKILL_INSTALL_MISSING", "ask").lower()
    if no_install_missing:
        return "no"
    if install_missing is not None:
        mode = install_missing.lower()
    if mode in _TRUTHY:
        return "yes"
    if mode in _FALSY:
        return "no"
    return "ask"


def decide_install(mode: str, *, is_tty: bool, has_missing: bool) -> InstallDecision:
    """Map ``(mode, tty, has_missing)`` to an install decision. Pure: no I/O.

    Args:
        mode: Normalized install mode (``'yes'``, ``'no'``, or ``'ask'``).
        is_tty: Whether stdin is interactive (only then can we prompt).
        has_missing: Whether any package for the feature is actually missing.

    Returns:
        :attr:`InstallDecision.INSTALL`, :attr:`InstallDecision.ASK_USER`, or
        :attr:`InstallDecision.USE_FALLBACK`.
    """
    if not has_missing:
        return InstallDecision.USE_FALLBACK
    if mode == "yes":
        return InstallDecision.INSTALL
    if mode == "ask" and is_tty:
        return InstallDecision.ASK_USER
    return InstallDecision.USE_FALLBACK


def _warn_if_not_venv() -> None:
    # sys.prefix == sys.base_prefix means we are NOT inside a virtualenv, so pip
    # would mutate the global interpreter — worth a heads-up.
    if sys.prefix == sys.base_prefix:
        print(
            "WARNING: not running inside a virtualenv — packages will install "
            "into the global Python environment. Consider a venv or use "
            "--no-install-missing to rely on fallbacks.",
            file=sys.stderr,
        )


def install_python_packages(packages: list[str]) -> bool:
    """Install packages with pip into the current interpreter.

    Warns when not running inside a virtualenv, since pip would then mutate the
    global environment.

    Args:
        packages: pip distribution names to install.

    Returns:
        ``True`` on success (or nothing to do), ``False`` if pip failed.
    """
    if not packages:
        return True
    print(f"Installing missing Python package(s): {', '.join(packages)}")
    _warn_if_not_venv()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", *packages],
            text=True,
            timeout=_INSTALL_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Package installation failed: {exc}", file=sys.stderr)
        return False
    importlib.invalidate_caches()
    return result.returncode == 0


def _user_accepts_install() -> bool:
    answer = input("Missing package(s) detected. Do you want to install? y=install, n=fallback: ")
    return answer.strip().lower() in {"y", "yes", "install"}


def run_install_flow(offer: DepOffer, install_mode: str) -> None:
    """Announce one dependency offer and honor the install decision.

    Side-effecting (prints, may prompt, may shell out to pip). Callers are
    expected to have already filtered by :attr:`DepOffer.applies`.

    Args:
        offer: The dependency offer to act on.
        install_mode: The yes/no/ask install policy (not the PDF extraction
            mode).
    """
    packages = missing_python_packages(offer.module_names)
    if not packages:
        return

    _announce_offer(offer, packages)
    decision = decide_install(install_mode, is_tty=sys.stdin.isatty(), has_missing=True)
    if decision is InstallDecision.ASK_USER:
        decision = (
            InstallDecision.INSTALL if _user_accepts_install() else InstallDecision.USE_FALLBACK
        )

    if decision is InstallDecision.USE_FALLBACK:
        _announce_fallback(offer)
        return
    _install_and_report(offer, packages)


def _announce_offer(offer: DepOffer, packages: list[str]) -> None:
    message = f"{offer.feature} uses {', '.join(packages)} if installed"
    if offer.fallback:
        message += f", otherwise {offer.fallback}"
    print(message + ".")


def _announce_fallback(offer: DepOffer) -> None:
    if offer.fallback:
        print(f"Using fallback: {offer.fallback}.")
    else:
        print("Installation skipped.")


def _install_and_report(offer: DepOffer, packages: list[str]) -> None:
    if install_python_packages(packages) and not missing_python_packages(offer.module_names):
        print("Package installation complete.")
        return
    print("Package installation incomplete or failed.", file=sys.stderr)
    _announce_fallback(offer)
