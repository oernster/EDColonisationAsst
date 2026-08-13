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
