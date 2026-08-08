"""Showing a dialog when there is no window to show it over.

A packaged EDCA has no main window. The backend runs headless in-process and
the tray icon is the entire interface, so a dialog opened from the tray menu
has no parent and the application has no active window for it to sit over.
Windows then leaves it wherever the z-order happens to put it, which with a
full-screen game in front means somewhere the user will never see it. They
choose Exit, nothing appears to happen and they conclude the application
ignored them.

`Qt.WindowStaysOnTopHint` is what actually fixes that; it is the same flag
[`splash.py`](backend/src/runtime/splash.py:1) already sets for the same
reason: the splash is visible on launch precisely because it asks to be.

The order below matters and is asserted in
[`test_dialogs.py`](backend/tests/unit/test_dialogs.py:1):

1. set the flag BEFORE the window exists, because changing it afterwards
   recreates the native window and drops it back down the z-order;
2. `show()` to create that window, since there is nothing to raise or
   activate until it exists;
3. `raise_()` then `activateWindow()`, which put it in front and give it the
   keyboard;
4. `exec()` last, entering the modal loop on the window already on screen.

Activation can still be refused: Windows will not let a process that does not
own the foreground steal it. The stays-on-top flag is what makes that
survivable, because the dialog is then visible whether or not it took focus,
and being seen is the whole point.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMessageBox

_ON_TOP = Qt.WindowType.WindowStaysOnTopHint


class Presentable(Protocol):
    """The part of a Qt dialog `present` uses.

    Narrow on purpose: it is what lets the ordering above be tested against a
    recording stand-in rather than against a real window on a real desktop.
    """

    def setWindowFlag(self, flag: Qt.WindowType, on: bool) -> None:
        """Turn a window flag on or off, before the window is created."""

    def show(self) -> None:
        """Create and display the window."""

    def raise_(self) -> None:
        """Move the window to the top of the z-order."""

    def activateWindow(self) -> None:
        """Ask for the keyboard focus."""

    def exec(self) -> int:
        """Run the modal loop and return the user's answer."""


def present(dialog: Presentable) -> int:
    """Show `dialog` in front of whatever the user is looking at.

    Returns whatever the dialog's own `exec` returns.
    """
    dialog.setWindowFlag(_ON_TOP, True)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog.exec()


def ask_yes_no(
    title: str,
    question: str,
    icon_path: Path | None = None,
) -> bool:
    """Ask a yes/no question in a dialog the user will actually see.

    `No` is the default, so dismissing the dialog cannot destroy anything.

    The application icon is set when one is available. A tray application's
    dialog is its only taskbar entry, so the icon is how the user recognises
    which program is asking.
    """
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(question)
    box.setIcon(QMessageBox.Icon.Question)
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.setDefaultButton(QMessageBox.StandardButton.No)
    if icon_path is not None and icon_path.exists():
        box.setWindowIcon(QIcon(str(icon_path)))

    return present(box) == QMessageBox.StandardButton.Yes


__all__ = ["Presentable", "ask_yes_no", "present"]
