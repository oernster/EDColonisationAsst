"""Common runtime utilities shared by the packaged EXE and launcher/tray stack.

This module centralises:

- Lightweight debug logging that writes to a plain text log file next to the
  running executable (or current working directory as a fallback).
- Import of the FastAPI application instance used by the in-process uvicorn
  server in frozen mode.
- Import and initialisation of the backend logging configuration.
- Runtime mode detection via [`RuntimeMode`](backend/src/utils/runtime.py:1)
  and [`get_runtime_mode()`](backend/src/utils/runtime.py:1).

It is deliberately free of any Qt or uvicorn dependencies so that it can be
imported early by both [`runtime_entry`](backend/src/runtime_entry.py:1) and
the supporting runtime modules without creating circular imports.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Import FastAPI app and runtime utilities. In normal (package) execution the
# relative imports work (backend.src.runtime.common). In the frozen Nuitka
# onefile build the module is executed as a top-level script so relative
# imports can fail with "attempted relative import with no known parent
# package". We attempt both relative and absolute imports and log any fatal
# failure via _debug_log before re-raising.


def _debug_log(message: str) -> None:
    """Lightweight debug logger for the frozen runtime.

    Writes to EDColonisationAsst-runtime.log next to the EXE so that we can
    see how far startup progresses even if the Qt tray/icon never appears.
    This deliberately does not depend on the backend logging config.
    """
    try:
        try:
            exe_dir = Path(sys.argv[0]).resolve().parent
        except (OSError, TypeError, ValueError):
            # resolve() touching the filesystem (OSError) and an unusable
            # sys.argv[0] (TypeError, ValueError) are the ways this fails.
            # The current directory is a fine second choice for a log file.
            exe_dir = Path.cwd()

        log_path = exe_dir / "EDColonisationAsst-runtime.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:  # noqa: BLE001, S110
        # Deliberately broad, the broadest in the file on purpose. This
        # is the logger the frozen runtime uses to explain its own startup
        # failures, so it runs before anything else is known to work and it
        # must never be the thing that breaks. An unwritable install
        # directory raises OSError; everything else is unknowable here.
        pass


try:
    try:
        from ..main import app as fastapi_app  # type: ignore[import-not-found]
        from ..utils.logger import get_logger, setup_logging
        from ..utils.runtime import RuntimeMode, get_runtime_mode, is_flatpak
    except ImportError:
        # The relative form fails only when this module is executed as a
        # top-level script, which the frozen Nuitka onefile build does. That
        # is an ImportError; anything else raised while importing the app is
        # a real failure and belongs to the outer handler below.
        from backend.src.main import app as fastapi_app  # type: ignore[import-error]
        from backend.src.utils.logger import (  # type: ignore[import-error]
            get_logger,
            setup_logging,
        )
        from backend.src.utils.runtime import (  # type: ignore[import-error]
            RuntimeMode,
            get_runtime_mode,
            is_flatpak,
        )
except Exception as exc:  # pragma: no cover
    _debug_log(
        f"[runtime.common] FATAL importing FastAPI app or runtime utilities: {exc!r}"
    )
    # Re-raise so Nuitka/console still see the failure; we at least have
    # EDColonisationAsst-runtime.log with the cause.
    raise

# Initialise logging once at import time so that all runtime modules share the
# same configuration and logger hierarchy.
setup_logging()
logger = get_logger(__name__)

# This module is the runtime stack's single import surface: app_runtime,
# runtime_entry, tray_components and splash all reach these names through
# here rather than through backend.src.main and backend.src.utils.runtime
# directly, which is what keeps the dual relative/absolute import dance in
# one place for the frozen build.
#
# __all__ is what says so. Without it these read as unused imports and an
# unattended `ruff check --fix` deletes them, which is not hypothetical: it
# happened: it broke the runtime with "cannot import name RuntimeMode".
__all__ = [
    "RuntimeMode",
    "_debug_log",
    "fastapi_app",
    "get_logger",
    "get_runtime_mode",
    "is_flatpak",
    "logger",
    "setup_logging",
]
