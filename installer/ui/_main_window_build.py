"""Assembling the setup window's layout, and naming its primary action.

Construction is separated from behaviour so each stays small enough to read in
one pass: this module only builds widgets, places them and decides what the
labels say; the window module decides what they do.

The primary button's caption is derived from the detected state rather than
fixed at "Install". A button that says Install while it is about to replace a
newer version is the same defect as the flow that used to uninstall and then
stop. British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from installer.constants import APP_DISPLAY_NAME
from installer.ops.progress import COMPLETE_PCT, MINIMUM_PCT
from installer.state.model import InstallState, StateSnapshot
from installer.ui.layout import (
    ACTION_BUTTON_HEIGHT_PX,
    BUTTON_SPACING,
    CONTENT_MARGIN,
    DARK_THEME_BUTTON,
    LIGHT_THEME_BUTTON,
    OPTION_SPACING,
    PATH_LABEL,
    PRIMARY_BUTTON,
    PROGRESS_BAR,
    REPAIR_BUTTON,
    SECTION_SPACING,
    STATUS_LABEL,
    SUBTITLE_LABEL,
    THEME_BUTTON_PX,
    THEME_BUTTON_SPACING,
    TITLE_LABEL,
    UNINSTALL_BUTTON,
)

INSTALL_LABEL = "Install"
UPGRADE_LABEL = "Upgrade to {version}"
UPGRADE_FALLBACK_LABEL = "Upgrade"
REINSTALL_LABEL = "Reinstall"
DOWNGRADE_LABEL = "Downgrade to {version}"
DOWNGRADE_FALLBACK_LABEL = "Downgrade"
REPAIR_LABEL = "Repair"
UNINSTALL_LABEL = "Uninstall"

TITLE_TEXT = f"{APP_DISPLAY_NAME} Installer"
INSTALL_PATH_TEXT = "Install directory:\n{path}"
NOT_INSTALLED_SUBTITLE = "Installer version {version} · nothing installed yet"
INSTALLED_SUBTITLE = (
    "Installer version {version} · installed version {installed} at {path}"
)

DESKTOP_LABEL = "Create Desktop shortcut"
START_MENU_LABEL = "Add Start Menu entry"
LAUNCH_LABEL = f"Launch {APP_DISPLAY_NAME} when finished"
AUTOSTART_LABEL = "Start EDCA automatically when I sign in (system tray)"

LIGHT_GLYPH = "☀️"
DARK_GLYPH = "\U0001f319"
LIGHT_TOOLTIP = "Switch to light mode"
DARK_TOOLTIP = "Switch to dark mode"
IDLE_STATUS = "Ready"


@dataclass(frozen=True, slots=True)
class WindowWidgets:
    """Every widget the window's behaviour needs to reach."""

    subtitle: QLabel
    path_label: QLabel
    status: QLabel
    progress: QProgressBar
    primary: QPushButton
    repair: QPushButton
    uninstall: QPushButton
    light_button: QPushButton
    dark_button: QPushButton
    desktop: QCheckBox
    start_menu: QCheckBox
    launch_on_finish: QCheckBox
    autostart: QCheckBox


def primary_label(snapshot: StateSnapshot) -> str:
    """Return the primary button caption for the detected state."""
    version = snapshot.bundled_version
    if snapshot.state == InstallState.NOT_INSTALLED:
        return INSTALL_LABEL
    if snapshot.state == InstallState.REINSTALL:
        return REINSTALL_LABEL
    versioned, plain = (
        (UPGRADE_LABEL, UPGRADE_FALLBACK_LABEL)
        if snapshot.state == InstallState.UPGRADE
        else (DOWNGRADE_LABEL, DOWNGRADE_FALLBACK_LABEL)
    )
    return versioned.format(version=version) if version else plain


def subtitle_text(snapshot: StateSnapshot) -> str:
    """Return the subtitle describing what is installed against what is bundled."""
    if not snapshot.installed:
        return NOT_INSTALLED_SUBTITLE.format(version=snapshot.bundled_version)
    return INSTALLED_SUBTITLE.format(
        version=snapshot.bundled_version,
        installed=snapshot.installed_version,
        path=snapshot.install_dir,
    )


def _action_button(text: str, name: str) -> QPushButton:
    """Return one of the three action pills, named for the stylesheet."""
    button = QPushButton(text)
    button.setObjectName(name)
    button.setMinimumHeight(ACTION_BUTTON_HEIGHT_PX)
    return button


def _theme_button(glyph: str, name: str, tooltip: str) -> QPushButton:
    """Return one of the two header theme toggles."""
    button = QPushButton(glyph)
    button.setObjectName(name)
    button.setCheckable(True)
    button.setFixedSize(THEME_BUTTON_PX, THEME_BUTTON_PX)
    button.setToolTip(tooltip)
    return button


def _make_widgets(snapshot: StateSnapshot, windows: bool) -> WindowWidgets:
    """Create every widget, named and styled, before any of it is placed."""
    subtitle = QLabel(subtitle_text(snapshot))
    subtitle.setObjectName(SUBTITLE_LABEL)
    subtitle.setWordWrap(True)

    path_label = QLabel(INSTALL_PATH_TEXT.format(path=snapshot.install_dir))
    path_label.setObjectName(PATH_LABEL)
    path_label.setWordWrap(True)

    status = QLabel(IDLE_STATUS)
    status.setObjectName(STATUS_LABEL)
    status.setWordWrap(True)

    progress = QProgressBar()
    progress.setObjectName(PROGRESS_BAR)
    progress.setRange(MINIMUM_PCT, COMPLETE_PCT)
    progress.setValue(MINIMUM_PCT)
    progress.setTextVisible(True)

    desktop = QCheckBox(DESKTOP_LABEL)
    start_menu = QCheckBox(START_MENU_LABEL)
    launch_on_finish = QCheckBox(LAUNCH_LABEL)
    autostart = QCheckBox(AUTOSTART_LABEL)
    for box in (desktop, start_menu, launch_on_finish):
        box.setChecked(windows)
        box.setEnabled(windows)
    # The sign-in setting reflects what is actually registered, so a repair no
    # longer switches it off behind the user's back.
    autostart.setChecked(snapshot.autostart)
    autostart.setEnabled(windows)

    return WindowWidgets(
        subtitle=subtitle,
        path_label=path_label,
        status=status,
        progress=progress,
        primary=_action_button(primary_label(snapshot), PRIMARY_BUTTON),
        repair=_action_button(REPAIR_LABEL, REPAIR_BUTTON),
        uninstall=_action_button(UNINSTALL_LABEL, UNINSTALL_BUTTON),
        light_button=_theme_button(LIGHT_GLYPH, LIGHT_THEME_BUTTON, LIGHT_TOOLTIP),
        dark_button=_theme_button(DARK_GLYPH, DARK_THEME_BUTTON, DARK_TOOLTIP),
        desktop=desktop,
        start_menu=start_menu,
        launch_on_finish=launch_on_finish,
        autostart=autostart,
    )


def _build_header(widgets: WindowWidgets) -> QHBoxLayout:
    """Build the header: title and subtitle on the left, the toggles on the right."""
    title = QLabel(TITLE_TEXT)
    title.setObjectName(TITLE_LABEL)
    title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    text_column = QVBoxLayout()
    text_column.addWidget(title)
    text_column.addWidget(widgets.subtitle)

    toggles = QHBoxLayout()
    toggles.setSpacing(THEME_BUTTON_SPACING)
    toggles.addWidget(widgets.light_button)
    toggles.addWidget(widgets.dark_button)

    header = QHBoxLayout()
    header.addLayout(text_column)
    header.addStretch()
    header.addLayout(toggles)
    return header


def _build_options(widgets: WindowWidgets) -> QVBoxLayout:
    """Build the column of install options."""
    options = QVBoxLayout()
    options.setSpacing(OPTION_SPACING)
    options.addWidget(widgets.desktop)
    options.addWidget(widgets.start_menu)
    options.addWidget(widgets.launch_on_finish)
    options.addWidget(widgets.autostart)
    return options


def _build_actions(widgets: WindowWidgets) -> QVBoxLayout:
    """Build the stacked action buttons."""
    actions = QVBoxLayout()
    actions.setSpacing(BUTTON_SPACING)
    actions.addWidget(widgets.primary)
    actions.addWidget(widgets.repair)
    actions.addWidget(widgets.uninstall)
    return actions


def build_window(
    window: QMainWindow, snapshot: StateSnapshot, *, windows: bool
) -> WindowWidgets:
    """Create the window's widgets and lay them out in one column."""
    widgets = _make_widgets(snapshot, windows)

    central = QWidget(window)
    layout = QVBoxLayout(central)
    layout.setContentsMargins(
        CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN
    )
    layout.setSpacing(SECTION_SPACING)

    layout.addLayout(_build_header(widgets))
    layout.addLayout(_build_actions(widgets))
    layout.addWidget(widgets.path_label)
    layout.addLayout(_build_options(widgets))
    layout.addWidget(widgets.progress)
    layout.addWidget(widgets.status)
    layout.addStretch()

    window.setCentralWidget(central)
    return widgets
