"""Launcher orchestration: also the public surface of the launcher stack.

This module contains the GUI launcher's orchestration: the ordered steps that
take a bare checkout to a running backend, plus the subprocess and log
plumbing those steps need. The window itself lives in
[`launcher_view.py`](backend/src/runtime/launcher_view.py:1), which this module
imports and re-exports so that
[`launcher.py`](backend/src/launcher.py:1) keeps reaching the whole stack
through one name.

The dependency is one-way: this module knows about the view module, the view
module knows nothing about this one; `Launcher` talks only to the
`LaunchView` interface. That is what lets a full launch sequence be tested
against a recording stand-in with no Qt involved.

Public API re-exported by [`launcher`](backend/src/launcher.py:1):

- `APP_NAME`, `BACKEND_PORT`, `FRONTEND_PORT`, `PROGRESS_MAX`
- `InitStep`
- `LaunchView`
- `QtLaunchWindow`
- `Launcher`

`__all__` is what marks the re-exports intentional. Without it they read as
unused imports and an unattended `ruff check --fix` deletes them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time

from .launcher_view import APP_NAME, PROGRESS_MAX, LaunchView, QtLaunchWindow

try:
    from ..constants import DEFAULT_BACKEND_PORT  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script,
    # which the frozen Nuitka build does. That is an ImportError; anything else
    # raised while importing is a real defect and should surface.
    from backend.src.constants import (  # type: ignore[import-error]
        DEFAULT_BACKEND_PORT,
    )

BACKEND_PORT = DEFAULT_BACKEND_PORT
FRONTEND_PORT = 5173

# Readiness polling. The timeout is generous because the first run of a fresh
# checkout is creating a venv and installing into it before this point.
_READINESS_TIMEOUT_SECONDS = 60.0
_READINESS_POLL_SECONDS = 1.0
_PROBE_TIMEOUT_SECONDS = 1

# A response at all means the port is answering, which is what readiness asks.
# 4xx counts: an endpoint that refuses the request is still an endpoint.
_HTTP_OK = 200
_HTTP_SERVER_ERROR = 500

# Windows process creation flag: start the tray without a console window.
_CREATE_NO_WINDOW = 0x08000000

_LOG_FILENAME = "run-edca.log"


@dataclass(frozen=True)
class InitStep:
    """Represents a single initialization step."""

    name: str
    progress: int
    action: Callable[[], None]


class Launcher:
    """Orchestrates initialization steps and updates the view."""

    def __init__(self, project_root: Path, view: LaunchView) -> None:
        self._project_root = project_root
        self._view = view
        self._backend_dir = project_root / "backend"
        self._frontend_dir = project_root / "frontend"
        self._venv_python = self._backend_dir / "venv" / "Scripts" / "python.exe"
        self._log_path = project_root / _LOG_FILENAME

    # Public API -------------------------------------------------------

    def run(self) -> None:
        """Run all initialization steps, updating the view."""
        try:
            for step in self._build_steps():
                self._view.set_status(step.name, step.progress)
                step.action()
            # Once all steps are done, allow opening the UI served by the backend.
            frontend_url = f"http://127.0.0.1:{BACKEND_PORT}/app/"
            self._view.set_status(f"Ready. Open {frontend_url}", PROGRESS_MAX)
            self._view.allow_open_frontend(frontend_url)
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad. The steps this runs span venv creation, pip, npm and
            # process spawning, so the failure set is the union of everything those can
            # do. The launcher's job here is to show the user what went wrong rather
            # than to disappear.
            self._view.show_error(str(exc))

    # Step construction ------------------------------------------------

    def _build_steps(self) -> list[InitStep]:
        """
        Define the ordered initialisation steps for the launcher.

        Note that we no longer install or start the frontend via npm at
        runtime. Instead, the frontend is expected to be built ahead of
        time (e.g. `npm run build`) and served as static files by the
        backend. This removes any Node.js/npm requirement for end users.

        The progress figures are the table: each one is where that step
        leaves the bar, which is why they are written here rather than named.
        """
        return [
            InitStep("Checking Python environment...", 5, self._check_python),
            InitStep("Ensuring backend virtual environment...", 20, self._ensure_venv),
            InitStep(
                "Installing backend dependencies...",
                45,
                self._install_backend_deps,
            ),
            InitStep("Starting services...", 75, self._start_services),
            InitStep(
                "Waiting for web UI to become available...",
                95,
                self._wait_for_readiness,
            ),
        ]

    # Individual actions -----------------------------------------------

    def _check_python(self) -> None:
        """Ensure that some python is available."""
        try:
            result = subprocess.run(
                ["python", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise RuntimeError(f"Python is required but was not found: {exc}") from exc

        self._append_log(f"[launcher] System python: {result.stdout.strip()}")

    def _ensure_venv(self) -> None:
        """Create backend/venv if missing."""
        if self._venv_python.exists():
            self._append_log(f"[launcher] Using existing venv: {self._venv_python}")
            return

        self._append_log("[launcher] Creating backend/venv...")
        cmd = ["python", "-m", "venv", str(self._backend_dir / "venv")]
        self._run_subprocess(cmd, cwd=self._project_root, label="create venv")

    def _install_backend_deps(self) -> None:
        """Install backend Python dependencies into the venv.

        In an installed environment the venv will typically already have had
        its dependencies installed successfully by a previous run. If this
        step fails (for example due to a transient network issue), we log a
        warning and continue using the existing environment instead of
        treating it as a hard error that blocks the launcher UI.
        """
        if not self._venv_python.exists():
            # If the venv python is missing entirely, subsequent steps are
            # unlikely to succeed, so this is still considered fatal.
            raise RuntimeError(
                "Virtual environment python.exe is missing; "
                "cannot install backend deps.",
            )

        requirements = self._backend_dir / "requirements.txt"
        if not requirements.exists():
            self._append_log(
                "[launcher] backend/requirements.txt not found; "
                "skipping backend deps install.",
            )
            return

        self._append_log(
            f"[launcher] Installing backend dependencies from {requirements}...",
        )
        cmd = [str(self._venv_python), "-m", "pip", "install", "-r", str(requirements)]
        try:
            self._run_subprocess(
                cmd,
                cwd=self._project_root,
                label="install backend deps",
            )
        except RuntimeError as exc:
            # Log the error but continue with the existing environment so that
            # users with an already-populated venv are not blocked by a
            # subsequent pip failure.
            self._append_log(
                "[launcher] WARNING: Backend dependency installation failed but "
                f"continuing with existing environment: {exc}",
            )

    def _start_services(self) -> None:
        """
        Start tray controller using the venv python.

        The tray controller is responsible for starting the backend (uvicorn)
        and frontend (Vite dev server) in the background.
        """
        if not self._venv_python.exists():
            raise RuntimeError(
                "Virtual environment python.exe is missing; cannot start services.",
            )

        tray_script = self._backend_dir / "src" / "tray_app.py"
        if not tray_script.exists():
            raise RuntimeError(f"Tray script not found at {tray_script}")

        self._append_log("[launcher] Starting tray controller...")
        # Launch tray in the background; we do not wait here, readiness is
        # checked separately.
        command = [str(self._venv_python), str(tray_script)]
        if sys.platform.startswith("win"):
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen(
                command,
                cwd=str(self._project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_CREATE_NO_WINDOW,
                startupinfo=startup_info,
            )
        else:
            subprocess.Popen(
                command,
                cwd=str(self._project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def _wait_for_readiness(self) -> None:
        """Poll backend API and frontend UI endpoints until they respond or timeout."""
        import urllib.error
        import urllib.request

        def _probe(url: str) -> bool:
            try:
                with urllib.request.urlopen(
                    url, timeout=_PROBE_TIMEOUT_SECONDS
                ) as resp:
                    return _HTTP_OK <= resp.getcode() < _HTTP_SERVER_ERROR
            except urllib.error.URLError:
                return False

        # Backend health endpoint and static frontend served by the backend.
        backend_health = f"http://127.0.0.1:{BACKEND_PORT}/api/health"
        frontend_url = f"http://127.0.0.1:{BACKEND_PORT}/app/"

        deadline = time.time() + _READINESS_TIMEOUT_SECONDS
        self._append_log(
            "[launcher] Waiting for backend at "
            f"{backend_health} and frontend at {frontend_url}...",
        )

        while time.time() < deadline:
            backend_ok = _probe(backend_health)
            frontend_ok = _probe(frontend_url)
            if backend_ok and frontend_ok:
                self._append_log("[launcher] Backend and frontend are ready.")
                return
            # Light backoff and keep GUI responsive.
            self._view.process_events()
            time.sleep(_READINESS_POLL_SECONDS)

        self._append_log(
            "[launcher] Timeout waiting for backend/frontend readiness; "
            "continuing anyway.",
        )

    # Helpers -----------------------------------------------------------

    def _run_subprocess(self, cmd: list[str], cwd: Path, label: str) -> None:
        """Run a subprocess synchronously, raising on error and logging output."""
        self._append_log(f"[launcher] Running ({label}): {' '.join(cmd)} (cwd={cwd})")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Failed to start process for {label}: {exc}") from exc

        # Stream output to log while keeping UI responsive.
        assert proc.stdout is not None
        for line in proc.stdout:
            self._append_log(line.rstrip("\n"))
            self._view.process_events()

        ret = proc.wait()
        if ret != 0:
            raise RuntimeError(f"Command for '{label}' failed with exit code {ret}")

    def _append_log(self, message: str) -> None:
        try:
            with self._log_path.open("a", encoding="utf-8") as f:
                f.write(message + "\n")
        except OSError:
            # Logging failures should not break the launcher.
            pass


__all__ = [
    "APP_NAME",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "PROGRESS_MAX",
    "InitStep",
    "LaunchView",
    "Launcher",
    "QtLaunchWindow",
]
