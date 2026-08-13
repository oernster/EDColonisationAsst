"""
Runtime mode detection utilities.

This module centralises the logic for determining whether the application
is running in a regular development environment (Python interpreter +
virtual environment) or as a frozen executable produced by Nuitka.

It is intentionally minimal and side‑effect free so that it can be safely
imported from anywhere in the backend.
"""

from __future__ import annotations

from enum import Enum, auto
import os
from pathlib import Path
import sys

# Set by flatpak inside the sandbox, naming the running application. This is the
# one place the sandbox is detected; the runtime stack reaches it through
# runtime.common.
_ENV_FLATPAK_ID = "FLATPAK_ID"

# The application's reverse-DNS identity. It is the flatpak app id, the basename
# of the installed desktop entry and the name of the installed icons, because a
# desktop matches a running window to its launcher by that one string. The
# packaging script declares the same value; the test in test_desktop_identity.py
# fails if the two ever drift.
APPLICATION_ID = "uk.co.oernster.EDColonisationAsst"


def desktop_file_name() -> str:
    """Return the desktop entry this process should claim as its identity.

    Wayland does not use WM_CLASS: a compositor ties a window to its launcher
    by the desktop entry the application names, which is what
    ``QGuiApplication.setDesktopFileName`` announces. Without it a window opens
    as a second, generic entry beside the launcher it was started from.

    Inside a flatpak the answer is stated by the sandbox itself. That is not a
    convenience: it is the same string flatpak uses to install the desktop
    entry, so reading it back cannot disagree with the file on disk the way a
    second copy of the constant could.
    """
    return os.environ.get(_ENV_FLATPAK_ID) or APPLICATION_ID


class RuntimeMode(Enum):
    """Enumerates the supported runtime modes for the application."""

    DEV = auto()
    FROZEN = auto()


def is_frozen() -> bool:
    """
    Return True if the current process is a frozen executable.

    Nuitka (and other freezer tools) set ``sys.frozen`` on the embedded
    Python interpreter. We use that to distinguish between a packaged
    runtime EXE and a regular Python interpreter invocation.

    In some environments the ``sys.frozen`` attribute may not be present
    or may not behave as expected. As a pragmatic fallback we also treat
    any process whose argv[0] is a non-Python ``.exe`` as frozen. This
    covers the typical case where the runtime is launched via the
    Nuitka-built EDColonisationAsst.exe rather than ``python.exe``.
    """
    # Primary detection: explicit flag set by freezer.
    if bool(getattr(sys, "frozen", False)):
        return True

    # Fallback: argv[0] points at a non-Python .exe
    try:
        exe_path = Path(sys.argv[0])
        if exe_path.suffix.lower() == ".exe" and not exe_path.stem.lower().startswith(
            "python"
        ):
            return True
    except (TypeError, ValueError):
        # sys.argv[0] is not guaranteed to be a usable path string: an
        # embedded host can leave it non-string (TypeError) and a null byte
        # in it raises ValueError. Falling back to non-frozen is the safe
        # answer because it keeps the source layout.
        return False

    return False


def is_flatpak() -> bool:
    """
    Return True if the current process is running inside a flatpak sandbox.

    Flatpak sets ``FLATPAK_ID`` in the sandbox, naming the application being
    run. Nothing else sets it, so its presence is a reliable answer.
    """
    return bool(os.environ.get(_ENV_FLATPAK_ID))


def get_runtime_mode() -> RuntimeMode:
    """
    Determine the current runtime mode.

    A flatpak reports the packaged mode despite not being frozen, because the
    distinction the modes actually draw is not "compiled by Nuitka" but
    "dependencies already installed and the layout already fixed". Both hold
    inside the sandbox: it ships its own Python and every requirement; ``/app``
    is read-only. Development mode would be actively wrong there, since it
    builds a virtual environment and starts the backend and the front end as
    separate processes, none of which a sandbox can or should do.

    Returns
    -------
    RuntimeMode
        ``RuntimeMode.FROZEN`` when running inside a frozen executable or a
        flatpak, otherwise ``RuntimeMode.DEV``.
    """
    return RuntimeMode.FROZEN if is_frozen() or is_flatpak() else RuntimeMode.DEV


def is_packaged() -> bool:
    """
    Return True when the application runs from a packaged layout.

    This is the question every module asks before deciding where to keep a file
    it writes. A packaged layout ships its own dependencies at a fixed location
    that the application must not write into, so its data belongs in the
    per-user directory :func:`utils.user_data.user_data_dir` reports. A source
    checkout is the opposite case: the tree is the developer's own and keeping
    derived files beside the packages that use them is what makes a checkout
    self-contained.

    It is the runtime mode asked as a yes or no question rather than a second
    detection, so a runtime that counts as packaged counts as packaged
    everywhere at once.
    """
    return get_runtime_mode() is RuntimeMode.FROZEN
