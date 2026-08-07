"""Launcher UI and orchestration components.

This module contains the bulk of the GUI launcher implementation that was
previously defined in a single large file in
[`launcher.py`](backend/src/launcher.py:1). Keeping these components here
allows [`launcher.main()`](backend/src/launcher.py:441) to remain a small,
entrypoint-focused module while the OO logic and Qt view live in a dedicated
runtime submodule.

Public API re-exported by [`launcher`](backend/src/launcher.py:1):

- `APP_NAME`, `BACKEND_PORT`, `FRONTEND_PORT`, `PROGRESS_MAX`
- `InitStep`
- `LaunchView`
- `QtLaunchWindow`
- `Launcher`
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Elite: Dangerous Colonisation Assistant"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
PROGRESS_MAX = 100


@dataclass(frozen=True)
class InitStep:
    """Represents a single initialization step."""

    name: str
    progress: int
    action: Callable[[], None]


class LaunchView:
    """Abstraction of the launcher UI for testability and SOLID compliance."""

    def set_status(
        self, message: str, progress: int
    ) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def show_error(self, message: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def allow_open_frontend(self, url: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def process_events(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class QtLaunchWindow(QMainWindow, LaunchView):
    """Simple launcher window with icon, title, status label and progress bar."""

    def __init__(self, project_root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._frontend_url: str | None = None

        self.setWindowTitle(f"{APP_NAME} Launcher")
        # Taller window to comfortably fit a larger app icon and primary button.
        self.setFixedSize(420, 360)
        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Icon
        icon_label = QLabel(self)

        # STRICTLY use the PNG for the in-window artwork so it renders crisply.
        # We intentionally do NOT fall back to the ICO here; if the PNG cannot
        # be loaded, the label will remain empty so the problem is obvious.
        png_path = self._project_root / "EDColonisationAsst.png"

        pixmap = QPixmap()
        if png_path.exists():
            pixmap = QPixmap(str(png_path))

        if not pixmap.isNull():
            scaled = pixmap.scaled(
                160,
                160,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            icon_label.setPixmap(scaled)

        icon_label.setMinimumSize(160, 160)
        icon_label.setAlignment(Qt.AlignHCenter)

        # Title
        title_label = QLabel(APP_NAME, self)
        title_label.setAlignment(Qt.AlignHCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        # Status label
        self._status_label = QLabel("Initialising...", self)
        self._status_label.setAlignment(Qt.AlignHCenter)
        self._status_label.setWordWrap(True)

        # Progress bar
        self._progress = QProgressBar(self)
        self._progress.setRange(0, PROGRESS_MAX)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")
        self._progress.setTextVisible(True)

        # "Open UI" button (enabled when ready): make it visually prominent.
        self._open_button = QPushButton("Open Web UI", self)
        self._open_button.setEnabled(False)
        self._open_button.setMinimumHeight(40)
        self._open_button.setMinimumWidth(200)
        self._open_button.setStyleSheet(
            "font-size: 13px; font-weight: 600; padding: 8px 24px;",
        )
        self._open_button.clicked.connect(self._on_open_clicked)

        layout.addWidget(icon_label)
        # Extra space so the large icon does not visually collide with the title.
        layout.addSpacing(12)
        layout.addWidget(title_label)
        layout.addSpacing(8)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)
        layout.addSpacing(12)
        layout.addWidget(self._open_button, alignment=Qt.AlignHCenter)

        central.setLayout(layout)
        self.setCentralWidget(central)

    # LaunchView implementation -------------------------------------------------

    def set_status(self, message: str, progress: int) -> None:
        self._status_label.setText(message)
        self._progress.setValue(progress)
        self.process_events()

    def show_error(self, message: str) -> None:
        # For now, just show it prominently in the status label.
        self._status_label.setText(f"ERROR: {message}")
        self._progress.setValue(0)
        self.process_events()

    def allow_open_frontend(self, url: str) -> None:
        self._frontend_url = url
        self._open_button.setEnabled(True)
        self.process_events()

    def process_events(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    # ------------------------------------------------------------------ slots

    def _on_open_clicked(self) -> None:
        if self._frontend_url:
            import webbrowser  # local import to keep module import cost low

            webbrowser.open(self._frontend_url)


class Launcher:
    """Orchestrates initialization steps and updates the view."""

    def __init__(self, project_root: Path, view: LaunchView) -> None:
        self._project_root = project_root
        self._view = view
        self._backend_dir = project_root / "backend"
        self._frontend_dir = project_root / "frontend"
        self._venv_python = self._backend_dir / "venv" / "Scripts" / "python.exe"
        self._log_path = project_root / "run-edca.log"

    # Public API -------------------------------------------------------

    def run(self) -> None:
        """Run all initialization steps, updating the view."""
        try:
            steps = self._build_steps()
            for step in steps:
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
        if sys.platform.startswith("win"):
            CREATE_NO_WINDOW = 0x08000000
            startup_info = subprocess.STARTUPINFO()
            startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen(
                [str(self._venv_python), str(tray_script)],
                cwd=str(self._project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                startupinfo=startup_info,
            )
        else:
            subprocess.Popen(
                [str(self._venv_python), str(tray_script)],
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
                with urllib.request.urlopen(url, timeout=1) as resp:
                    return 200 <= resp.getcode() < 500
            except urllib.error.URLError:
                return False

        # Backend health endpoint and static frontend served by the backend.
        backend_health = f"http://127.0.0.1:{BACKEND_PORT}/api/health"
        frontend_url = f"http://127.0.0.1:{BACKEND_PORT}/app/"

        deadline = time.time() + 60.0  # 60 seconds
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
            time.sleep(1.0)

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
