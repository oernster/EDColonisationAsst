"""
Core runtime orchestration for the packaged and development runtimes.

This module contains the bulk of the logic that was previously embedded in
[`runtime_entry`](backend/src/runtime_entry.py:1):

- [`RuntimeApplication`] coordinates DEV vs FROZEN behaviour, which is all
  that is defined here.
- [`BackendServerController`](backend/src/runtime/backend_server.py:1) starts
  the FastAPI backend, in-process in frozen mode.
- [`TrayUIController`](backend/src/runtime/tray_ui.py:1) owns the Qt system
  tray UI for the frozen runtime.

The two controllers moved out to modules of their own once this file passed
the 400-line cap; they are re-exported here so that this module stays the
runtime stack's public surface, which is what `runtime_entry` and the tests
import from. `__all__` is what says so: without it they read as unused
imports and an unattended `ruff check --fix` deletes them.

Keeping the orchestration here allows runtime_entry.py to remain a thin
entrypoint focused on single-instance enforcement and crash logging.
"""

from __future__ import annotations

import webbrowser

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .common import RuntimeMode, _debug_log, logger
from .environment import RuntimeEnvironment

# Canonical application version, resolved from the top-level VERSION file.
try:
    from .. import __version__  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src import __version__  # type: ignore[import-error]

# The two controllers this module orchestrates, re-exported through __all__.
try:
    from .backend_server import (  # type: ignore[import-not-found]
        BackendServerController,
    )
    from .tray_ui import TrayUIController  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.backend_server import (  # type: ignore[import-error]
        BackendServerController,
    )
    from backend.src.runtime.tray_ui import (  # type: ignore[import-error]
        TrayUIController,
    )

# Shared Help menu icon, used for the startup splash.
try:
    from .help_menu import resolve_about_icon  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        resolve_about_icon,
    )

# Startup splash and non-blocking readiness monitor for the frozen runtime.
try:
    from .splash import (  # type: ignore[import-not-found]
        SPLASH_FAILURE_CLOSE_DELAY_MS,
        STATUS_TIMED_OUT,
        StartupMonitor,
        StartupSplashWindow,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.splash import (  # type: ignore[import-error]
        SPLASH_FAILURE_CLOSE_DELAY_MS,
        STATUS_TIMED_OUT,
        StartupMonitor,
        StartupSplashWindow,
    )

_APPLICATION_NAME = "Elite: Dangerous Colonisation Assistant"


class RuntimeApplication:
    """
    Top-level application orchestrator.

    - In DEV mode:
      Delegates to the existing launcher window and venv-based startup so
      that developers continue to use the same tooling as before.

    - In FROZEN mode:
      Starts the backend in-process and presents a tray icon that can open
      the web UI and exit the application.
    """

    def __init__(self, open_browser: bool = True) -> None:
        self._env = RuntimeEnvironment.detect()
        self._backend = BackendServerController(self._env)
        self._open_browser = open_browser
        # Strong references to Qt-side startup helpers created in
        # _run_frozen(); kept on self so they outlive the local scope.
        self._monitor: StartupMonitor | None = None
        self._splash: StartupSplashWindow | None = None
        _debug_log(
            "[RuntimeApplication] detected environment: "
            f"mode={self._env.mode}, project_root={self._env.project_root}",
        )

    def run(self) -> int:
        if self._env.mode is RuntimeMode.DEV:
            logger.info("RuntimeApplication starting in DEV mode.")
            _debug_log("[RuntimeApplication] run() entering DEV mode")
            return self._run_dev()

        logger.info("RuntimeApplication starting in FROZEN mode.")
        _debug_log("[RuntimeApplication] run() entering FROZEN mode")
        return self._run_frozen()

    # -------------------- DEV mode -------------------------------------------

    def _run_dev(self) -> int:
        """
        Development mode behaviour.

        This reuses the existing launcher window (`backend/src/launcher.py`)
        exactly as before, so that developer workflows are unchanged.
        """
        from PySide6.QtCore import QTimer  # imported lazily for speed

        from .launcher import Launcher, QtLaunchWindow

        app = QApplication([])
        window = QtLaunchWindow(self._env.project_root)
        window.show()

        launcher = Launcher(self._env.project_root, window)

        def _start() -> None:
            launcher.run()

        QTimer.singleShot(0, _start)
        return app.exec()

    # -------------------- FROZEN mode ----------------------------------------

    def _run_frozen(self) -> int:
        """
        Frozen (packaged EXE) behaviour.

        - Shows a startup splash immediately (unless started with
          --no-browser for silent background/login starts).
        - Starts the backend in-process and shows the tray icon straight
          away so Exit is always available.
        - Polls readiness (health + /app) on a Qt timer without blocking
          the UI thread, reporting progress on the splash.
        - Opens the browser only once both endpoints actually respond, so
          the user never lands on an empty page.
        """
        _debug_log("[RuntimeApplication] _run_frozen() starting")
        app = self._build_application()

        # Show the splash before any heavier startup work so the user gets
        # immediate feedback. Background starts (--no-browser) stay silent.
        splash = self._show_splash_if_wanted(app)

        # Start backend in-process.
        _debug_log("[RuntimeApplication] starting in-process backend")
        self._backend.start()

        # Create and show tray UI immediately; Exit must not wait for
        # readiness.
        tray = TrayUIController(app, self._env, self._backend)
        tray.show()
        _debug_log("[RuntimeApplication] TrayUIController created and shown")

        monitor = self._build_startup_monitor(splash)
        monitor.start()
        # Keep strong references so Qt-side objects are not garbage-collected.
        self._monitor = monitor
        self._splash = splash

        result = app.exec()
        _debug_log(
            f"[RuntimeApplication] Qt event loop exited with code {result}",
        )
        return result

    def _build_application(self) -> QApplication:
        """Create the QApplication and give it the packaged EXE's identity."""
        app = QApplication([])
        app.setApplicationName(_APPLICATION_NAME)
        app.setQuitOnLastWindowClosed(False)

        # Ensure the runtime EXE has the correct icon in the Windows taskbar.
        # In frozen mode this process is the Nuitka-built EDColonisationAsst.exe,
        # not python.exe, so Qt will use this icon for the taskbar button.
        icon_path = self._env.icon_path
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
        return app

    def _show_splash_if_wanted(self, app: QApplication) -> StartupSplashWindow | None:
        """Show the startup splash, unless this is a silent background start."""
        if not self._open_browser:
            return None

        splash = StartupSplashWindow(
            version=__version__,
            icon_path=resolve_about_icon(self._env.project_root) or self._env.icon_path,
        )
        splash.show()
        app.processEvents()
        _debug_log("[RuntimeApplication] startup splash shown")
        return splash

    def _build_startup_monitor(
        self,
        splash: StartupSplashWindow | None,
    ) -> StartupMonitor:
        """Wire the readiness monitor to the splash and the browser launch."""

        def _set_status(message: str) -> None:
            if splash is not None:
                splash.set_status(message)

        def _on_ready() -> None:
            _debug_log("[RuntimeApplication] backend/frontend reported ready")
            if self._open_browser:
                webbrowser.open(self._env.frontend_url)
                _debug_log(
                    "[RuntimeApplication] Opening web UI at "
                    f"{self._env.frontend_url}",
                )
            else:
                _debug_log(
                    "[RuntimeApplication] open_browser disabled; "
                    "not launching web UI automatically",
                )
            if splash is not None:
                splash.close()

        def _on_timeout() -> None:
            _debug_log("[RuntimeApplication] readiness monitoring timed out")
            _set_status(STATUS_TIMED_OUT)
            if splash is not None:
                QTimer.singleShot(SPLASH_FAILURE_CLOSE_DELAY_MS, splash.close)

        def _on_failure(reason: str) -> None:
            # The backend has already failed, so there is nothing left to wait
            # for: show the cause rather than a generic "taking longer than
            # expected" the user cannot act on.
            _debug_log(f"[RuntimeApplication] backend startup failed: {reason}")
            _set_status(reason)
            if splash is not None:
                QTimer.singleShot(SPLASH_FAILURE_CLOSE_DELAY_MS, splash.close)

        def _on_startup_report(report: object) -> None:
            # Whatever the backend is doing beats the generic "starting the
            # local backend", because it is the part that actually takes time
            # and the only part that can explain itself.
            if splash is None:
                return
            message = getattr(report, "message", None)
            if message:
                splash.set_status(message)
            splash.set_progress(getattr(report, "percent", None))
            splash.set_detail(getattr(report, "explanation", None))

        return StartupMonitor(
            probe=self._backend.probe_ready,
            on_status=_set_status,
            on_ready=_on_ready,
            on_timeout=_on_timeout,
            failure_reason=self._backend.startup_failure,
            on_failure=_on_failure,
            startup_report=self._backend.latest_startup,
            on_startup_report=_on_startup_report,
        )


__all__ = ["BackendServerController", "RuntimeApplication", "TrayUIController"]
