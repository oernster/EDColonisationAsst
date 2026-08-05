"""The setup program's composition root.

This is the only module that wires the pieces together: it installs crash
logging, reads the command line and then either runs the window or the headless
uninstall the registered UninstallString invokes. British spelling is used in
comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from installer.cli import Options, parse_args
from installer.constants import APP_DISPLAY_NAME
from installer.ops.errors import InstallerError
from installer.ops.uninstall_ops import uninstall
from installer.shared.logging_setup import install_crash_logging
from installer.ui.icons import app_icon
from installer.ui.main_window import WINDOW_TITLE, InstallerWindow

SETUP_APPLICATION_NAME = f"{APP_DISPLAY_NAME} Installer"

SUCCESS = 0
FAILURE = 1
IMMEDIATELY_MS = 0


def _application() -> QApplication:
    """Return a QApplication carrying the setup program's identity."""
    app = QApplication(sys.argv)
    app.setApplicationName(SETUP_APPLICATION_NAME)
    app.setWindowIcon(app_icon())
    return app


def run_uninstall_quietly() -> int:
    """Run the uninstall with no window, as a scripted removal would."""
    try:
        uninstall()
    except InstallerError:
        return FAILURE
    return SUCCESS


def run_window(*, uninstall_on_open: bool = False) -> int:
    """Show the setup window and run the Qt event loop until it closes."""
    app = _application()
    app.setApplicationName(WINDOW_TITLE)
    window = InstallerWindow()
    window.show()
    if uninstall_on_open:
        # Queued rather than called directly, so the window is painted behind
        # the confirmation instead of appearing after it.
        QTimer.singleShot(IMMEDIATELY_MS, window.start_uninstall)
    return app.exec()


def run_uninstall(options: Options) -> int:
    """Run the uninstall flow invoked by the registered UninstallString.

    The windowed path opens the setup window with the confirmation already up,
    so a user who meant to repair rather than remove can still do so. Only the
    explicitly quiet invocation removes anything without asking.
    """
    if options.quiet:
        _application()
        return run_uninstall_quietly()
    return run_window(uninstall_on_open=True)


def main(argv: list[str] | None = None) -> int:
    """Run the setup program, or the uninstall flow when so invoked."""
    install_crash_logging()
    options = parse_args(list(argv) if argv is not None else sys.argv[1:])
    if options.uninstall:
        return run_uninstall(options)
    return run_window()


if __name__ == "__main__":
    raise SystemExit(main())
