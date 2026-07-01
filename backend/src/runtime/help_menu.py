from __future__ import annotations

"""Shared Help menu and About dialog for the EDCA tray UIs.

This module is used by both tray controllers:

- [`TrayUIController`](backend/src/runtime/app_runtime.py:1) for the frozen
  (packaged EXE) runtime.
- [`TrayController`](backend/src/runtime/tray_components.py:1) for the
  development tray.

It provides:

- [`add_help_menu()`](backend/src/runtime/help_menu.py:1): appends a
  "Help" submenu (About, Check for Updates) to an existing tray menu.
- [`AboutDialog`](backend/src/runtime/help_menu.py:1): the Help | About
  dialog showing the app icon, author, copyright and open source credits.
- [`open_releases_page()`](backend/src/runtime/help_menu.py:1): opens the
  GitHub releases page so users can check for newer versions.

The application version is never hardcoded here; it is resolved from the
top-level VERSION file via the package `__version__`.
"""

import webbrowser
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

# Canonical version resolved from the top-level VERSION file. The defensive
# import mirrors the strategy used by the other runtime modules so that both
# package layouts (src.* and backend.src.*) work.
try:
    from .. import __version__  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    from backend.src import __version__  # type: ignore[import-error]


APP_NAME = "Elite: Dangerous Colonisation Assistant"
APP_AUTHOR = "Oliver Ernster"
COPYRIGHT_YEAR = "2026"
RELEASES_URL = "https://github.com/oernster/EDColonisationAsst/releases"

# Menu item labels, shared with tests so wording stays consistent.
HELP_MENU_TITLE = "Help"
ABOUT_ACTION_TEXT = "About"
CHECK_FOR_UPDATES_ACTION_TEXT = "Check for Updates"

# Dialog sizing constants (pixels).
_ICON_PX = 96
_DIALOG_MIN_WIDTH_PX = 560
_BODY_MIN_HEIGHT_PX = 360

# Icon files installed next to the runtime EXE (and present in the source
# tree). The PNG renders better at About/splash sizes; the ICO is a fallback.
_ICON_FILE_CANDIDATES = ("EDColonisationAsst.png", "EDColonisationAsst.ico")

# Every real dependency the application ships, with its licence and the role
# it plays. Rendered as the "Open source credits" list in the About dialog.
_OPEN_SOURCE_CREDITS: tuple[tuple[str, str, str], ...] = (
    ("Python", "PSF Licence", "the language the backend is written in"),
    ("PySide6 (Qt for Python)", "LGPL-3.0", "tray UI and dialogs"),
    ("FastAPI", "MIT", "backend web framework"),
    ("Uvicorn", "BSD-3-Clause", "ASGI server"),
    ("Pydantic", "MIT", "data validation and settings"),
    ("aiofiles", "Apache-2.0", "async file access"),
    ("httpx", "BSD-3-Clause", "HTTP client"),
    ("PyYAML", "MIT", "configuration parsing"),
    ("watchdog", "Apache-2.0", "journal file watching"),
    ("websockets", "BSD-3-Clause", "live updates"),
    ("python-dotenv", "BSD-3-Clause", "environment configuration"),
    ("python-multipart", "Apache-2.0", "form parsing"),
    ("Nuitka", "Apache-2.0", "runtime packaging"),
    ("React", "MIT", "web UI framework"),
    ("MUI (Material UI)", "MIT", "web UI components"),
    ("Emotion", "MIT", "web UI styling"),
    ("axios", "MIT", "web UI HTTP client"),
    ("Zustand", "MIT", "web UI state management"),
    ("Vite", "MIT", "frontend build tooling"),
    ("TypeScript", "Apache-2.0", "frontend language"),
)

_CAFFEINE_CREDIT = (
    "The caffeine drink providers of planet Earth: coffee roasters, tea "
    "growers and the manufacturers of energy drinks with names that sound "
    "like rejected superheroes. Licence: proprietary, non-transferable and "
    "billed per mug. This software was, strictly speaking, co-authored by "
    "caffeine; the human just did the typing."
)


def resolve_about_icon(root: Path) -> Optional[Path]:
    """Return the best icon file under ``root`` for dialog display, if any."""
    for name in _ICON_FILE_CANDIDATES:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def build_about_html(version: str) -> str:
    """Build the HTML body for the About dialog."""
    credit_items = "".join(
        f"<li><b>{name}</b> - {licence} ({context}).</li>"
        for name, licence, context in _OPEN_SOURCE_CREDITS
    )
    return (
        f"<h2>{APP_NAME}</h2>"
        f"<p><b>Version:</b> {version}</p>"
        f"<p><b>Author:</b> by {APP_AUTHOR}</p>"
        f"<p><b>Copyright:</b> &copy; {APP_AUTHOR} {COPYRIGHT_YEAR}</p>"
        "<p>Licensed under the LGPL-3.0. See the LICENSE file in the "
        "install directory for the full text.</p>"
        "<hr>"
        "<h3>Open source credits</h3>"
        f"<ul>{credit_items}</ul>"
        "<h3>Honourable mention</h3>"
        f"<p>{_CAFFEINE_CREDIT}</p>"
        "<p>Built on the Python, Qt and web ecosystems, with thanks to "
        "their communities.</p>"
    )


class AboutDialog(QDialog):
    """Help | About dialog: icon, author, copyright and credits."""

    def __init__(
        self,
        version: str,
        icon_path: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(_DIALOG_MIN_WIDTH_PX)

        layout = QVBoxLayout(self)

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
            self.setWindowIcon(QIcon(str(icon_path)))

        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setMinimumHeight(_BODY_MIN_HEIGHT_PX)
        body.setHtml(build_about_html(version))
        layout.addWidget(body)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)


def open_releases_page() -> None:
    """Open the GitHub releases page in the default browser."""
    try:
        webbrowser.open(RELEASES_URL)
    except Exception:  # noqa: BLE001
        # A browser launch failure must never crash the tray.
        pass


def add_help_menu(
    menu: Any,
    icon_path: Optional[Path] = None,
    parent: Optional[QWidget] = None,
    version: Optional[str] = None,
) -> Any:
    """Append a Help submenu (About, Check for Updates) to ``menu``.

    The submenu is created through ``menu.addMenu`` so that tests can drive
    this with lightweight menu fakes; no Qt widgets are constructed until an
    action is actually triggered.

    Returns the created submenu.
    """
    resolved_version = version if version is not None else __version__

    help_menu = menu.addMenu(HELP_MENU_TITLE)

    about_action = help_menu.addAction(ABOUT_ACTION_TEXT)

    def _show_about() -> None:
        dialog = AboutDialog(resolved_version, icon_path=icon_path, parent=parent)
        dialog.exec()

    about_action.triggered.connect(_show_about)

    updates_action = help_menu.addAction(CHECK_FOR_UPDATES_ACTION_TEXT)
    updates_action.triggered.connect(open_releases_page)

    return help_menu


__all__ = [
    "APP_AUTHOR",
    "APP_NAME",
    "AboutDialog",
    "COPYRIGHT_YEAR",
    "RELEASES_URL",
    "add_help_menu",
    "build_about_html",
    "open_releases_page",
    "resolve_about_icon",
]
