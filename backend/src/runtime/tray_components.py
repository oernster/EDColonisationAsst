"""Tray controller components for the EDCA runtime stack.

This module contains the core tray logic that was previously defined in
[`tray_app.py`](backend/src/tray_app.py:1):

- [`ProcessGroup`](backend/src/runtime/tray_components.py:29): thin wrapper
  around a child `subprocess.Popen` with graceful termination semantics.
- [`TrayController`](backend/src/runtime/tray_components.py:62): the Qt
  system tray controller responsible for starting and stopping the backend
  and frontend processes and wiring up the tray icon and Exit action.

By moving these classes into `runtime.tray_components`, the
[`tray_app`](backend/src/tray_app.py:1) module can be slimmed down to a small
entrypoint that focuses on:

- Single-instance enforcement via `ApplicationInstanceLock`.
- Creating the `QApplication` and instantiating `TrayController`.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# Shared Help menu (About + Check for Updates). Defensive import so this
# module works both as part of the backend.src package and when executed
# with backend/ on sys.path.
try:
    from .help_menu import (  # type: ignore[import-not-found]
        add_help_menu,
        resolve_about_icon,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        add_help_menu,
        resolve_about_icon,
    )

try:
    from ..constants import DEFAULT_BACKEND_PORT  # type: ignore[import-not-found]
except ImportError:
    # As above.
    from backend.src.constants import (  # type: ignore[import-error]
        DEFAULT_BACKEND_PORT,
    )

try:
    from .update_check import default_update_check  # type: ignore[import-not-found]
except ImportError:
    # As above.
    from backend.src.runtime.update_check import (  # type: ignore[import-error]
        default_update_check,
    )

try:
    from ..utils.user_data import user_data_dir  # type: ignore[import-not-found]
except ImportError:
    # As above.
    from backend.src.utils.user_data import (  # type: ignore[import-error]
        user_data_dir,
    )


APP_NAME = "Elite: Dangerous Colonisation Assistant"


class ProcessGroup:
    """Simple wrapper to manage a child process."""

    def __init__(self, popen: subprocess.Popen) -> None:
        self._popen = popen

    @property
    def alive(self) -> bool:
        return self._popen.poll() is None

    def terminate(self, graceful_timeout: float = 5.0) -> None:
        """Attempt graceful termination, then kill if still running."""
        if not self.alive:
            return
        try:
            # Prefer terminate() first.
            self._popen.terminate()
        except Exception:  # noqa: BLE001
            # Fallback to kill if terminate is not supported on this platform.
            try:
                self._popen.kill()
            except Exception:  # noqa: BLE001
                # Deliberately broad. Reaching here means the process could not be
                # killed after it could not be terminated: it has already gone,
                # cannot be reached. Either way there is nothing further to try.
                return

        try:
            self._popen.wait(timeout=graceful_timeout)
        except Exception:  # noqa: BLE001
            # Deliberately broad. TimeoutExpired is the expected case; a process
            # that exits between terminate() and wait() raises OSError on some
            # platforms. Both mean escalate to kill below.
            try:
                self._popen.kill()
            except Exception:  # noqa: BLE001, S110
                # Deliberately broad, as above. This is the second kill attempt; failing
                # it leaves the process to the OS, which is the only remaining option.
                pass


class TrayController:
    """
    System tray controller that manages the EDCA backend and frontend.

    - Starts the FastAPI backend via uvicorn.
    - Starts the frontend via `npm run dev`.
    - Exposes a tray icon with a context menu containing an Exit action.
    - On Exit, gracefully terminates both child processes.
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._tray = QSystemTrayIcon()
        self._backend: ProcessGroup | None = None
        self._frontend: ProcessGroup | None = None

        # Resolve install / project root based on this file location.
        # Expected layout (both dev and installed):
        #   <root>/
        #       backend/
        #           src/
        #               tray_app.py
        #               runtime/tray_components.py  <-- this file
        #           venv/
        #       frontend/
        self._root = Path(__file__).resolve().parents[2]

        # Record our PID so the installer can stop the tray cleanly during
        # uninstall, avoiding "files in use" errors on Windows.
        self._pid_file = self._root / "tray.pid"
        try:
            self._pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except Exception:  # noqa: BLE001
            # Never let logging/housekeeping break tray startup.
            self._pid_file = self._root / "tray.pid"

        self._configure_tray_icon()
        self._start_services()

    def _configure_tray_icon(self) -> None:
        icon_path = self._root / "EDColonisationAsst.ico"
        if icon_path.exists():
            self._tray.setIcon(QIcon(str(icon_path)))
        self._tray.setToolTip(APP_NAME)

        menu = QMenu()
        # Held on the controller: it is a QObject with no parent, so dropping
        # the reference would collect it and take the manual check with it.
        self._updates = default_update_check(icon_path=icon_path)
        add_help_menu(
            menu,
            icon_path=resolve_about_icon(self._root),
            on_check_updates=self._updates.check_manually,
        )
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._on_exit_triggered)

        self._tray.setContextMenu(menu)
        self._tray.setVisible(True)

    # --------------------------------------------------------------------- logging

    def _log_message(self, message: str) -> None:
        """
        Append a simple message to log files for debugging.

        Primary target:
        - The same run-edca.log used by run-edca.bat in the install root.

        Secondary target (best-effort):
        - A user-local log under the per-user data directory, to avoid any
          filesystem virtualisation or permission issues writing directly into
          Program Files. Inside a flatpak this is the only one of the two that
          can be written at all, since the primary target sits under a read-only
          /app, so it is what explains a sandbox that fails to start.
        """
        # Primary: install root next to run-edca.bat
        try:
            root_log = self._root / "run-edca.log"
            with root_log.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:  # noqa: BLE001, S110
            # Logging failures must never crash the tray.
            pass

        # Secondary: user-local log that should always be writable.
        try:
            user_log_dir = user_data_dir()
            user_log_dir.mkdir(parents=True, exist_ok=True)
            user_log = user_log_dir / "run-edca.log"
            with user_log.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:  # noqa: BLE001, S110
            # Ignore all errors here as well.
            pass

    # --------------------------------------------------------------------- start

    def _start_services(self) -> None:
        """Start backend and frontend as background processes."""
        self._backend = self._start_backend()
        self._frontend = self._start_frontend()

    def _start_backend(self) -> ProcessGroup | None:
        """Start the FastAPI backend (uvicorn) in the background."""
        backend_dir = self._root / "backend"
        venv_python = backend_dir / "venv" / "Scripts" / "python.exe"

        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            # Fallback to system Python if the venv is missing.
            python_exe = "python"

        cmd = [
            python_exe,
            "-m",
            "uvicorn",
            "backend.src.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(DEFAULT_BACKEND_PORT),
        ]

        # Log what we're about to start to help diagnose issues in production.
        self._log_message(
            f"Starting backend process: {' '.join(cmd)} (cwd={self._root})",
        )
        return self._spawn_process(cmd, cwd=self._root, name="backend")

    def _start_frontend(self) -> ProcessGroup | None:
        """Start the frontend (Vite dev server) in the background."""
        frontend_dir = self._root / "frontend"

        # Use npm via cmd.exe so that Windows can resolve store/alias shims
        # (e.g. when npm is installed via Windows Apps rather than a plain
        # npm.cmd on PATH). We still run inside the frontend directory and
        # force host/port so users know to browse to http://localhost:5173/.
        cmd = [
            "cmd.exe",
            "/c",
            "npm",
            "run",
            "dev",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            "5173",
        ]

        self._log_message(
            f"Starting frontend process: {' '.join(cmd)} (cwd={frontend_dir})",
        )
        return self._spawn_process(cmd, cwd=frontend_dir, name="frontend")

    def _spawn_process(
        self,
        cmd: list[str],
        cwd: Path,
        name: str,
    ) -> ProcessGroup | None:
        """
        Spawn a child process with no visible console window on Windows.

        Any failure to create the process is logged so that issues such as a
        missing `npm` binary or Python interpreter can be diagnosed from an
        installed environment.

        For the frontend specifically, stdout/stderr are captured into a
        dedicated frontend-dev.log file so that Vite/npm errors are visible.
        """
        try:
            kwargs: dict = {
                "cwd": str(cwd),
            }

            if name == "frontend":
                # Capture Vite/npm output into a log for easier debugging.
                log_path = self._root / "frontend-dev.log"
                try:
                    log_file = log_path.open("ab")
                except Exception:  # noqa: BLE001
                    # If we cannot open the log file, fall back to discarding output.
                    kwargs["stdout"] = subprocess.DEVNULL
                    kwargs["stderr"] = subprocess.DEVNULL
                else:
                    kwargs["stdout"] = log_file
                    kwargs["stderr"] = subprocess.STDOUT
            else:
                # Backend or other processes: keep output hidden.
                kwargs["stdout"] = subprocess.DEVNULL
                kwargs["stderr"] = subprocess.DEVNULL

            if sys.platform.startswith("win"):
                # Ensure no console window pops up, even when launching via cmd.exe.
                CREATE_NO_WINDOW = 0x08000000
                kwargs["creationflags"] = CREATE_NO_WINDOW

                # Also request that the subprocess window not be shown.
                startup_info = subprocess.STARTUPINFO()
                startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startup_info

            popen = subprocess.Popen(cmd, **kwargs)  # type: ignore[arg-type]
            return ProcessGroup(popen)
        except Exception as exc:  # noqa: BLE001
            # We don't want frontend/backend startup failures to be completely
            # silent from an installed build. Log the failure and continue so
            # the tray icon can still be shown.
            self._log_message(
                f"Failed to start {name} process: {' '.join(cmd)} (cwd={cwd}): {exc}",
            )
            return None

    # --------------------------------------------------------------------- exit

    def _on_exit_triggered(self) -> None:
        """Handle Exit from the tray menu."""
        # Stop frontend first, then backend.
        if self._frontend is not None:
            self._frontend.terminate()
            self._frontend = None

        if self._backend is not None:
            self._backend.terminate()
            self._backend = None

        self._tray.setVisible(False)

        # Best-effort cleanup of the PID marker file used by the installer to
        # stop the tray process during uninstall.
        try:
            pid_file = getattr(self, "_pid_file", None)
            if pid_file is not None and pid_file.exists():
                pid_file.unlink()
        except Exception:  # noqa: BLE001, S110
            # Deliberately broad, on the exit path. The pid file is a courtesy for the
            # next launch, so failing to remove it must not stop the application
            # quitting.
            pass

        self._app.quit()
