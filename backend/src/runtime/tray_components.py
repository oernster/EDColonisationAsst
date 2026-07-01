from __future__ import annotations

"""Tray controller components for the EDCA runtime stack.

This module contains the core tray logic that was previously defined in
[`tray_app.py`](backend/src/tray_app.py:1):

- [`ProcessGroup`](backend/src/runtime/tray_components.py:29) – thin wrapper
  around a child `subprocess.Popen` with graceful termination semantics.
- [`TrayController`](backend/src/runtime/tray_components.py:62) – the Qt
  system tray controller responsible for starting and stopping the backend
  and frontend processes and wiring up the tray icon and Exit action.

By moving these classes into `runtime.tray_components`, the
[`tray_app`](backend/src/tray_app.py:1) module can be slimmed down to a small
entrypoint that focuses on:

- Single-instance enforcement via `ApplicationInstanceLock`.
- Creating the `QApplication` and instantiating `TrayController`.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# Shared Help menu (About + Check for Updates). Defensive import so this
# module works both as part of the backend.src package and when executed
# with backend/ on sys.path.
try:
    from .help_menu import add_help_menu, resolve_about_icon  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        add_help_menu,
        resolve_about_icon,
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
        except Exception:
            # Fallback to kill if terminate is not supported on this platform.
            try:
                self._popen.kill()
            except Exception:
                return

        try:
            self._popen.wait(timeout=graceful_timeout)
        except Exception:
            try:
                self._popen.kill()
            except Exception:
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
        self._backend: Optional[ProcessGroup] = None
        self._frontend: Optional[ProcessGroup] = None

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
        except Exception:
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
        add_help_menu(menu, icon_path=resolve_about_icon(self._root))
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
        - A user-local log under %LOCALAPPDATA%\\EDColonisationAsst\\run-edca.log
          to avoid any filesystem virtualisation / permission issues writing
          directly into Program Files.
        """
        # Primary: install root next to run-edca.bat
        try:
            root_log = self._root / "run-edca.log"
            with root_log.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception:
            # Logging failures must never crash the tray.
            pass

        # Secondary: user-local log that should always be writable.
        try:
            local_base = os.environ.get("LOCALAPPDATA")
            if local_base:
                user_log_dir = Path(local_base) / "EDColonisationAsst"
                user_log_dir.mkdir(parents=True, exist_ok=True)
                user_log = user_log_dir / "run-edca.log"
                with user_log.open("a", encoding="utf-8") as f:
                    f.write(message + "\n")
        except Exception:
            # Ignore all errors here as well.
            pass

    # --------------------------------------------------------------------- start

    def _start_services(self) -> None:
        """Start backend and frontend as background processes."""
        self._backend = self._start_backend()
        self._frontend = self._start_frontend()

    def _start_backend(self) -> Optional[ProcessGroup]:
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
            "8000",
        ]

        # Log what we're about to start to help diagnose issues in production.
        self._log_message(
            f"Starting backend process: {' '.join(cmd)} (cwd={self._root})",
        )
        return self._spawn_process(cmd, cwd=self._root, name="backend")

    def _start_frontend(self) -> Optional[ProcessGroup]:
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
    ) -> Optional[ProcessGroup]:
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
                except Exception:
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
        except Exception as exc:
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
        except Exception:
            pass

        self._app.quit()
