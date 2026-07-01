#!/usr/bin/env python3
"""
PySide6-based installer UI for Elite: Dangerous Colonisation Assistant (EDCA).

Features:
- Cross-platform PySide6 GUI (Windows / macOS / Linux).
- Dark and light themes with a simple toggle.
- Main actions: Install, Repair, Uninstall.
- About dialog showing the LGPL-3 license text (read from INSTALLER_LICENSE in project root).
- Simple log area and status bar for feedback.

This script is intended to be run as a GUI application. It lives at
installer/app.py, is compiled by buildinstaller.py and expects that the
installer payload (the EDColonisationAsst project files) is located in a
known directory relative to the script, for example:

- When running from source:
    <project_root>/build/payload/  (staged by buildinstaller.py)
- When built as a compiled installer:
    a 'payload' directory placed alongside the compiled executable
    or this module file (see get_payload_root()).

By default, the installer:
- Installs into:
    - Windows:   %LOCALAPPDATA%\\EDColonisationAssistant
    - macOS:     ~/Applications/EDColonisationAssistant
    - Linux:     ~/.local/share/EDColonisationAssistant

Install/Repair both copy the payload into the chosen install directory
(overwriting existing files on Repair). Uninstall removes the install
directory after confirmation.
"""

import os
import shutil
import sys
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QIcon, QPalette, QColor, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QStatusBar,
    QFileDialog,
    QMessageBox,
    QToolBar,
    QCheckBox,
    QProgressBar,
    QSplashScreen,
    QDialog,
    QDialogButtonBox,
)

from css import DARK_QSS, LIGHT_QSS


APP_NAME = "Elite: Dangerous Colonisation Assistant"
APP_ID = "EDColonisationAssistant"
# Directory containing this module. In the compiled onefile installer this is
# the unpack directory where bundled data (payload/, VERSION, LICENSE) lives.
MODULE_DIR = Path(__file__).resolve().parent
# Repository root when running from source (this module lives in installer/).
# Used only as a last-resort fallback; bundled lookups anchor on MODULE_DIR.
PROJECT_ROOT = MODULE_DIR.parent
# Default relative payload directory when running from source.
DEFAULT_PAYLOAD_DIR = PROJECT_ROOT / "build" / "payload"
WINDOWS_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\EDColonisationAsst"
)

# Windows auto-start (per-user) registry Run key.
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_RUN_VALUE_NAME = "EDColonisationAsst"


def get_backend_version() -> str:
    """
    Determine the backend version.

    Priority:
    1. VERSION file bundled with the installer (next to this module or exe).
    2. VERSION file in the project root (dev mode).
    3. __version__ from backend/src/__init__.py in common layouts.
    4. Fallback to "0.0.0" if all else fails.
    """
    # --- 1) VERSION file (preferred, bundled by buildinstaller.py) ----
    version_candidates: list[Path] = []

    try:
        here = Path(__file__).resolve().parent
        version_candidates.append(here / "VERSION")
    except Exception:
        here = None  # type: ignore[assignment]

    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        if exe_dir != here:
            version_candidates.append(exe_dir / "VERSION")
    except Exception:
        pass

    version_candidates.append(PROJECT_ROOT / "VERSION")

    for path in version_candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if raw:
                return raw
        except Exception:
            continue

    # --- 2) Fallback: scan backend/src/__init__.py for __version__ --------
    init_candidates: list[Path] = []

    # Paths relative to the current module location (common for packaged builds).
    try:
        if here is None:
            here = Path(__file__).resolve().parent
        init_candidates.append(here / "payload" / "backend" / "src" / "__init__.py")
        init_candidates.append(here / "backend" / "src" / "__init__.py")
    except Exception:
        pass

    # Paths relative to the executable location (in case data is laid out there).
    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        init_candidates.append(exe_dir / "payload" / "backend" / "src" / "__init__.py")
    except Exception:
        pass

    # Source/dev layouts.
    init_candidates.append(DEFAULT_PAYLOAD_DIR / "backend" / "src" / "__init__.py")
    init_candidates.append(PROJECT_ROOT / "backend" / "src" / "__init__.py")

    seen: set[Path] = set()
    for init_py in init_candidates:
        if init_py in seen:
            continue
        seen.add(init_py)
        if not init_py.exists():
            continue
        try:
            text = init_py.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("__version__"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        return parts[1].strip().strip('"').strip("'")
        except Exception:
            continue

    return "0.0.0"


def get_default_install_dir() -> Path:
    """Return a sensible default install directory based on OS.

    On Windows we deliberately choose a user-writable location under
    %LOCALAPPDATA% so that elevation is not required to install or run
    the application for a standard (non-administrator) user account.
    """
    if sys.platform.startswith("win"):
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            # Fallbacks in case LOCALAPPDATA is not defined for some reason.
            appdata = os.environ.get("APPDATA")
            if appdata:
                base = Path(appdata).parent  # typically ...\AppData
            else:
                base = Path.home() / "AppData" / "Local"
        else:
            base = Path(local_appdata)
        return base / APP_ID
    elif sys.platform == "darwin":
        return Path.home() / "Applications" / APP_ID
    else:
        # Linux / other Unix
        return Path.home() / ".local" / "share" / APP_ID


def get_payload_root() -> Optional[Path]:
    """
    Determine where the installer payload lives.

    In order of preference:

    1. When running from a compiled installer:
       a "payload" directory next to the executable or this module file.
    2. When running from source:
       DEFAULT_PAYLOAD_DIR (build_payload/) if non-empty,
       otherwise PROJECT_ROOT.
    """
    candidates: list[Path] = []

    # Compiled installer (onefile / standalone): payload directory next to exe
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent / "payload")
    except Exception:
        pass

    # Or next to this module file
    try:
        candidates.append(Path(__file__).resolve().parent / "payload")
    except Exception:
        pass

    for path in candidates:
        if path.exists():
            return path

    # Source mode: prefer build_payload/
    payload_root = DEFAULT_PAYLOAD_DIR
    if payload_root.exists():
        try:
            if any(payload_root.iterdir()):
                return payload_root
        except Exception:
            pass

    # Fallback: project root
    if PROJECT_ROOT.exists():
        return PROJECT_ROOT

    return None


def _reflow_license_body(text: str, width: int = 75) -> str:
    """
    Reflow the plain-text LICENSE body so that paragraphs use wider lines.

    The raw LGPL text is formatted for an ~80-column console. For a wide,
    scrollable dialog we join intra-paragraph line breaks and let Qt re-wrap
    to a larger width, while preserving blank lines between paragraphs.
    """
    import textwrap

    paragraphs = text.split("\n\n")
    reflowed: list[str] = []

    for para in paragraphs:
        lines = [ln.rstrip() for ln in para.splitlines()]
        if not any(lines):
            # Preserve empty paragraphs exactly
            reflowed.append("")
            continue

        # If this paragraph looks like a block with significant indentation
        # (e.g. code blocks), keep its internal line breaks.
        if any(ln.startswith("    ") or ln.startswith("\t") for ln in lines):
            reflowed.append("\n".join(lines))
            continue

        # Normal paragraph: join lines and re-wrap to the requested width.
        joined = " ".join(ln.strip() for ln in lines)
        reflowed.append(textwrap.fill(joined, width=width))

    return "\n\n".join(reflowed)


def read_license_text() -> str:
    """Read LICENSE file (GPL-3) from bundled resources or project root.

    When running as a compiled installer or main app, LICENSE is expected to
    live next to the binaries. When running from source, we fall back to
    PROJECT_ROOT / 'LICENSE'. If all lookups fail, we show a URL instead.
    """
    header = "GNU General Public License v3 (GPL-3.0)\n\n"

    candidate_paths: list[Path] = []

    # Compiled build: look next to this module file
    try:
        candidate_paths.append(Path(__file__).resolve().parent / "LICENSE")
    except Exception:
        pass

    # Fallback: repository root (source mode)
    candidate_paths.append(PROJECT_ROOT / "LICENSE")

    for license_path in candidate_paths:
        if license_path.exists():
            try:
                raw = license_path.read_text(encoding="utf-8")
                return header + _reflow_license_body(raw)
            except Exception as exc:
                return (
                    header
                    + f"Could not read LICENSE file at {license_path}:\n{exc}\n\n"
                    "Please see: https://www.gnu.org/licenses/lgpl-3.0.html"
                )

    return (
        header + "LICENSE file not found in bundled resources or project root.\n\n"
        "Please see: https://www.gnu.org/licenses/lgpl-3.0.html"
    )


# --------------------------------------------------------------------------- QSS
# Dark and light theme QSS are defined in css.DARK_QSS / css.LIGHT_QSS.


class ThemeManager:
    """Encapsulates installer theme palettes and application of QSS."""

    def __init__(self, app: QApplication) -> None:
        self._app = app

    @staticmethod
    def dark_palette() -> QPalette:
        """Return a dark palette tuned to the purple/orange theme."""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(21, 16, 32))  # main background
        palette.setColor(QPalette.WindowText, QColor(245, 245, 247))  # text
        palette.setColor(QPalette.Base, QColor(28, 20, 42))  # text edit bg
        palette.setColor(QPalette.AlternateBase, QColor(35, 26, 52))
        palette.setColor(QPalette.ToolTipBase, QColor(45, 37, 80))
        palette.setColor(QPalette.ToolTipText, QColor(245, 245, 247))
        palette.setColor(QPalette.Text, QColor(245, 245, 247))
        palette.setColor(QPalette.Button, QColor(45, 37, 80))
        palette.setColor(QPalette.ButtonText, QColor(245, 245, 247))
        palette.setColor(QPalette.Highlight, QColor(255, 159, 28))  # orange accent
        palette.setColor(QPalette.HighlightedText, Qt.black)
        return palette

    def apply(self, mode: str) -> str:
        """Apply the requested theme mode to the application and return the mode."""
        if mode == "dark":
            # Purple/orange dark theme.
            self._app.setPalette(self.dark_palette())
            self._app.setStyle("Fusion")
            self._app.setStyleSheet(DARK_QSS)
        else:
            # Light blue / light orange theme.
            self._app.setPalette(QApplication.style().standardPalette())
            self._app.setStyle("Fusion")
            self._app.setStyleSheet(LIGHT_QSS)
        return mode


class InstallerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.version = get_backend_version()
        self.install_dir: Path = get_default_install_dir()

        # On Windows, prefer any previously-registered install location
        # only if it is not under a Program Files directory. This avoids
        # defaulting back to an admin-only location on systems where a
        # prior install lived in C:\Program Files but the current user
        # does not have elevation rights.
        if sys.platform.startswith("win"):
            existing = _windows_get_install_location()
            if existing is not None and not _is_under_program_files(existing):
                self.install_dir = existing

        # Installed version information (from HKCU uninstall key) and its
        # relationship to the installer version:
        #   -1 => installed older than this installer
        #    0 => same version
        #    1 => installed newer than this installer
        self.installed_version: str | None = None
        self._version_cmp: int | None = None

        if sys.platform.startswith("win"):
            installed_version = _windows_get_installed_version()
            if installed_version:
                self.installed_version = installed_version
                self._version_cmp = _compare_versions(installed_version, self.version)

        self.current_theme = "dark"  # start in dark mode by default
        self.total_files: int = 0
        self.copied_files: int = 0

        self.setWindowTitle(f"{APP_NAME} Installer")
        self.resize(780, 520)

        self._create_actions()
        self._create_toolbar()
        self._create_central_widget()
        self._create_status_bar()
        self._apply_theme(self.current_theme)

        self._log(f"{APP_NAME} Installer v{self.version}")
        self._log(f"Default install directory: {self.install_dir}")
        self._refresh_versions_and_buttons()

    # ------------------------------------------------------------------ UI setup

    def _create_actions(self) -> None:
        self.install_action = QAction("Install", self)
        self.install_action.setStatusTip("Install the application")
        self.install_action.triggered.connect(self.on_install_clicked)

        self.repair_action = QAction("Repair", self)
        self.repair_action.setStatusTip("Re-install files into the existing directory")
        self.repair_action.triggered.connect(self.on_repair_clicked)

        self.uninstall_action = QAction("Uninstall", self)
        self.uninstall_action.setStatusTip("Remove the installed application")
        self.uninstall_action.triggered.connect(self.on_uninstall_clicked)

        self.about_action = QAction("About / License", self)
        self.about_action.setStatusTip("Show LGPL-3 license information")
        self.about_action.triggered.connect(self.on_about_clicked)

        self.choose_dir_action = QAction("Change Install Location", self)
        self.choose_dir_action.setStatusTip("Choose a different installation folder")
        self.choose_dir_action.triggered.connect(self.on_choose_install_dir)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # Only non-obsolete actions in the toolbar
        toolbar.addAction(self.choose_dir_action)
        toolbar.addSeparator()
        toolbar.addAction(self.about_action)

    def _create_central_widget(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title_label = QLabel(f"{APP_NAME} Installer", self)
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.subtitle_label = QLabel("", self)
        self.subtitle_label.setWordWrap(True)

        # Header row: title/subtitle on the left, theme emoji buttons on the right
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.addWidget(title_label)
        header_text_layout.addWidget(self.subtitle_label)

        # Theme switch: emoji buttons mirroring the main app header (☀️ / 🌙)
        theme_row = QHBoxLayout()
        theme_row.setSpacing(6)

        self.light_button = QPushButton("☀️", self)
        self.light_button.setObjectName("lightThemeButton")
        self.light_button.setCheckable(True)
        self.light_button.setFixedSize(32, 32)
        self.light_button.setToolTip("Switch to light mode")
        self.light_button.clicked.connect(self.on_light_theme_clicked)

        self.dark_button = QPushButton("🌙", self)
        self.dark_button.setObjectName("darkThemeButton")
        self.dark_button.setCheckable(True)
        self.dark_button.setFixedSize(32, 32)
        self.dark_button.setToolTip("Switch to dark mode")
        self.dark_button.clicked.connect(self.on_dark_theme_clicked)

        theme_row.addWidget(self.light_button)
        theme_row.addWidget(self.dark_button)

        # Place header text on the left, toggle row on the far right
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()
        header_layout.addLayout(theme_row)

        layout.addLayout(header_layout)

        # Buttons column (Install / Repair / Uninstall) stacked vertically
        buttons_row = QVBoxLayout()
        buttons_row.setSpacing(8)

        # Give the primary buttons stable object names so QSS can style them
        self.install_button = QPushButton("Install")
        self.install_button.setObjectName("installButton")
        self.install_button.setMinimumHeight(40)
        self.install_button.clicked.connect(self.on_install_clicked)

        self.repair_button = QPushButton("Repair")
        self.repair_button.setObjectName("repairButton")
        self.repair_button.setMinimumHeight(40)
        self.repair_button.clicked.connect(self.on_repair_clicked)

        self.uninstall_button = QPushButton("Uninstall")
        self.uninstall_button.setObjectName("uninstallButton")
        self.uninstall_button.setMinimumHeight(40)
        self.uninstall_button.clicked.connect(self.on_uninstall_clicked)

        buttons_row.addWidget(self.install_button)
        buttons_row.addWidget(self.repair_button)
        buttons_row.addWidget(self.uninstall_button)

        layout.addLayout(buttons_row)

        # Install dir info
        self.install_dir_label = QLabel(f"Install directory:\n{self.install_dir}", self)
        self.install_dir_label.setWordWrap(True)
        self.install_dir_label.setStyleSheet("font-size: 11px;")

        layout.addWidget(self.install_dir_label)

        # Windows-only options: desktop shortcut / start menu integration / auto-start
        self.desktop_shortcut_checkbox = QCheckBox("Create Desktop shortcut", self)
        self.start_menu_checkbox = QCheckBox("Add Start Menu entry", self)
        self.autostart_checkbox = QCheckBox(
            "Start EDCA automatically when I sign in (system tray)",
            self,
        )

        if sys.platform.startswith("win"):
            # Enabled and checked by default on Windows
            self.desktop_shortcut_checkbox.setChecked(True)
            self.start_menu_checkbox.setChecked(True)
            # Default to off to avoid surprising users.
            self.autostart_checkbox.setChecked(False)
        else:
            # Non-Windows platforms: disable and uncheck
            self.desktop_shortcut_checkbox.setChecked(False)
            self.desktop_shortcut_checkbox.setEnabled(False)
            self.start_menu_checkbox.setChecked(False)
            self.start_menu_checkbox.setEnabled(False)

            self.autostart_checkbox.setChecked(False)
            self.autostart_checkbox.setEnabled(False)

        options_layout = QVBoxLayout()
        options_layout.setSpacing(2)
        options_layout.addWidget(self.desktop_shortcut_checkbox)
        options_layout.addWidget(self.start_menu_checkbox)
        options_layout.addWidget(self.autostart_checkbox)

        layout.addLayout(options_layout)

        # Progress bar for install / repair operations
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Idle")
        self.progress_bar.setMinimumHeight(18)
        layout.addWidget(self.progress_bar)

        # Hidden log area kept for debugging but not shown in the UI
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(120)
        self.log_view.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 11px;"
        )
        self.log_view.hide()

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _create_status_bar(self) -> None:
        status = QStatusBar(self)
        self.setStatusBar(status)
        status.showMessage("Ready")

    def _update_version_labels(self) -> None:
        """Update header subtitle with installer and installed version information."""
        if self.installed_version:
            text = (
                f"Installer version {self.version} · "
                f"Installed version {self.installed_version} at {self.install_dir}"
            )
        else:
            text = (
                f"Installer version {self.version} · "
                "No existing installation detected"
            )
        self.subtitle_label.setText(text)

    def _refresh_versions_and_buttons(self) -> None:
        """Refresh version labels and action button enabled states."""
        self._update_version_labels()

        has_installed = self.installed_version is not None and self.install_dir.exists()

        # Install is always available.
        self.install_button.setEnabled(True)

        # Repair is only meaningful when something is installed.
        self.repair_button.setEnabled(bool(has_installed))

    # ------------------------------------------------------------------ theme

    def _apply_theme(self, mode: str) -> None:
        app = QApplication.instance()
        if app is None:
            return

        theme_manager = ThemeManager(app)
        self.current_theme = theme_manager.apply(mode)
        self._log(f"Switched to {self.current_theme} theme")
        self._update_theme_buttons()

    def _update_theme_buttons(self) -> None:
        """Update the emoji theme buttons to reflect the current theme."""
        light_btn = getattr(self, "light_button", None)
        dark_btn = getattr(self, "dark_button", None)
        if light_btn is None or dark_btn is None:
            return
        is_dark = self.current_theme == "dark"
        light_btn.setChecked(not is_dark)
        dark_btn.setChecked(is_dark)

    @Slot()
    def on_light_theme_clicked(self) -> None:
        if self.current_theme != "light":
            self._apply_theme("light")

    @Slot()
    def on_dark_theme_clicked(self) -> None:
        if self.current_theme != "dark":
            self._apply_theme("dark")

    # ------------------------------------------------------------------ actions

    def _log(self, msg: str) -> None:
        """Append a message to the log view, persist to file, and keep the UI responsive."""
        # In-UI log
        self.log_view.append(msg)
        self.log_view.ensureCursorVisible()
        self.statusBar().showMessage(msg, 5000)

        # File log (next to the executable when compiled, otherwise in project root)
        try:
            base_dir = Path(sys.argv[0]).resolve().parent
        except Exception:
            base_dir = PROJECT_ROOT

        log_path = base_dir / "guiinstaller.log"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            # Logging failure should never break the UI
            pass

        # Make sure the UI repaints promptly even during longer operations
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    @Slot()
    def on_choose_install_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        initial = str(self.install_dir.parent)
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Choose installation directory",
            initial,
        )
        if chosen:
            # We still append APP_ID so the chosen directory is a base.
            self.install_dir = Path(chosen) / APP_ID
            self.install_dir_label.setText(f"Install directory:\n{self.install_dir}")
            self._log(f"Install directory set to: {self.install_dir}")

    def _confirm(self, title: str, text: str) -> bool:
        res = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return res == QMessageBox.Yes

    def _show_error(self, title: str, text: str) -> None:
        self._log(f"ERROR: {text}")
        QMessageBox.critical(self, title, text)

    def _show_info(self, title: str, text: str) -> None:
        self._log(text)
        QMessageBox.information(self, title, text)

    @Slot()
    def on_install_clicked(self) -> None:
        """Handle Install button click."""
        # Prevent changing the install location while an operation is in progress.
        self.choose_dir_action.setEnabled(False)
        try:
            self._log("Starting installation...")

            # If an older version is installed, ask whether to uninstall it first.
            if self.installed_version is not None and self._version_cmp == -1:
                if not self._confirm(
                    "Existing installation detected",
                    (
                        f"A previous version ({self.installed_version}) is installed at:\n"
                        f"{self.install_dir}\n\n"
                        f"To install version {self.version}, the old version should be "
                        "uninstalled first.\n\n"
                        "Do you want to uninstall the old version now?"
                    ),
                ):
                    self._log(
                        "Installation cancelled; user chose not to uninstall the "
                        f"older version {self.installed_version}."
                    )
                    return

                # Perform uninstall as if the Uninstall button had been clicked,
                # but without prompting the user a second time.
                self._perform_uninstall(confirm=False)
                self._log(
                    "Old version removed at user's request via Install; "
                    "no new installation started automatically."
                )
                return

            payload_root = get_payload_root()
            if payload_root is None:
                self._show_error(
                    "Payload not found",
                    "Could not locate the installer payload.\n"
                    "Make sure the payload directory exists or you are running a packaged installer.",
                )
                return

            self._log(f"Installing from payload: {payload_root}")
            if not self.install_dir.exists():
                self.install_dir.mkdir(parents=True, exist_ok=True)

            total_files = self._count_files(payload_root)
            self._prepare_progress(total_files, "Installing")

            self._copy_tree(payload_root, self.install_dir)

            # Windows-only: create shortcuts and register in Add/Remove Programs
            if sys.platform.startswith("win"):
                self._create_windows_shortcuts()
                self._apply_windows_autostart_setting()
                self._register_windows_app()

            self._finish_progress("Installation complete")
            self.installed_version = self.version
            self._version_cmp = 0
            self._refresh_versions_and_buttons()
            self._show_info(
                "Installation complete",
                f"{APP_NAME} version {self.version} has been installed to:\n{self.install_dir}",
            )
        except Exception as exc:
            self._finish_progress("Install failed")
            self._show_error(
                "Install failed", f"Unexpected error during install:\n{exc}"
            )
        finally:
            # Re-enable location changes once the operation is finished.
            self.choose_dir_action.setEnabled(True)

    @Slot()
    def on_repair_clicked(self) -> None:
        """Handle Repair button click."""
        # Prevent changing the install location while an operation is in progress.
        self.choose_dir_action.setEnabled(False)
        try:
            self._log("Starting repair...")
            if not self.install_dir.exists():
                self._show_error(
                    "Not installed",
                    f"No existing installation found at:\n{self.install_dir}\n\n"
                    "Run Install first.",
                )
                return
            payload_root = get_payload_root()
            if payload_root is None:
                self._show_error(
                    "Payload not found",
                    "Could not locate the installer payload for repair.",
                )
                return

            # Provide informational messaging when repairing across version
            # boundaries, but do not block the repair.
            if self.installed_version is not None and self._version_cmp is not None:
                if self._version_cmp == -1:
                    self._show_info(
                        "Repairing older installation",
                        (
                            f"Repair will copy files for installer version {self.version} "
                            f"over the existing installation (currently version "
                            f"{self.installed_version})."
                        ),
                    )
                elif self._version_cmp == 1:
                    self._show_info(
                        "Repair may downgrade",
                        (
                            f"Repair will copy files for installer version {self.version} "
                            f"over an installation that reports version "
                            f"{self.installed_version}. This may effectively "
                            "downgrade some files."
                        ),
                    )

            self._log(
                f"Repairing installation at {self.install_dir} from {payload_root}"
            )

            total_files = self._count_files(payload_root)
            self._prepare_progress(total_files, "Repairing")

            self._copy_tree(payload_root, self.install_dir)

            # Windows-only: (re)create shortcuts if requested
            if sys.platform.startswith("win"):
                self._create_windows_shortcuts()
                self._apply_windows_autostart_setting()

            self._finish_progress("Repair complete")
            self.installed_version = self.version
            self._version_cmp = 0
            self._refresh_versions_and_buttons()
            self._show_info(
                "Repair complete",
                f"{APP_NAME} version {self.version} has been repaired at:\n{self.install_dir}",
            )
        except Exception as exc:
            self._finish_progress("Repair failed")
            self._show_error("Repair failed", f"Unexpected error during repair:\n{exc}")
        finally:
            # Re-enable location changes once the operation is finished.
            self.choose_dir_action.setEnabled(True)

    @Slot()
    def on_uninstall_clicked(self) -> None:
        """Handle Uninstall button click."""
        # Prevent changing the install location while an operation is in progress.
        self.choose_dir_action.setEnabled(False)
        try:
            self._perform_uninstall(confirm=True)
        except Exception as exc:
            self._finish_progress("Uninstall failed")
            self._show_error(
                "Uninstall failed",
                f"Unexpected error during uninstall:\n{exc}",
            )
        finally:
            # Re-enable location changes once the operation is finished.
            self.choose_dir_action.setEnabled(True)

    @Slot()
    def on_about_clicked(self) -> None:
        """
        Show the LGPL license / About dialog.

        Use a wider, scrollable dialog instead of a tall message box so that
        the full license text remains usable on typical displays.
        """
        text = read_license_text()

        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {APP_NAME}")

        layout = QVBoxLayout(dialog)

        text_edit = QTextEdit(dialog)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(text_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        # Make the license dialog narrow enough that the text column closely
        # matches the window width with minimal right-side whitespace.
        dialog.resize(480, 650)
        dialog.exec()

    # ------------------------------------------------------------------ copying

    def _count_files(self, root: Path) -> int:
        """Count the total number of files under root for progress reporting."""
        count = 0
        for _, _, files in os.walk(root):
            count += len(files)
        return count

    def _prepare_progress(self, total_files: int, label: str) -> None:
        """Initialise the progress bar for an operation."""
        self.total_files = total_files
        self.copied_files = 0

        if total_files <= 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"{label} (no files)")
        else:
            self.progress_bar.setRange(0, total_files)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"{label} (%p%)")

    def _update_progress(self) -> None:
        """Advance the progress bar by one file."""
        if self.total_files <= 0:
            return
        self.copied_files += 1
        self.progress_bar.setValue(self.copied_files)
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def _finish_progress(self, label: str) -> None:
        """Set the progress bar to 100% with a final label."""
        if self.total_files > 0:
            self.progress_bar.setValue(self.total_files)
        self.progress_bar.setFormat(label)

    def _copy_tree(self, src: Path, dst: Path) -> None:
        """
        Copy src tree into dst, overwriting existing files, updating progress only.

        Additionally:
        - Skip known development / VCS / cache directories if encountered
          (e.g. when running directly from a project root rather than a
          curated payload tree).
        - Restore renamed Python sources shipped as ``*.py_`` in the payload
          back to real ``*.py`` files in the install directory. This pairs
          with the renaming performed in buildinstaller._ensure_payload_dir().
        """
        # These directory names are never needed at runtime and should not be
        # installed even if the payload root accidentally points at a repo
        # checkout instead of a curated payload tree.
        ignore_dir_names = {
            ".git",
            ".venv",
            ".benchmarks",
            "htmlcov",
            ".pytest_cache",
            "__pycache__",
            "tests",
        }

        for root, dirs, files in os.walk(src):
            # Prune unwanted directories from traversal.
            dirs[:] = [d for d in dirs if d not in ignore_dir_names]

            rel_root = Path(root).relative_to(src)
            target_root = dst / rel_root
            target_root.mkdir(parents=True, exist_ok=True)

            for name in files:
                s = Path(root) / name

                # If this is a renamed Python source from the payload
                # (e.g. "main.py_"), restore the original ".py" extension
                # in the installed tree.
                if name.endswith(".py_"):
                    dest_name = name[:-1]  # strip the trailing underscore
                else:
                    dest_name = name

                d = target_root / dest_name
                try:
                    shutil.copy2(s, d)
                    self._update_progress()
                except Exception as exc:
                    self._log(f"Failed to copy {s} -> {d}: {exc}")

    def _delete_tree(self, root: Path) -> None:
        """
        Recursively delete the installation directory with progress updates.

        This keeps the UI responsive during uninstall and avoids the blocking
        behaviour of a single shutil.rmtree() call, especially on large
        installations.
        """
        if not root.exists():
            return

        # Walk bottom-up so that we can remove files before their parent dirs.
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            base = Path(dirpath)

            # Delete files first
            for name in filenames:
                p = base / name
                try:
                    if p.exists():
                        p.unlink()
                    self._update_progress()
                except Exception as exc:
                    self._log(f"Failed to delete file {p}: {exc}")

            # Then delete subdirectories
            for name in dirnames:
                d = base / name
                try:
                    if d.exists():
                        d.rmdir()
                except Exception as exc:
                    self._log(f"Failed to delete directory {d}: {exc}")

        # Finally remove the root directory itself
        try:
            if root.exists():
                root.rmdir()
        except Exception as exc:
            self._log(f"Failed to delete install root {root}: {exc}")

    def _perform_uninstall(self, confirm: bool = True) -> None:
        """
        Core uninstall logic shared by the Uninstall button and the
        Install-based upgrade flow.

        If confirm is True, a confirmation dialog is shown before files
        are removed. When invoked from on_install_clicked during an
        upgrade, confirm is False so that the user is not prompted twice.
        """
        self._log("Starting uninstall...")

        # Best-effort attempt to stop a running tray controller before
        # removing files, to avoid "files in use" issues on Windows.
        self._stop_running_tray()

        if not self.install_dir.exists():
            self._finish_progress("Uninstall failed")
            self._show_error(
                "Not installed",
                f"No existing installation found at:\n{self.install_dir}",
            )
            return

        # Count files in the install directory so the progress bar shows a
        # meaningful label instead of "(no files)".
        total_files = self._count_files(self.install_dir)
        if total_files <= 0:
            # At least show a 0→100% transition even if no files were
            # counted (e.g. empty directory or permission issues).
            total_files = 1
        self._prepare_progress(total_files, "Uninstalling")

        installed_version = self.installed_version or "previously installed"

        if confirm:
            if not self._confirm(
                "Confirm uninstall",
                (
                    f"Are you sure you want to remove {APP_NAME} version "
                    f"{installed_version} from:\n{self.install_dir}?"
                ),
            ):
                self._finish_progress("Uninstall cancelled")
                return

        # Delete files with progress updates so the UI remains responsive.
        self._delete_tree(self.install_dir)

        # Windows-only: remove shortcuts and unregister Add/Remove entry
        if sys.platform.startswith("win"):
            self._remove_windows_shortcuts()
            self._set_windows_autostart_enabled(False)
            self._unregister_windows_app()

        # Clear installed-version state and refresh UI.
        self.installed_version = None
        self._version_cmp = None

        self._finish_progress("Uninstall complete")
        self._refresh_versions_and_buttons()
        self._show_info(
            "Uninstall complete",
            f"{APP_NAME} version {installed_version} has been removed from:\n{self.install_dir}",
        )

    # ------------------------------------------------------------------ Windows autostart

    def _apply_windows_autostart_setting(self) -> None:
        """Apply the user's chosen auto-start preference (Windows only)."""
        if not sys.platform.startswith("win"):
            return
        enabled = bool(getattr(self, "autostart_checkbox", None) and self.autostart_checkbox.isChecked())
        self._set_windows_autostart_enabled(enabled)

    def _set_windows_autostart_enabled(self, enabled: bool) -> None:
        r"""Enable/disable per-user auto-start via HKCU\...\Run on Windows."""
        if not sys.platform.startswith("win"):
            return

        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            self._log("winreg not available; cannot configure auto-start.")
            return

        # Target the installed runtime EXE. Pass --no-browser so that login start
        # does not pop a browser window.
        runtime_exe = self.install_dir / "EDColonisationAsst.exe"
        cmd = f'"{runtime_exe}" --no-browser'

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                WINDOWS_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, WINDOWS_RUN_VALUE_NAME, 0, winreg.REG_SZ, cmd)
                    self._log("Enabled auto-start on login (system tray).")
                else:
                    try:
                        winreg.DeleteValue(key, WINDOWS_RUN_VALUE_NAME)
                    except FileNotFoundError:
                        pass
                    self._log("Disabled auto-start on login.")
        except Exception as exc:
            self._log(f"Failed to configure auto-start on login: {exc}")

    def _stop_running_tray(self) -> None:
        """
        Attempt to stop any running EDCA tray/runtime process before uninstalling.

        Legacy behaviour:
        - If a PID file 'tray.pid' exists under the install directory (created
          by the older tray_app.py controller), we read the PID and call
          'taskkill /PID <pid> /T /F' on Windows.

        New behaviour:
        - Regardless of whether a PID file exists, we also issue a best-effort
          'taskkill /IM "EDColonisationAsst.exe" /T /F' so that the packaged
          runtime executable (which hosts the new tray in-process) is stopped
          before we start deleting files. This avoids leaving a ghost tray icon
          running after uninstall via Add/Remove Programs.
        """
        # First, try the legacy PID-based tray controller if present.
        pid_file = self.install_dir / "tray.pid"
        if pid_file.exists():
            try:
                raw = pid_file.read_text(encoding="utf-8").strip()
                if raw:
                    pid = int(raw)
                else:
                    pid = None
            except Exception:
                pid = None

            if pid is not None and sys.platform.startswith("win"):
                try:
                    # Run taskkill in a hidden console window so uninstall does not
                    # flash a black cmd window.
                    CREATE_NO_WINDOW = 0x08000000
                    startup_info = subprocess.STARTUPINFO()
                    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW,
                        startupinfo=startup_info,
                    )
                except Exception:
                    # Failing to kill the legacy tray should not abort uninstall.
                    pass

        # Additionally, always try to kill any running packaged runtime EXE so
        # that the new in-process tray hosted by EDColonisationAsst.exe is
        # terminated cleanly before we start removing files.
        if sys.platform.startswith("win"):
            try:
                CREATE_NO_WINDOW = 0x08000000
                startup_info = subprocess.STARTUPINFO()
                startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                subprocess.run(
                    ["taskkill", "/IM", "EDColonisationAsst.exe", "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                    startupinfo=startup_info,
                )
            except Exception:
                # As above, failure to kill should not block uninstall; worst
                # case, Windows will still allow the user to exit the tray
                # manually.
                pass

    # ------------------------------------------------------------------ Windows shortcuts

    def _windows_shortcut_paths(self) -> tuple[Path, Path]:
        """
        Return (desktop_shortcut, start_menu_shortcut) paths on Windows.
        """
        shortcut_name = "EDColonisationAsst.lnk"

        # Desktop
        user_profile = os.environ.get("USERPROFILE") or str(Path.home())
        desktop_dir = Path(user_profile) / "Desktop"
        desktop_shortcut = desktop_dir / shortcut_name

        # Start Menu
        appdata = os.environ.get("APPDATA", "")
        start_menu_root = (
            Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
        start_menu_dir = start_menu_root / "EDColonisationAsst"
        start_menu_shortcut = start_menu_dir / shortcut_name

        return desktop_shortcut, start_menu_shortcut

    def _create_windows_shortcuts(self) -> None:
        """
        Create Desktop and/or Start Menu shortcuts on Windows,
        based on the current checkbox states.

        Shortcut strategy for the installed app:

        - Shortcuts point directly at the packaged runtime EXE
          (EDColonisationAsst.exe) in the install directory.
        - No batch files or VBScript launchers are used at runtime.
        - The shortcut icon is always EDColonisationAsst.ico from the install
          directory, so the user never sees a Python icon for the app.
        """
        if not sys.platform.startswith("win"):
            return

        runtime_exe = self.install_dir / "EDColonisationAsst.exe"
        self._log(f"Shortcut creation using install dir: {self.install_dir}")
        self._log(f"Expected runtime EXE at: {runtime_exe}")

        # In theory the runtime EXE should always have been copied from the
        # payload into the install directory by _copy_tree(). However, Nuitka's
        # onefile packaging can treat executables differently inside data
        # directories. We therefore embed EDColonisationAsst.exe explicitly as a
        # data file under a dedicated "runtime/" directory in the bundle (see
        # buildinstaller.build_installer) and recover from there if needed.
        if not runtime_exe.exists():
            # 1) Prefer the dedicated runtime/ directory next to the extracted
            #    installer module. In onefile builds, __file__ points at the
            #    extraction directory that also contains data files such as
            #    "runtime/EDColonisationAsst.exe".
            runtime_candidates: list[Path] = []
            try:
                runtime_candidates.append(
                    Path(__file__).resolve().parent
                    / "runtime"
                    / "EDColonisationAsst.exe"
                )
            except Exception:
                pass

            # 2) Also consider a runtime/ directory next to the executable path
            #    as a fallback, in case Nuitka lays out data relative to the stub
            #    exe instead of the module file.
            try:
                runtime_candidates.append(
                    Path(sys.argv[0]).resolve().parent
                    / "runtime"
                    / "EDColonisationAsst.exe"
                )
            except Exception:
                pass

            recovered = False
            for candidate in runtime_candidates:
                self._log(f"Runtime EXE missing; probing runtime data at: {candidate}")
                if candidate.exists():
                    try:
                        shutil.copy2(candidate, runtime_exe)
                        self._log(
                            "Recovered runtime EXE into install directory from "
                            f"runtime data: {candidate} -> {runtime_exe}"
                        )
                        recovered = True
                        break
                    except Exception as exc:
                        self._log(
                            "Failed to copy runtime EXE from runtime data into "
                            f"install directory: {exc}"
                        )

            # 3) Final fallback: try the payload/ tree (older installers that
            #    happened to keep the EXE inside payload before we introduced
            #    the dedicated runtime/ embedding).
            if not recovered:
                payload_root = get_payload_root()
                if payload_root is not None:
                    candidate = payload_root / "EDColonisationAsst.exe"
                    self._log(
                        f"Runtime EXE still missing; probing payload at: {candidate}"
                    )
                    if candidate.exists():
                        try:
                            shutil.copy2(candidate, runtime_exe)
                            self._log(
                                "Recovered runtime EXE into install directory "
                                f"from payload: {candidate} -> {runtime_exe}"
                            )
                            recovered = True
                        except Exception as exc:
                            self._log(
                                "Failed to copy runtime EXE from payload into "
                                f"install directory: {exc}"
                            )
                    else:
                        self._log(
                            "Runtime EXE not found in payload either; cannot "
                            "recover EDColonisationAsst.exe for shortcuts."
                        )

        if not runtime_exe.exists():
            self._log(
                "Runtime EXE not found in install directory after all recovery "
                "attempts; skipping shortcut creation."
            )
            return

        target = runtime_exe
        self._log(f"Using runtime EXE for shortcuts: {target}")

        icon = self.install_dir / "EDColonisationAsst.ico"
        if not icon.exists():
            # Fallback so the shortcut still has *some* icon even if the ICO
            # went missing for any reason.
            icon = runtime_exe if runtime_exe.exists() else target

        if not target.exists():
            self._log(f"Shortcut target does not exist: {target}")
            return

        desktop_shortcut, start_menu_shortcut = self._windows_shortcut_paths()

        if self.desktop_shortcut_checkbox.isChecked():
            self._create_single_shortcut(desktop_shortcut, target, icon)

        if self.start_menu_checkbox.isChecked():
            # Ensure the Start Menu subfolder exists
            start_menu_shortcut.parent.mkdir(parents=True, exist_ok=True)
            self._create_single_shortcut(start_menu_shortcut, target, icon)

    def _create_single_shortcut(
        self, shortcut_path: Path, target: Path, icon: Path
    ) -> None:
        """
        Create a single .lnk shortcut using PowerShell + WScript.Shell COM.

        The shortcut points directly at the packaged runtime EXE so that the
        app starts without any intermediate batch or VBScript launcher.
        """
        try:
            shortcut_path.parent.mkdir(parents=True, exist_ok=True)
            target_s = str(target)
            icon_s = str(icon)
            working_dir_s = str(target.parent)
            shortcut_s = str(shortcut_path)

            # Escape single quotes for PowerShell literal strings
            def esc(s: str) -> str:
                return s.replace("'", "''")

            ps_command = (
                "$shell = New-Object -ComObject WScript.Shell;"
                f"$shortcut = $shell.CreateShortcut('{esc(shortcut_s)}');"
                f"$shortcut.TargetPath = '{esc(target_s)}';"
                f"$shortcut.WorkingDirectory = '{esc(working_dir_s)}';"
                f"$shortcut.IconLocation = '{esc(icon_s)},0';"
                "$shortcut.Save();"
            )

            # Run PowerShell without showing a console window during
            # shortcut creation, so installation remains fully GUI-only.
            kwargs = {
                "check": True,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform.startswith("win"):
                CREATE_NO_WINDOW = 0x08000000
                kwargs["creationflags"] = CREATE_NO_WINDOW

            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                **kwargs,
            )
            self._log(f"Created shortcut: {shortcut_path}")
        except Exception as exc:
            self._log(f"Failed to create shortcut {shortcut_path}: {exc}")

    def _remove_windows_shortcuts(self) -> None:
        """
        Remove Desktop and Start Menu shortcuts on Windows.
        """
        if not sys.platform.startswith("win"):
            return

        desktop_shortcut, start_menu_shortcut = self._windows_shortcut_paths()
        for path in (desktop_shortcut, start_menu_shortcut):
            try:
                if path.exists():
                    path.unlink()
                    self._log(f"Removed shortcut: {path}")
            except Exception as exc:
                self._log(f"Failed to remove shortcut {path}: {exc}")

    def _register_windows_app(self) -> None:
        """
        Register the application in Windows "Add or Remove Programs" (HKCU).

        IMPORTANT:
        - We always register an installer EXE that lives INSIDE the install
          directory so that uninstall/modify never depends on where the
          original installer was run from (dev tree, Downloads, etc.).
        """
        if not sys.platform.startswith("win"):
            return

        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            self._log("winreg not available; skipping Windows Add/Remove registration.")
            return

        # Resolve the currently running installer executable. This may be in a
        # development checkout, a Downloads folder, etc.
        try:
            exe_src = Path(sys.argv[0]).resolve()
        except Exception as exc:
            self._log(f"Failed to resolve installer executable path: {exc}")
            return

        # Copy the installer into the install directory and register THAT copy
        # in Add/Remove Programs so that uninstall never looks back at the
        # original source location.
        installer_copy = self.install_dir / exe_src.name
        try:
            if not installer_copy.exists() or os.path.getsize(installer_copy) == 0:
                self.install_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(exe_src, installer_copy)
                self._log(
                    f"Copied installer executable to {installer_copy} "
                    "for Add/Remove Programs integration."
                )
            exe_for_registry = installer_copy
        except Exception as exc:
            # If copying fails for any reason, fall back to the original path
            # so uninstall still works, but log clearly for diagnostics.
            self._log(
                "Failed to copy installer into install directory for uninstall; "
                f"falling back to source path {exe_src}: {exc}"
            )
            exe_for_registry = exe_src

        # Prefer the installed icon if present; otherwise fall back to the
        # installer copy we just registered.
        icon_path = self.install_dir / "EDColonisationAsst.ico"
        if not icon_path.exists():
            icon_path = exe_for_registry

        try:
            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                WINDOWS_UNINSTALL_KEY,
                0,
                winreg.KEY_WRITE,
            )
            with key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(icon_path))
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Oliver Ernster")
                winreg.SetValueEx(
                    key, "InstallLocation", 0, winreg.REG_SZ, str(self.install_dir)
                )
                # Launch the installer copy inside the install directory when
                # uninstalling or modifying.
                uninstall_cmd = f'"{exe_for_registry}"'
                winreg.SetValueEx(
                    key, "UninstallString", 0, winreg.REG_SZ, uninstall_cmd
                )
                # Enable "Modify" in Apps & Features by providing a ModifyPath
                # that re-launches this installer as well.
                winreg.SetValueEx(key, "ModifyPath", 0, winreg.REG_SZ, uninstall_cmd)
                # Explicitly allow modify/repair operations.
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 0)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 0)
                if self.version:
                    winreg.SetValueEx(
                        key, "DisplayVersion", 0, winreg.REG_SZ, self.version
                    )
            self._log("Registered application in Windows Add/Remove Programs (HKCU).")
        except Exception as exc:
            self._log(f"Failed to register app in Add/Remove Programs: {exc}")

    def _unregister_windows_app(self) -> None:
        """
        Remove the application's entry from Windows "Add or Remove Programs".
        """
        if not sys.platform.startswith("win"):
            return

        try:
            import winreg  # type: ignore[import-not-found]
        except ImportError:
            return

        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_KEY)
            self._log("Removed Windows Add/Remove Programs entry.")
        except FileNotFoundError:
            self._log("Windows Add/Remove Programs entry not found to remove.")
        except OSError as exc:
            self._log(f"Failed to remove Add/Remove Programs entry: {exc}")


def _is_under_program_files(path: Path) -> bool:
    """
    Return True if the given path resides under a Program Files directory
    on Windows. Used to avoid defaulting back to an admin-only install
    location when the current user does not have elevation rights.
    """
    if not sys.platform.startswith("win"):
        return False

    try:
        resolved = path.resolve()
    except OSError:
        return False

    candidates: list[Path] = []
    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        candidates.append(Path(program_files))

    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
    if program_files_x86:
        candidates.append(Path(program_files_x86))

    for base in candidates:
        try:
            # Python 3.9+ has Path.is_relative_to
            if resolved.is_relative_to(base):
                return True
        except AttributeError:
            # Fallback for older Python: simple prefix comparison
            try:
                if str(resolved).lower().startswith(str(base.resolve()).lower()):
                    return True
            except OSError:
                continue

    return False


def _compare_versions(installed: str, installer: str) -> int:
    """
    Compare two dotted version strings.

    Returns:
        -1 if installed < installer
         0 if installed == installer
         1 if installed > installer
    """

    def _parse(v: str) -> list[int]:
        parts = v.split(".")
        nums: list[int] = []
        for part in parts:
            num = 0
            for ch in part:
                if ch.isdigit():
                    num = num * 10 + int(ch)
                else:
                    break
            nums.append(num)
        return nums

    try:
        a = _parse(installed)
        b = _parse(installer)
    except Exception:
        # Fall back to "equal" on unexpected parsing issues.
        return 0

    max_len = max(len(a), len(b))
    a.extend([0] * (max_len - len(a)))
    b.extend([0] * (max_len - len(b)))

    for av, bv in zip(a, b, strict=False):
        if av < bv:
            return -1
        if av > bv:
            return 1
    return 0


def _windows_get_installed_version() -> Optional[str]:
    """
    Look up the existing installed version (DisplayVersion) from the HKCU
    uninstall key, if any.
    """
    if not sys.platform.startswith("win"):
        return None

    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "DisplayVersion")
            if isinstance(value, str) and value:
                return value
    except OSError:
        return None

    return None


def _windows_get_install_location() -> Optional[Path]:
    """
    Look up the existing InstallLocation from HKCU uninstall key, if any.
    """
    if not sys.platform.startswith("win"):
        return None

    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "InstallLocation")
            if value:
                return Path(value)
    except OSError:
        return None

    return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} Installer")

    # Ensure the installer EXE has the correct icon in the Windows taskbar and
    # reuse the same icon for the splash screen if available.
    splash: QSplashScreen | None = None
    icon_path = PROJECT_ROOT / "EDColonisationAsst.ico"
    if icon_path.exists():
        try:
            app.setWindowIcon(QIcon(str(icon_path)))
            pixmap = QPixmap(str(icon_path))
            splash = QSplashScreen(pixmap)
            splash.showMessage(
                "EDCA Installer",
                Qt.AlignHCenter | Qt.AlignBottom,
                QColor(245, 245, 247),
            )
            splash.show()
            # Process events so the splash actually appears promptly.
            app.processEvents()
        except Exception:
            splash = None

    window = InstallerWindow()
    window.show()

    if splash is not None:
        splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
