"""Startup splash window and readiness monitor for the frozen runtime.

On first run the packaged runtime can take a noticeable amount of time to
come up (onefile extraction, backend start, database preparation). Opening
the browser before the backend answers produces an empty page, so instead:

- [`StartupSplashWindow`](backend/src/runtime/splash.py:1) is shown
  immediately: app icon, author, version and a live status line.
- [`StartupMonitor`](backend/src/runtime/startup_monitor.py:1) polls the
  backend readiness probe on a Qt timer without blocking the UI thread,
  updating the splash as startup progresses.
- Only once both the health endpoint and the web UI respond does the
  runtime open the browser and close the splash.

The monitor and the status wording moved to
[`startup_monitor`](backend/src/runtime/startup_monitor.py:1) when this file
reached the module limit; they are re-exported here so either import works.
What remains is the window itself: the icon, the status line, the bar and the
one explanatory line beneath it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap, QShowEvent
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from .startup_monitor import (
    POLL_INTERVAL_MS,
    READINESS_TIMEOUT_SECONDS,
    SPLASH_FAILURE_CLOSE_DELAY_MS,
    STATUS_READY,
    STATUS_STARTING_BACKEND,
    STATUS_TIMED_OUT,
    STATUS_WAITING_FRONTEND,
    StartupMonitor,
    startup_status_message,
)

# Shared identity constants; the defensive import mirrors the other runtime
# modules so both package layouts (src.* and backend.src.*) work.
try:
    from .help_menu import APP_AUTHOR, APP_NAME  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        APP_AUTHOR,
        APP_NAME,
    )


# Splash layout constants (pixels).
_ICON_PX = 96
_SPLASH_MIN_WIDTH_PX = 420
_CONTENT_MARGIN_PX = 24
_CONTENT_SPACING_PX = 10

# A QProgressBar whose maximum is zero animates as a barber pole rather than
# reporting a position, which is Qt's way of saying "unknown".
_INDETERMINATE = 0
_PERCENT_COMPLETE = 100

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
QLabel#SplashDetail {
    color: #8b8781;
    font-size: 11px;
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


class StartupSplashWindow(QWidget):
    """Frameless splash shown while the packaged runtime starts up.

    Shows the application icon with the author line and version beneath it,
    plus a live status label and an indeterminate progress bar.
    """

    def __init__(
        self,
        version: str,
        icon_path: Path | None = None,
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

        # Starts indeterminate because nothing is measurable yet: the backend
        # has not reported how much journal there is to read. set_progress()
        # switches it to a real scale the moment it can.
        self._progress = QProgressBar()
        self._progress.setRange(0, _INDETERMINATE)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        self._status_label = QLabel(STATUS_STARTING_BACKEND)
        self._status_label.setObjectName("SplashStatus")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Reserved for the one thing worth explaining: why a first run is
        # slow. Hidden until there is something to say, so the splash does
        # not carry a permanent empty line.
        self._detail_label = QLabel("")
        self._detail_label.setObjectName("SplashDetail")
        self._detail_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail_label.setWordWrap(True)
        self._detail_label.setVisible(False)
        layout.addWidget(self._detail_label)

    def set_status(self, message: str) -> None:
        """Update the live status line."""
        self._status_label.setText(message)

    def set_detail(self, message: str | None) -> None:
        """Show or clear the explanatory line beneath the status."""
        self._detail_label.setText(message or "")
        self._detail_label.setVisible(bool(message))
        self.adjustSize()

    def set_progress(self, percent: int | None) -> None:
        """Drive the bar, or return it to indeterminate.

        None means the backend cannot say how far along it is, which is the
        honest state before the import has measured itself and again once
        there is nothing left to measure.
        """
        if percent is None:
            self._progress.setRange(0, _INDETERMINATE)
            return

        self._progress.setRange(0, _PERCENT_COMPLETE)
        self._progress.setValue(max(0, min(_PERCENT_COMPLETE, percent)))

    def showEvent(self, event: QShowEvent) -> None:
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
