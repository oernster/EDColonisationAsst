from __future__ import annotations

"""Startup splash window and readiness monitor for the frozen runtime.

On first run the packaged runtime can take a noticeable amount of time to
come up (onefile extraction, backend start, database preparation). Opening
the browser before the backend answers produces an empty page, so instead:

- [`StartupSplashWindow`](backend/src/runtime/splash.py:1) is shown
  immediately: app icon, author, version and a live status line.
- [`StartupMonitor`](backend/src/runtime/splash.py:1) polls the backend
  readiness probe on a Qt timer without blocking the UI thread, updating
  the splash as startup progresses.
- Only once both the health endpoint and the web UI respond does the
  runtime open the browser and close the splash.

The pure decision logic lives in
[`startup_status_message()`](backend/src/runtime/splash.py:1) and the
monitor accepts an injectable clock so both are unit-testable without a
Qt event loop.
"""

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap, QShowEvent
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

# Shared identity constants; the defensive import mirrors the other runtime
# modules so both package layouts (src.* and backend.src.*) work.
try:
    from .help_menu import APP_AUTHOR, APP_NAME  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        APP_AUTHOR,
        APP_NAME,
    )


# Readiness polling cadence and overall budget. First runs can be slow, so
# the budget is deliberately generous; the monitor stops polling as soon as
# both endpoints respond.
POLL_INTERVAL_MS = 500
READINESS_TIMEOUT_SECONDS = 180.0

# How long the splash stays visible after a timeout so the user can read the
# failure status before it closes.
SPLASH_FAILURE_CLOSE_DELAY_MS = 6000

# Splash layout constants (pixels).
_ICON_PX = 96
_SPLASH_MIN_WIDTH_PX = 420
_CONTENT_MARGIN_PX = 24
_CONTENT_SPACING_PX = 10

STATUS_STARTING_BACKEND = "Starting the local backend..."
STATUS_WAITING_FRONTEND = "Backend is up. Preparing the web interface..."
STATUS_READY = "Ready. Opening your browser..."
STATUS_TIMED_OUT = (
    "Startup is taking longer than expected. The tray icon remains "
    "available; use Open Web UI once the backend responds."
)

# Elite-flavoured dark theme with the familiar orange accent.
_SPLASH_STYLESHEET = """
QWidget#StartupSplash {
    background-color: #16181d;
    border: 1px solid #ff8c0d;
}
QLabel {
    color: #e8e6e3;
    background: transparent;
}
QLabel#SplashTitle {
    color: #ff8c0d;
    font-size: 16px;
    font-weight: bold;
}
QLabel#SplashStatus {
    color: #b9b6b1;
}
QProgressBar {
    background-color: #24272e;
    border: 1px solid #3a3e47;
    height: 8px;
}
QProgressBar::chunk {
    background-color: #ff8c0d;
}
"""


def startup_status_message(backend_ok: bool, frontend_ok: bool) -> str:
    """Map a readiness probe result onto a user-facing status line."""
    if backend_ok and frontend_ok:
        return STATUS_READY
    if backend_ok:
        return STATUS_WAITING_FRONTEND
    return STATUS_STARTING_BACKEND


class StartupMonitor:
    """Watches a readiness probe and reports progress to the splash.

    The probe returns a ``(backend_ok, frontend_ok)`` tuple and may BLOCK
    (network connect timeouts), so it must never run on the Qt UI thread:
    a blocked timer slot freezes the splash's progress animation. The
    monitor therefore splits the work across two sides:

    - A daemon worker thread runs ``probe_once()`` in a loop, storing the
      latest result (a single tuple assignment, atomic under the GIL).
    - A Qt timer on the UI thread runs ``poll_once()``, which only READS
      the latest result and drives the status/ready/timeout callbacks, so
      each UI tick costs microseconds and the event loop stays fluid.

    When both probes pass the monitor stops and calls ``on_ready`` exactly
    once; if the timeout budget elapses first it calls ``on_timeout``
    instead. The clock is injectable and ``probe_once()``/``poll_once()``
    can be driven directly, so tests need neither threads nor a running
    Qt event loop.
    """

    def __init__(
        self,
        probe: Callable[[], tuple[bool, bool]],
        on_status: Callable[[str], None],
        on_ready: Callable[[], None],
        on_timeout: Callable[[], None],
        timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
        interval_ms: int = POLL_INTERVAL_MS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._on_status = on_status
        self._on_ready = on_ready
        self._on_timeout = on_timeout
        self._timeout_seconds = timeout_seconds
        self._interval_ms = interval_ms
        self._monotonic = monotonic
        self._deadline: Optional[float] = None
        self._timer: Optional[QTimer] = None
        self._finished = False
        self._latest: tuple[bool, bool] = (False, False)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    @property
    def finished(self) -> bool:
        return self._finished

    def start(self) -> None:
        """Start the probe worker thread and the UI-side Qt timer."""
        worker = threading.Thread(
            target=self._probe_loop,
            name="startup-readiness-probe",
            daemon=True,
        )
        self._worker = worker
        worker.start()

        timer = QTimer()
        timer.setInterval(self._interval_ms)
        timer.timeout.connect(self.poll_once)
        self._timer = timer
        timer.start()

    def probe_once(self) -> None:
        """Run one blocking probe and record the result.

        Called from the worker thread in production; tests call it
        directly to feed results without a thread.
        """
        try:
            self._latest = self._probe()
        except Exception:  # noqa: BLE001
            self._latest = (False, False)

    def poll_once(self) -> None:
        """Consume the latest probe result; never blocks the UI thread."""
        if self._finished:
            return

        # The deadline is anchored to the first poll so that timer start
        # latency does not eat into the readiness budget.
        if self._deadline is None:
            self._deadline = self._monotonic() + self._timeout_seconds

        backend_ok, frontend_ok = self._latest
        self._on_status(startup_status_message(backend_ok, frontend_ok))

        if backend_ok and frontend_ok:
            self._finish()
            self._on_ready()
            return

        if self._monotonic() >= self._deadline:
            self._finish()
            self._on_timeout()

    def _probe_loop(self) -> None:
        """Worker-thread loop: probe, store, sleep, until stopped or ready."""
        while not self._stop_event.is_set():
            self.probe_once()
            if self._latest == (True, True):
                return
            self._stop_event.wait(self._interval_ms / 1000.0)

    def _finish(self) -> None:
        self._finished = True
        self._stop_event.set()
        if self._timer is not None:
            self._timer.stop()
            self._timer = None


class StartupSplashWindow(QWidget):
    """Frameless splash shown while the packaged runtime starts up.

    Shows the application icon with the author line and version beneath it,
    plus a live status label and an indeterminate progress bar.
    """

    def __init__(
        self,
        version: str,
        icon_path: Optional[Path] = None,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.SplashScreen
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setObjectName("StartupSplash")
        self.setMinimumWidth(_SPLASH_MIN_WIDTH_PX)
        self.setStyleSheet(_SPLASH_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            _CONTENT_MARGIN_PX,
            _CONTENT_MARGIN_PX,
            _CONTENT_MARGIN_PX,
            _CONTENT_MARGIN_PX,
        )
        layout.setSpacing(_CONTENT_SPACING_PX)

        if icon_path is not None and icon_path.exists():
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label = QLabel()
                icon_label.setPixmap(
                    pixmap.scaled(
                        _ICON_PX,
                        _ICON_PX,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(icon_label)

        title_label = QLabel(APP_NAME)
        title_label.setObjectName("SplashTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        author_label = QLabel(f"by {APP_AUTHOR}")
        author_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(author_label)

        version_label = QLabel(f"Version {version}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(version_label)

        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        layout.addWidget(progress)

        self._status_label = QLabel(STATUS_STARTING_BACKEND)
        self._status_label.setObjectName("SplashStatus")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

    def set_status(self, message: str) -> None:
        """Update the live status line."""
        self._status_label.setText(message)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self._center_on_screen()

    def _center_on_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        self.adjustSize()
        self.move(geometry.center() - self.rect().center())


__all__ = [
    "POLL_INTERVAL_MS",
    "READINESS_TIMEOUT_SECONDS",
    "SPLASH_FAILURE_CLOSE_DELAY_MS",
    "STATUS_READY",
    "STATUS_STARTING_BACKEND",
    "STATUS_TIMED_OUT",
    "STATUS_WAITING_FRONTEND",
    "StartupMonitor",
    "StartupSplashWindow",
    "startup_status_message",
]
