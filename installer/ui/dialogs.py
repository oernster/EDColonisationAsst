"""The confirmations and reports the setup window shows.

Every destructive step is confirmed and the confirmation names what is affected
and what the consequence is. Closing the running application is confirmed for
the same reason: the user's session ends, so they are told that before it
happens rather than after. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget

from installer.constants import APP_DISPLAY_NAME

CLOSE_TITLE = f"Close {APP_DISPLAY_NAME}"
CLOSE_MESSAGE = (
    f"{APP_DISPLAY_NAME} is running and its files cannot be replaced while it "
    "is open.\n\nClose it now and continue? The running session ends, "
    "including anything it is part way through."
)

UNINSTALL_TITLE = "Confirm uninstall"
UNINSTALL_MESSAGE = (
    "Remove {name} version {version} from this PC?\n\n"
    "Everything under {path} is deleted, along with the shortcuts and the "
    "Apps list entry. Your Elite Dangerous journal is never touched."
)

NOT_INSTALLED_TITLE = "Not installed"
NOT_INSTALLED_MESSAGE = "No existing installation was found at:\n{path}"


def confirm(parent: QWidget, title: str, text: str) -> bool:
    """Ask a yes or no question, defaulting to no."""
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def show_error(parent: QWidget, title: str, text: str) -> None:
    """Report a failure the user needs to act on."""
    QMessageBox.critical(parent, title, text)


def show_info(parent: QWidget, title: str, text: str) -> None:
    """Report a completed operation."""
    QMessageBox.information(parent, title, text)


def confirm_close_running(parent: QWidget) -> bool:
    """Offer to end the running application, stating that the session ends."""
    return confirm(parent, CLOSE_TITLE, CLOSE_MESSAGE)


def confirm_uninstall(parent: QWidget, version: str, path: Path) -> bool:
    """Confirm the removal, naming the version and the directory that goes."""
    return confirm(
        parent,
        UNINSTALL_TITLE,
        UNINSTALL_MESSAGE.format(name=APP_DISPLAY_NAME, version=version, path=path),
    )
