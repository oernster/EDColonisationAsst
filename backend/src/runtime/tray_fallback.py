"""The tray's stand-in on a desktop that has no system tray.

A packaged install has no window of its own: the backend runs headless and the
tray icon is the entire visible surface, so it is how the user reaches the web
UI and (more importantly) how they quit. That arrangement assumes a tray
exists. On Windows one always does. On Linux a tray icon is not drawn into a
panel by the application at all: it is published over D-Bus as a
StatusNotifierItem and the desktop's own watcher draws it. Several desktops
ship no watcher; inside a flatpak the watcher is unreachable unless the
sandbox is granted the name.

Without this module the failure is silent and total: the application starts,
serves the interface, shows nothing and cannot be quit except by killing the
process. So when there is no tray, this window takes its place. It offers the
same two actions and the same Help menu, saying plainly why it is there,
which is what stops it reading as an unexplained extra window.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

try:
    from .help_menu import add_help_menu  # type: ignore[import-not-found]
except ImportError:
    # The relative form fails only when this module runs as a top-level script,
    # which the frozen build does. That is an ImportError; anything else raised
    # while importing is a real defect and should surface.
    from backend.src.runtime.help_menu import (  # type: ignore[import-error]
        add_help_menu,
    )

_WINDOW_TITLE = "Elite: Dangerous Colonisation Assistant"

_EXPLANATION = (
    "This desktop reported no system tray, so this window stands in for the "
    "tray icon. Use it to open the interface in your browser or to quit."
)

# Wide enough for the explanation to wrap to two lines rather than one long
# one, which is what keeps the window a small panel rather than a banner.
_WINDOW_WIDTH = 460

_OPEN_BUTTON_TEXT = "Open Web UI"
_EXIT_BUTTON_TEXT = "Exit"

# A 2px transparent default so gaining a border on hover or focus never
# reflows the row; both rules are gated on :enabled so a disabled control
# stays inert to the mouse and to a skipped focus step alike.
_BUTTON_STYLE = """
QPushButton {
    border: 2px solid transparent;
    padding: 4px 12px;
}
QPushButton:enabled:hover {
    border: 2px solid #f0a000;
}
QPushButton:enabled:focus {
    border: 2px solid #f0a000;
}
"""


class TrayFallbackWindow(QWidget):
    """A small control panel offering what the tray menu would have offered.

    ``on_exit`` is expected to run the same confirmation the tray's Exit runs
    and to report whether the application is actually going away. Closing this
    window through its title bar is the same request as pressing Exit, so it
    is routed to the same callback: a window that vanished on a close while
    the process kept running would put the user back in exactly the state this
    module exists to prevent, with no way to reach the application at all.
    """

    def __init__(
        self,
        *,
        icon_path: Path | None,
        about_icon_path: Path | None,
        on_open_web_ui: Callable[[], None],
        on_exit: Callable[[], bool],
        on_check_updates: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self._on_open_web_ui = on_open_web_ui
        self._on_exit = on_exit

        self.setWindowTitle(_WINDOW_TITLE)
        if icon_path is not None and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)

        menu_bar = QMenuBar(self)
        add_help_menu(
            menu_bar,
            icon_path=about_icon_path,
            parent=self,
            on_check_updates=on_check_updates,
        )
        layout.setMenuBar(menu_bar)

        explanation = QLabel(_EXPLANATION)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        buttons = QHBoxLayout()
        buttons.addStretch()

        open_button = QPushButton(_OPEN_BUTTON_TEXT)
        open_button.setStyleSheet(_BUTTON_STYLE)
        open_button.clicked.connect(self._handle_open)  # type: ignore[arg-type]
        buttons.addWidget(open_button)

        exit_button = QPushButton(_EXIT_BUTTON_TEXT)
        exit_button.setStyleSheet(_BUTTON_STYLE)
        exit_button.clicked.connect(self._handle_exit)  # type: ignore[arg-type]
        buttons.addWidget(exit_button)

        layout.addLayout(buttons)

        self.setMinimumWidth(_WINDOW_WIDTH)
        # Opening the interface is what the user came here to do, so it is the
        # focused control. Two buttons need no explicit focus ring: the natural
        # tab order over two siblings is already the order they are read in.
        open_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _handle_open(self) -> None:
        self._on_open_web_ui()

    def _handle_exit(self) -> None:
        self._on_exit()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Treat closing the window as pressing Exit.

        The application sets quitOnLastWindowClosed to False, because it is
        built around a tray that outlives every window. Here there is no tray,
        so a close that merely hid this window would leave the process running
        with nothing on screen to reach it by.
        """
        if self._on_exit():
            event.accept()
        else:
            # The user cancelled at the confirmation, so the window stays.
            event.ignore()


__all__ = ["TrayFallbackWindow"]
