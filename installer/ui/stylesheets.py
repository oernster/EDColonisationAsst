"""Building the setup window's stylesheet from a theme.

There is one template rather than two hand-maintained sheets, so the dark and
the light themes cannot drift apart in structure and every colour comes from
the theme value. The rules that used to exist only in the light sheet (menus
and message boxes) now apply to both, which is why the dark theme's message
boxes are finally dark as well. British spelling is used in comments. No em
dashes appear anywhere.
"""

from __future__ import annotations

from installer.ui.layout import (
    ACTION_BUTTON_HEIGHT_PX,
    BORDER_RADIUS_PX,
    DARK_THEME_BUTTON,
    LIGHT_THEME_BUTTON,
    PATH_LABEL,
    PRIMARY_BUTTON,
    PROGRESS_BAR,
    PROGRESS_HEIGHT_PX,
    REPAIR_BUTTON,
    STATUS_LABEL,
    SUBTITLE_LABEL,
    THEME_BUTTON_PX,
    THEME_BUTTON_RADIUS_PX,
    TITLE_LABEL,
    UNINSTALL_BUTTON,
)
from installer.ui.theme import Theme

_GRADIENT = (
    "qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, "
    "stop:0 {start}, stop:1 {end})"
)
_GRADIENT_UP = (
    "qlineargradient(spread:pad, x1:0, y1:1, x2:1, y2:0, "
    "stop:0 {start}, stop:1 {end})"
)

TITLE_FONT_PX = 22
BODY_FONT_PX = 12
SMALL_FONT_PX = 11
INDICATOR_PX = 14
BORDER_PX = 1
INDICATOR_RADIUS_PX = 3


def _gradient(start: str, end: str, *, upward: bool = False) -> str:
    """Return one of the two diagonal gradients the action buttons use."""
    template = _GRADIENT_UP if upward else _GRADIENT
    return template.format(start=start, end=end)


def _chrome(theme: Theme) -> str:
    """Return the rules for the window, its toolbar, its status bar and text."""
    return f"""
QMainWindow, QWidget {{ background-color: {theme.window_bg}; color: {theme.text}; }}
QToolBar {{
    background-color: {theme.chrome_bg};
    border-bottom: {BORDER_PX}px solid {theme.border};
}}
QToolBar QToolButton {{ color: {theme.text}; background-color: transparent; }}
QToolBar QToolButton:hover {{ background-color: {theme.chrome_bg}; }}
QToolBar QToolButton:pressed {{ background-color: {theme.dialog_button_pressed_bg}; }}
QStatusBar {{
    background-color: {theme.chrome_bg};
    color: {theme.text};
    border-top: {BORDER_PX}px solid {theme.border};
}}
QMenuBar, QMenu {{ background-color: {theme.chrome_bg}; color: {theme.text}; }}
QMenuBar::item, QMenu::item {{ color: {theme.text}; background-color: transparent; }}
QMenuBar::item:selected, QMenu::item:selected {{
    background-color: {theme.dialog_button_hover_bg};
    color: {theme.text};
}}
QLabel {{ color: {theme.body_text}; }}
QLabel#{TITLE_LABEL} {{
    color: {theme.title_text};
    font-size: {TITLE_FONT_PX}px;
    font-weight: 600;
    padding-bottom: 4px;
}}
QLabel#{SUBTITLE_LABEL} {{ color: {theme.body_text}; font-size: {BODY_FONT_PX}px; }}
QLabel#{STATUS_LABEL} {{ color: {theme.text}; font-size: {BODY_FONT_PX}px; }}
QLabel#{PATH_LABEL} {{ color: {theme.body_text}; font-size: {SMALL_FONT_PX}px; }}
QTextEdit {{
    background-color: {theme.base_bg};
    color: {theme.text};
    border: {BORDER_PX}px solid {theme.border};
    border-radius: 8px;
}}
"""


def _controls(theme: Theme) -> str:
    """Return the rules for checkboxes, the progress bar and message boxes."""
    return f"""
QCheckBox {{ color: {theme.body_text}; }}
QCheckBox::indicator {{
    width: {INDICATOR_PX}px;
    height: {INDICATOR_PX}px;
    background-color: {theme.indicator_bg};
    border: {BORDER_PX}px solid {theme.border};
    border-radius: {INDICATOR_RADIUS_PX}px;
}}
QCheckBox::indicator:hover {{ background-color: {theme.indicator_hover_bg}; }}
QCheckBox::indicator:checked {{
    background-color: {theme.indicator_checked_bg};
    border-color: {theme.indicator_checked_bg};
}}
QProgressBar#{PROGRESS_BAR} {{
    background-color: {theme.base_bg};
    border: {BORDER_PX}px solid {theme.border};
    border-radius: 6px;
    min-height: {PROGRESS_HEIGHT_PX}px;
    text-align: center;
    color: {theme.text};
}}
QProgressBar#{PROGRESS_BAR}::chunk {{
    background-color: {theme.progress_chunk};
    border-radius: 5px;
}}
QDialog, QMessageBox {{ background-color: {theme.dialog_bg}; color: {theme.text}; }}
QMessageBox QLabel {{ color: {theme.text}; }}
QMessageBox QPushButton, QDialogButtonBox QPushButton {{
    color: {theme.text};
    background-color: {theme.dialog_button_bg};
    border: {BORDER_PX}px solid {theme.border};
    padding: 4px 10px;
    border-radius: 4px;
}}
QMessageBox QPushButton:enabled:hover, QDialogButtonBox QPushButton:enabled:hover {{
    background-color: {theme.dialog_button_hover_bg};
}}
QMessageBox QPushButton:pressed, QDialogButtonBox QPushButton:pressed {{
    background-color: {theme.dialog_button_pressed_bg};
}}
"""


def _actions(theme: Theme) -> str:
    """Return the rules for the three action pills and the theme toggles."""
    return f"""
QPushButton#{PRIMARY_BUTTON}, QPushButton#{REPAIR_BUTTON},
QPushButton#{UNINSTALL_BUTTON} {{
    min-height: {ACTION_BUTTON_HEIGHT_PX}px;
    padding: 8px 18px;
    border-radius: {BORDER_RADIUS_PX}px;
    font-weight: 600;
    border: none;
}}
QPushButton#{PRIMARY_BUTTON} {{
    color: {theme.primary_text};
    background-color: {_gradient(theme.primary_start, theme.primary_end)};
}}
QPushButton#{PRIMARY_BUTTON}:enabled:hover {{
    background-color: {_gradient(
        theme.primary_hover_start, theme.primary_hover_end
    )};
}}
QPushButton#{PRIMARY_BUTTON}:pressed {{
    background-color: {_gradient(
        theme.primary_pressed_start, theme.primary_pressed_end, upward=True
    )};
}}
QPushButton#{REPAIR_BUTTON} {{
    color: {theme.repair_text};
    background-color: {_gradient(theme.repair_start, theme.repair_end)};
}}
QPushButton#{REPAIR_BUTTON}:enabled:hover {{
    background-color: {_gradient(theme.repair_hover_start, theme.repair_hover_end)};
}}
QPushButton#{REPAIR_BUTTON}:pressed {{
    background-color: {_gradient(
        theme.repair_pressed_start, theme.repair_pressed_end, upward=True
    )};
}}
QPushButton#{UNINSTALL_BUTTON} {{
    background-color: transparent;
    color: {theme.danger_text};
    border: {BORDER_PX}px solid {theme.danger_border};
}}
QPushButton#{UNINSTALL_BUTTON}:enabled:hover {{
    background-color: {theme.danger_hover_bg};
}}
QPushButton#{UNINSTALL_BUTTON}:pressed {{
    background-color: {theme.danger_pressed_bg};
}}
QPushButton#{PRIMARY_BUTTON}:disabled, QPushButton#{REPAIR_BUTTON}:disabled,
QPushButton#{UNINSTALL_BUTTON}:disabled {{
    background-color: {theme.chrome_bg};
    color: {theme.border};
    border-color: {theme.border};
}}
QPushButton#{LIGHT_THEME_BUTTON}, QPushButton#{DARK_THEME_BUTTON} {{
    border-radius: {THEME_BUTTON_RADIUS_PX}px;
    min-width: {THEME_BUTTON_PX}px;
    min-height: {THEME_BUTTON_PX}px;
    max-width: {THEME_BUTTON_PX}px;
    max-height: {THEME_BUTTON_PX}px;
    padding: 0;
    border: {BORDER_PX}px solid {theme.toggle_border};
    background-color: {theme.toggle_bg};
    color: {theme.toggle_text};
}}
QPushButton#{LIGHT_THEME_BUTTON}:checked, QPushButton#{DARK_THEME_BUTTON}:checked {{
    border: {BORDER_PX}px solid {theme.toggle_checked_border};
    background-color: {theme.toggle_checked_bg};
}}
"""


def stylesheet(theme: Theme) -> str:
    """Return the whole stylesheet for one theme."""
    return _chrome(theme) + _controls(theme) + _actions(theme)
