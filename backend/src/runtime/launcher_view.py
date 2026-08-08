"""The launcher's window, plus the interface that keeps Qt out of the rest.

`LaunchView` is the whole contract between the launcher and its display: four
methods, no Qt types in any signature. `Launcher` in launcher_components talks
to that and never to a widget, which is what lets the tests drive a full run
against a recording stand-in with no QApplication anywhere.

`QtLaunchWindow` is the one real implementation. It is deliberately dumb: it
paints what it is told and owns no orchestration, so everything worth
asserting about a launch sequence is assertable without it.

This module imports nothing from launcher_components, which is what keeps the
dependency one-way.
"""

from __future__ import annotations

from pathlib import Path

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
PROGRESS_MAX = 100

# Window geometry. The height carries the large icon and the primary button
# without the layout having to compress either.
_WINDOW_WIDTH = 420
_WINDOW_HEIGHT = 360

# The artwork is square. The label reserves the same box either way, so the
# layout does not jump when the image fails to load.
_ICON_PX = 160
_ICON_FILENAME = "EDColonisationAsst.png"

_MARGIN_PX = 20
_SPACING_PX = 12
_TITLE_GAP_PX = 8
_BUTTON_MIN_HEIGHT_PX = 40
_BUTTON_MIN_WIDTH_PX = 200


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
        self.setFixedSize(_WINDOW_WIDTH, _WINDOW_HEIGHT)
        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(_MARGIN_PX, _MARGIN_PX, _MARGIN_PX, _MARGIN_PX)
        layout.setSpacing(_SPACING_PX)

        icon_label = self._build_icon_label()

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

        self._open_button = self._build_open_button()

        layout.addWidget(icon_label)
        # Extra space so the large icon does not visually collide with the title.
        layout.addSpacing(_SPACING_PX)
        layout.addWidget(title_label)
        layout.addSpacing(_TITLE_GAP_PX)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)
        layout.addSpacing(_SPACING_PX)
        layout.addWidget(self._open_button, alignment=Qt.AlignHCenter)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _build_icon_label(self) -> QLabel:
        """The app artwork; an empty box of the same size if it is missing."""
        icon_label = QLabel(self)

        # STRICTLY use the PNG for the in-window artwork so it renders crisply.
        # We intentionally do NOT fall back to the ICO here; if the PNG cannot
        # be loaded, the label will remain empty so the problem is obvious.
        png_path = self._project_root / _ICON_FILENAME

        pixmap = QPixmap()
        if png_path.exists():
            pixmap = QPixmap(str(png_path))

        if not pixmap.isNull():
            icon_label.setPixmap(
                pixmap.scaled(
                    _ICON_PX,
                    _ICON_PX,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

        icon_label.setMinimumSize(_ICON_PX, _ICON_PX)
        icon_label.setAlignment(Qt.AlignHCenter)
        return icon_label

    def _build_open_button(self) -> QPushButton:
        """The primary action, disabled until the backend reports ready."""
        button = QPushButton("Open Web UI", self)
        button.setEnabled(False)
        button.setMinimumHeight(_BUTTON_MIN_HEIGHT_PX)
        button.setMinimumWidth(_BUTTON_MIN_WIDTH_PX)
        button.setStyleSheet(
            "font-size: 13px; font-weight: 600; padding: 8px 24px;",
        )
        button.clicked.connect(self._on_open_clicked)
        return button

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


__all__ = ["APP_NAME", "PROGRESS_MAX", "LaunchView", "QtLaunchWindow"]
