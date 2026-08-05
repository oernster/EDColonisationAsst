"""The setup window: a themed, state-aware lifecycle screen.

The window holds no installer logic of its own. It reads one state snapshot,
decides what to offer, and hands each operation to a worker thread. British
spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QStatusBar,
    QToolBar,
)

from installer.constants import APP_DISPLAY_NAME, APP_ID
from installer.ops.errors import InstallerError
from installer.ops.install_ops import InstallOptions, install, repair
from installer.ops.paths import install_target, installed_exe, is_windows
from installer.ops.payload import app_version, licence_text
from installer.ops.progress import COMPLETE_PCT, MINIMUM_PCT
from installer.ops.running_app import close_running_app, is_app_running, launch
from installer.ops.uninstall_ops import uninstall
from installer.state.model import InstallState, detect
from installer.state.registry import set_autostart
from installer.ui._main_window_build import (
    IDLE_STATUS,
    INSTALL_PATH_TEXT,
    WindowWidgets,
    build_window,
    primary_label,
    subtitle_text,
)
from installer.ui.dialogs import (
    NOT_INSTALLED_MESSAGE,
    NOT_INSTALLED_TITLE,
    confirm_close_running,
    confirm_uninstall,
    show_error,
    show_info,
)
from installer.ui.icons import app_icon
from installer.ui.layout import WINDOW_HEIGHT, WINDOW_WIDTH
from installer.ui.licence_dialog import LicenceDialog
from installer.ui.theme import DARK, LIGHT
from installer.ui.theme_manager import ThemeManager
from installer.ui.worker import OperationRunner

WINDOW_TITLE = f"{APP_DISPLAY_NAME} Installer"
CHOOSE_DIR_LABEL = "Change Install Location"
CHOOSE_DIR_TIP = "Choose a different installation folder"
ABOUT_LABEL = "About / Licence"
ABOUT_TIP = "Show the licence information"
CHOOSE_DIR_CAPTION = "Choose installation directory"

INSTALL_DONE_TITLE = "Installation complete"
INSTALL_DONE_MESSAGE = "{name} version {version} is installed at:\n{path}"
REPAIR_DONE_TITLE = "Repair complete"
REPAIR_DONE_MESSAGE = "{name} version {version} has been repaired at:\n{path}"
UNINSTALL_DONE_TITLE = "Uninstall complete"
UNINSTALL_DONE_MESSAGE = "{name} has been removed from:\n{path}"
FAILED_TITLE = "Operation failed"


class InstallerWindow(QMainWindow):
    """The installer window: a themed, state-aware lifecycle screen."""

    def __init__(self) -> None:
        super().__init__()
        self._windows = is_windows()
        self._snapshot = detect(app_version(), install_target())
        self._theme = DARK

        self.setWindowTitle(WINDOW_TITLE)
        self.setWindowIcon(app_icon())
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self._widgets: WindowWidgets = build_window(
            self, self._snapshot, windows=self._windows
        )
        self._build_chrome()
        self._runner = OperationRunner(self)
        self._wire()
        self._apply_theme(self._theme)
        self._show_installed_actions()

    # ------------------------------------------------------------- assembly

    def _build_chrome(self) -> None:
        """Create the toolbar actions and the status bar."""
        self._choose_dir_action = QAction(CHOOSE_DIR_LABEL, self)
        self._choose_dir_action.setStatusTip(CHOOSE_DIR_TIP)
        self._about_action = QAction(ABOUT_LABEL, self)
        self._about_action.setStatusTip(ABOUT_TIP)

        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.addAction(self._choose_dir_action)
        toolbar.addSeparator()
        toolbar.addAction(self._about_action)
        self.addToolBar(toolbar)

        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage(IDLE_STATUS)

    def _wire(self) -> None:
        """Connect every control to the action it performs."""
        widgets = self._widgets
        self._choose_dir_action.triggered.connect(self._on_choose_dir)
        self._about_action.triggered.connect(self._on_about)
        widgets.primary.clicked.connect(self._on_primary)
        widgets.repair.clicked.connect(self._on_repair)
        widgets.uninstall.clicked.connect(self._on_uninstall)
        widgets.light_button.clicked.connect(self._on_light_theme)
        widgets.dark_button.clicked.connect(self._on_dark_theme)
        widgets.autostart.toggled.connect(self._on_autostart_toggled)

    def _show_installed_actions(self) -> None:
        """Show Repair and Uninstall only when there is something to act on."""
        installed = self._snapshot.installed
        self._widgets.repair.setVisible(installed)
        self._widgets.uninstall.setVisible(installed)

    # ---------------------------------------------------------------- theme

    def _apply_theme(self, mode: str) -> None:
        """Apply a theme to the whole application and reflect it in the toggles."""
        app = QApplication.instance()
        if app is not None:
            self._theme = ThemeManager(app).apply(mode)
        is_dark = self._theme == DARK
        self._widgets.light_button.setChecked(not is_dark)
        self._widgets.dark_button.setChecked(is_dark)

    def _on_light_theme(self) -> None:
        """Switch to the light theme."""
        self._apply_theme(LIGHT)

    def _on_dark_theme(self) -> None:
        """Switch to the dark theme."""
        self._apply_theme(DARK)

    # -------------------------------------------------------------- actions

    def _on_about(self) -> None:
        """Open the bundled licence in a scrollable dialog."""
        LicenceDialog(licence_text(), self).exec()

    def _on_choose_dir(self) -> None:
        """Let the user pick a different base directory for the install."""
        chosen = QFileDialog.getExistingDirectory(
            self, CHOOSE_DIR_CAPTION, str(self._snapshot.install_dir.parent)
        )
        if not chosen:
            return
        self._snapshot = replace(self._snapshot, install_dir=Path(chosen) / APP_ID)
        self._relabel()

    def _on_autostart_toggled(self, enabled: bool) -> None:
        """Apply the sign-in choice at once when the app is already installed.

        Before an install there is no executable to point the Run entry at, so
        the choice is simply carried into the install that follows.
        """
        if not self._snapshot.installed:
            return
        set_autostart(enabled, installed_exe(self._snapshot.install_dir))

    def _ensure_app_closed(self) -> bool:
        """Return True when it is safe to proceed, offering to close the app."""
        if not is_app_running():
            return True
        if not confirm_close_running(self):
            return False
        try:
            close_running_app(install_dir=self._snapshot.install_dir)
        except InstallerError as error:
            show_error(self, FAILED_TITLE, str(error))
            return False
        return True

    def _on_primary(self) -> None:
        """Install, upgrade, reinstall or downgrade in one pass."""
        if not self._ensure_app_closed():
            return
        widgets = self._widgets
        options = InstallOptions(
            target_dir=self._snapshot.install_dir,
            desktop=widgets.desktop.isChecked(),
            start_menu=widgets.start_menu.isChecked(),
            autostart=widgets.autostart.isChecked(),
        )
        self._start(lambda report: install(options, progress=report), self._installed)

    def _on_repair(self) -> None:
        """Re-deploy the application files over the existing install."""
        if not self._installation_present():
            return
        if not self._ensure_app_closed():
            return
        location = self._snapshot.install_dir
        self._start(lambda report: repair(location, progress=report), self._repaired)

    def start_uninstall(self) -> None:
        """Begin the uninstall flow, as the registered UninstallString does."""
        self._on_uninstall()

    def _on_uninstall(self) -> None:
        """Confirm, then remove the application, its shortcuts and its entry."""
        if not self._installation_present():
            return
        version = self._snapshot.installed_version or self._snapshot.bundled_version
        if not confirm_uninstall(self, version, self._snapshot.install_dir):
            return
        if not self._ensure_app_closed():
            return
        location = self._snapshot.install_dir
        self._start(
            lambda report: uninstall(progress=report, install_dir=location),
            self._uninstalled,
        )

    def _installation_present(self) -> bool:
        """Report a missing installation rather than acting on a stale entry."""
        if self._snapshot.install_dir.exists():
            return True
        show_error(
            self,
            NOT_INSTALLED_TITLE,
            NOT_INSTALLED_MESSAGE.format(path=self._snapshot.install_dir),
        )
        return False

    # ------------------------------------------------------------- outcomes

    def _installed(self, result: object) -> None:
        """Report a completed install and launch the app when asked to."""
        exe_path = result if isinstance(result, Path) else None
        show_info(
            self,
            INSTALL_DONE_TITLE,
            INSTALL_DONE_MESSAGE.format(
                name=APP_DISPLAY_NAME,
                version=self._snapshot.bundled_version,
                path=self._snapshot.install_dir,
            ),
        )
        self._refresh()
        if exe_path is not None and self._widgets.launch_on_finish.isChecked():
            launch(exe_path)
            self.close()

    def _repaired(self, _result: object) -> None:
        """Report a completed repair."""
        show_info(
            self,
            REPAIR_DONE_TITLE,
            REPAIR_DONE_MESSAGE.format(
                name=APP_DISPLAY_NAME,
                version=self._snapshot.bundled_version,
                path=self._snapshot.install_dir,
            ),
        )
        self._refresh()

    def _uninstalled(self, _result: object) -> None:
        """Report a completed uninstall and return the window to its first state."""
        show_info(
            self,
            UNINSTALL_DONE_TITLE,
            UNINSTALL_DONE_MESSAGE.format(
                name=APP_DISPLAY_NAME, path=self._snapshot.install_dir
            ),
        )
        self._snapshot = replace(self._snapshot, state=InstallState.NOT_INSTALLED)
        self._relabel()

    # -------------------------------------------------------- worker plumbing

    def _start(self, operation, on_success) -> None:
        """Run one operation on a worker thread, showing progress while it runs."""
        self._set_busy(True)
        self._runner.start(
            operation,
            self._on_progress,
            lambda error, result: self._on_finished(error, result, on_success),
        )

    def _on_progress(self, pct: int, message: str) -> None:
        """Show the current phase and how far through it the operation is."""
        self._widgets.progress.setValue(pct)
        self._widgets.status.setText(message)
        self.statusBar().showMessage(message)

    def _on_finished(self, error: str, result: object, on_success) -> None:
        """Restore the window, then either report the failure or the success."""
        self._set_busy(False)
        if error:
            self._widgets.status.setText(error)
            show_error(self, FAILED_TITLE, error)
            return
        on_success(result)

    def _set_busy(self, busy: bool) -> None:
        """Disable the actions while work is running."""
        widgets = self._widgets
        widgets.progress.setValue(MINIMUM_PCT if busy else COMPLETE_PCT)
        self._choose_dir_action.setEnabled(not busy)
        for button in (widgets.primary, widgets.repair, widgets.uninstall):
            button.setEnabled(not busy)

    def _refresh(self) -> None:
        """Re-read the installed state and relabel the window to match it."""
        self._snapshot = detect(app_version(), self._snapshot.install_dir)
        self._relabel()

    def _relabel(self) -> None:
        """Reflect the current snapshot in every label and in what is shown."""
        widgets = self._widgets
        widgets.primary.setText(primary_label(self._snapshot))
        widgets.subtitle.setText(subtitle_text(self._snapshot))
        widgets.path_label.setText(
            INSTALL_PATH_TEXT.format(path=self._snapshot.install_dir)
        )
        self._show_installed_actions()
