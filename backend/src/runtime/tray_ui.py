"""System tray UI for the frozen runtime.

[`TrayUIController`] is the whole visible surface of a packaged install: the
backend runs headless in-process, so the tray icon is how the user reaches the
web UI and how they exit.

This is not the same tray as
[`tray_components.TrayController`](backend/src/runtime/tray_components.py:1),
which belongs to the development `tray_app` entrypoint and supervises backend
and frontend child processes. The two look alike and manage different things:
this one holds a
[`BackendServerController`](backend/src/runtime/backend_server.py:1) running
inside its own process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import webbrowser

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .common import logger
from .dialogs import ask_yes_no
from .environment import RuntimeEnvironment

# Shared Help menu (About + Check for Updates) used by the tray UI.
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
    from .update_check import default_update_check  # type: ignore[import-not-found]
except ImportError:
    from backend.src.runtime.update_check import (  # type: ignore[import-error]
        default_update_check,
    )

if TYPE_CHECKING:
    from .backend_server import BackendServerController

_TRAY_TOOLTIP = "Elite: Dangerous Colonisation Assistant"
_EXIT_DIALOG_TITLE = "Exit ED Colonisation Assistant"
_EXIT_DIALOG_QUESTION = "Are you sure you want to exit EDCA?"


class TrayUIController:
    """
    Simple Qt-based system tray UI for the frozen runtime.

    Responsibilities:
    - Show a tray icon using the EDCA icon.
    - Provide "Open Web UI" and "Exit" actions.
    - Stop the backend server cleanly on exit.
    """

    def __init__(
        self,
        app: QApplication,
        env: RuntimeEnvironment,
        backend: BackendServerController,
    ) -> None:
        self._app = app
        self._env = env
        self._backend = backend

        # Built before the menu, which hangs its Check for Updates action on
        # it. Held on the controller because it is a QObject with no parent:
        # dropping the reference would collect it and stop both timers.
        self._updates = default_update_check(icon_path=env.icon_path)

        self._tray = QSystemTrayIcon()
        self._configure_tray_icon()
        self._create_menu()

        # Treat clicking the tray icon itself as a large "Open Web UI" button.
        # Left-click or double-click on the tray icon will open the web UI,
        # in addition to the explicit "Open Web UI" menu item.
        self._tray.activated.connect(self._on_tray_activated)  # type: ignore[arg-type]

    # -------------------- setup ------------------------------------------------

    def _configure_tray_icon(self) -> None:
        icon_path = self._env.icon_path
        if icon_path.exists():
            self._tray.setIcon(QIcon(str(icon_path)))
        self._tray.setToolTip(_TRAY_TOOLTIP)
        self._tray.setVisible(True)

    def _create_menu(self) -> None:
        menu = QMenu()
        open_action = menu.addAction("Open Web UI")
        open_action.triggered.connect(self._on_open_web_ui)  # type: ignore[arg-type]

        menu.addSeparator()
        about_icon = resolve_about_icon(self._env.project_root)
        add_help_menu(
            menu,
            icon_path=about_icon,
            on_check_updates=self._updates.check_manually,
        )

        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._on_exit)  # type: ignore[arg-type]

        self._tray.setContextMenu(menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """
        Handle clicks on the tray icon itself.

        This effectively turns the tray icon into a large "Open Web UI" button:
        a left-click or double-click will open the browser to the frontend URL.
        """
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._on_open_web_ui()

    # -------------------- actions ---------------------------------------------

    def _on_open_web_ui(self) -> None:
        url = self._env.frontend_url
        logger.info("Opening web UI at %s", url)
        webbrowser.open(url)

    def _on_exit(self) -> None:
        logger.info("Exit requested from tray menu.")
        # Confirm with the user to avoid accidental shutdown. This goes through
        # `ask_yes_no` rather than QMessageBox.question because there is no
        # parent window to give it: a bare question box opens behind the game
        # and the user, seeing nothing happen, decides Exit is broken.
        if not ask_yes_no(
            _EXIT_DIALOG_TITLE,
            _EXIT_DIALOG_QUESTION,
            icon_path=self._env.icon_path,
        ):
            logger.info("Exit cancelled at the confirmation.")
            return

        try:
            self._backend.stop()
        finally:
            self._tray.setVisible(False)
            self._app.quit()

    # -------------------- public API ------------------------------------------

    def show(self) -> None:
        # Nothing extra to do at the moment; kept for symmetry / extension.
        self._tray.show()


__all__ = ["TrayUIController"]
