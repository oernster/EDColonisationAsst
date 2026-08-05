"""The About and licence view.

The licence arrives formatted for an eighty-column console, so it is rewrapped
before it is shown (see installer.ops.payload.reflow_licence) and the view wraps
to its own width from there. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from installer.constants import APP_DISPLAY_NAME
from installer.ui.icons import app_icon
from installer.ui.layout import (
    DIALOG_MARGIN,
    LICENCE_DIALOG_HEIGHT,
    LICENCE_DIALOG_WIDTH,
    SECTION_SPACING,
)

TITLE = f"About {APP_DISPLAY_NAME}"


class LicenceDialog(QDialog):
    """A scrollable view of the bundled licence text."""

    def __init__(self, licence_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.setWindowIcon(app_icon())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN, DIALOG_MARGIN
        )
        layout.setSpacing(SECTION_SPACING)

        view = QTextEdit(self)
        view.setReadOnly(True)
        view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        view.setPlainText(licence_text)
        layout.addWidget(view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=self)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.resize(LICENCE_DIALOG_WIDTH, LICENCE_DIALOG_HEIGHT)
