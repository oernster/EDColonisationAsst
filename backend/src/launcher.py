#!/usr/bin/env python3
"""
GUI launcher for Elite: Dangerous Colonisation Assistant.

This module now acts primarily as a thin entrypoint and façade over the
launcher components defined in
[`runtime.launcher_components`](backend/src/runtime/launcher_components.py:1).

Responsibilities:

- Enforce single-instance behaviour using
  [`ApplicationInstanceLock`](backend/src/runtime/app_singleton.py:1)
  shared with the packaged runtime and tray controller.
- Detect the project root based on this file's location.
- Initialise the Qt application, window icon and top-level
  [`QtLaunchWindow`](backend/src/runtime/launcher_view.py:70).
- Delegate all detailed initialisation logic to
  [`Launcher`](backend/src/runtime/launcher_components.py:68).

The Qt view lives in `runtime.launcher_view` and the orchestration in
`runtime.launcher_components`, which re-exports the view so this entrypoint
still reaches the whole stack through one import.
"""

from __future__ import annotations

from pathlib import Path
import sys
import webbrowser

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

# Single-instance lock shared with the packaged runtime. We mirror the
# defensive import strategy used in runtime_entry so this module works
# both as part of the backend.src package and when executed directly.
try:
    from .runtime.app_singleton import (
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )
except ImportError:
    # The relative form fails only when this module is executed directly
    # rather than imported as part of the package, which makes it a plain
    # ImportError (ModuleNotFoundError included). Anything else raised while
    # importing app_singleton is a genuine defect and should surface.
    from backend.src.runtime.app_singleton import (  # type: ignore[import-error]
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )

# Import launcher components (UI and orchestration) from the runtime package.
try:
    from .runtime.launcher_components import (  # type: ignore[import-not-found]
        APP_NAME,
        BACKEND_PORT,
        FRONTEND_PORT,
        PROGRESS_MAX,
        InitStep,
        Launcher,
        LaunchView,
        QtLaunchWindow,
    )
except ImportError:
    # Same direct-execution fallback as the import above.
    from backend.src.runtime.launcher_components import (  # type: ignore[import-error]
        BACKEND_PORT,
        Launcher,
        QtLaunchWindow,
    )


# These names are imported for re-export: launcher.py is the module the
# packaged runtime and the tests reach the launcher stack through; the
# dual relative/absolute import above is what makes that work in both the
# source tree and the frozen build. __all__ is what marks them intentional;
# without it they read as unused imports and `ruff check --fix` deletes
# them, which is not hypothetical (it broke runtime/common.py exactly that
# way during this sweep).
__all__ = [
    "APP_NAME",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "PROGRESS_MAX",
    "InitStep",
    "LaunchView",
    "Launcher",
    "QtLaunchWindow",
    "main",
]


def _detect_project_root() -> Path:
    """Detect project root from this file location."""
    return Path(__file__).resolve().parents[2]


def main() -> int:
    project_root = _detect_project_root()

    # Enforce single-instance behaviour shared with the packaged runtime.
    # If another instance is already running for this user, we avoid
    # starting a second launcher and instead best-effort open the
    # existing web UI.
    try:
        lock = ApplicationInstanceLock()
        if not lock.acquire():
            frontend_url = f"http://127.0.0.1:{BACKEND_PORT}/app/"
            try:
                webbrowser.open(frontend_url)
            except (webbrowser.Error, OSError):
                # No usable browser (webbrowser.Error) or the spawn itself
                # failing (OSError). We are already exiting because another
                # instance holds the lock, so a browser that will not open
                # must not turn a clean exit into a crash.
                pass
            return 0
    except ApplicationInstanceLockError:
        # If the lock cannot be created (e.g. permissions issue), continue
        # without single-instance enforcement rather than blocking startup.
        pass

    app = QApplication(sys.argv)

    # Ensure the taskbar / application icon is set for the launcher process.
    # Prefer the PNG (wrapped in a QIcon) for a crisp icon; fall back to the ICO.
    png_path = project_root / "EDColonisationAsst.png"
    ico_path = project_root / "EDColonisationAsst.ico"
    if png_path.exists():
        app.setWindowIcon(QIcon(str(png_path)))
    elif ico_path.exists():
        app.setWindowIcon(QIcon(str(ico_path)))

    window = QtLaunchWindow(project_root)
    window.show()

    # Kick off initialization after the event loop has had a chance to show the window.
    launcher = Launcher(project_root, window)

    def _start() -> None:
        launcher.run()

    QTimer.singleShot(0, _start)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
