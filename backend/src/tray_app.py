"""Tray controller entrypoint for Elite: Dangerous Colonisation Assistant.

This module is now a thin entrypoint that focuses on:

- Enforcing single-instance behaviour using
  [`ApplicationInstanceLock`](backend/src/runtime/app_singleton.py:27),
  shared with the GUI launcher and packaged runtime.
- Creating the top-level Qt application.
- Instantiating the tray controller defined in
  [`runtime.tray_components`](backend/src/runtime/tray_components.py:1).

The heavy-weight tray logic (process spawning, logging, Exit handling) lives
in the runtime submodule to keep this entrypoint small and focused.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

# Single-instance lock shared with the launcher and packaged runtime.
# Use a defensive import so this module works both as part of the
# backend.src package and when executed directly.
try:
    from .runtime.app_singleton import (  # type: ignore[import-not-found]
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.app_singleton import (  # type: ignore[import-error]
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )

# Import the tray controller implementation from the runtime package.
try:
    from .runtime.tray_components import (
        TrayController,  # type: ignore[import-not-found]
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.tray_components import (
        TrayController,  # type: ignore[import-error]
    )


def main() -> int:
    """Entry point for the tray controller.

    The dedicated launcher window already provides visible feedback during
    startup, so we intentionally avoid showing any additional splash screen
    here to prevent brief, obsolete flashes while the backend initialises.

    This entrypoint also participates in the single-instance guarantee shared
    with the GUI launcher and the packaged runtime. If another instance is
    already running for this user, we avoid starting a second tray and simply
    exit; the existing tray continues managing the backend and frontend.
    """
    try:
        lock = ApplicationInstanceLock()
        if not lock.acquire():
            # Another tray/backend pair is already running. We deliberately do
            # not attempt to start a second instance; just exit quietly.
            return 0
    except ApplicationInstanceLockError:
        # If the lock cannot be created (for example due to a permissions
        # issue on the lock directory), continue without enforcing
        # single-instance semantics rather than blocking startup entirely.
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = TrayController(app)
    # Keep a strong reference so it is not garbage-collected.
    app._controller = controller  # type: ignore[attr-defined]

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
