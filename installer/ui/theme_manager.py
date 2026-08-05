"""Applying a theme to the running application.

The palette and the stylesheet are set together: Qt paints some chrome from the
palette and some from the stylesheet, so setting only one leaves a window that
is half dark and half light. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from installer.ui.stylesheets import stylesheet
from installer.ui.theme import DARK, LIGHT, Theme, theme_for

FUSION_STYLE = "Fusion"


def palette_for(theme: Theme) -> QPalette:
    """Return a Qt palette carrying the theme's own colours."""
    palette = QPalette()
    window = QColor(theme.window_bg)
    text = QColor(theme.text)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.base_bg))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.chrome_bg))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.chrome_bg))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.chrome_bg))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, window)
    return palette


class ThemeManager:
    """Applies one of the two themes to a running QApplication."""

    def __init__(self, app: QApplication) -> None:
        self._app = app

    def apply(self, mode: str) -> str:
        """Apply the named theme and return the name that was applied."""
        theme = theme_for(mode)
        self._app.setStyle(FUSION_STYLE)
        self._app.setPalette(palette_for(theme))
        self._app.setStyleSheet(stylesheet(theme))
        return theme.name


def other_theme(mode: str) -> str:
    """Return the theme the toggle switches to from the given one."""
    return LIGHT if mode == DARK else DARK
