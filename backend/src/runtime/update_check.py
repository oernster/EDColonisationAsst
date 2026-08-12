"""The tray's update check: its triggers, its threading and its three answers.

Outside the coverage gate with the rest of the runtime shell. Everything with
a rule in it lives under `services/` and is tested there; what is left here is
Qt wiring and the words on three dialogs.

The threading shape matters and is deliberate. The request runs on a plain
`threading.Thread` so a slow or unreachable GitHub cannot freeze the tray. The
worker emits `_result_ready`, a signal on this object; the connected slot is a
bound method of that same object. The controller is created on the interface
thread, so Qt sees a receiver whose thread affinity it can consult and
delivers through a queued connection: the slot then runs on the interface
thread and every widget is built there. Connecting the worker's signal to a
bare function instead would leave Qt no receiver to consult, the connection
would degrade to a direct one and the prompt would be built on the worker
thread.

The prompts go through [`dialogs.present`](backend/src/runtime/dialogs.py:1)
rather than a bare `exec()` for the reason that module records: a packaged
EDCA has no main window, so a dialog raised from the tray can otherwise open
behind a full-screen game and never be seen.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QMessageBox

from .dialogs import present

if TYPE_CHECKING:  # pragma: no cover
    from ..models.update_info import UpdateStatus
    from ..services.update_service import UpdateService

APP_NAME = "EDCA"

# Late enough that the check never contends with starting the backend, early
# enough that a user who launches and walks away still hears about a release.
LAUNCH_DELAY_MS = 3000

_MILLISECONDS_PER_SECOND = 1000
_SECONDS_PER_DAY = 24 * 60 * 60
RECHECK_INTERVAL_MS = _SECONDS_PER_DAY * _MILLISECONDS_PER_SECOND

UPDATE_TITLE = "Update available"
UPDATE_MESSAGE = "{name} {latest} is available. You are running {current}."
DOWNLOAD_BUTTON_TEXT = "Download"
SKIP_BUTTON_TEXT = "Skip This Version"
LATER_BUTTON_TEXT = "Later"

UP_TO_DATE_TITLE = "No update available"
UP_TO_DATE_MESSAGE = "You are running the latest version."

UNREACHABLE_TITLE = "Update check failed"
UNREACHABLE_MESSAGE = "The update check could not reach GitHub. Please try again later."

SkipReader = Callable[[], "str | None"]
SkipWriter = Callable[[str], None]


class UpdateCheckController(QObject):
    """Runs the update check and reports what it found.

    Two ways in, differing only in what silence means. The automatic checks
    pass the skipped version and say nothing at all unless there is something
    new to say. The manual check from the Help menu ignores the skip and
    reports every outcome, because a user who asked deserves an answer even
    when the answer is that nothing has changed.
    """

    _result_ready = Signal(object, bool)

    def __init__(
        self,
        service: UpdateService,
        load_skipped: SkipReader,
        save_skipped: SkipWriter,
        icon_path: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent if isinstance(parent, QObject) else None)
        self._service = service
        self._load_skipped = load_skipped
        self._save_skipped = save_skipped
        self._icon_path = icon_path

        self._result_ready.connect(self._apply_result)

        QTimer.singleShot(LAUNCH_DELAY_MS, self.check_automatically)
        self._recheck = QTimer(self)
        self._recheck.setInterval(RECHECK_INTERVAL_MS)
        self._recheck.timeout.connect(self.check_automatically)
        self._recheck.start()

    # -------------------- entry points ----------------------------------------

    def check_automatically(self) -> None:
        """Check in the background, honouring a skipped version."""
        self._start(manual=False)

    def check_manually(self) -> None:
        """Check because the user asked, ignoring any skipped version."""
        self._start(manual=True)

    # -------------------- internals -------------------------------------------

    def _start(self, manual: bool) -> None:
        """Run one check on a worker thread."""
        thread = threading.Thread(
            target=self._run,
            args=(manual,),
            name="edca-update-check",
            daemon=True,
        )
        thread.start()

    def _run(self, manual: bool) -> None:
        """The worker body. Nothing here may touch a widget."""
        skipped = None if manual else self._load_skipped()
        status = self._service.check(skipped)
        self._result_ready.emit(status, manual)

    def _apply_result(self, status: UpdateStatus, manual: bool) -> None:
        """Report the outcome. Runs on the interface thread."""
        if status.update_available:
            self._prompt(status)
            return
        if not manual:
            # An automatic check that finds nothing says nothing. This is the
            # branch that keeps the feature quiet, so it is the one that must
            # never grow a dialog.
            return
        if status.reachable:
            self._inform(UP_TO_DATE_TITLE, UP_TO_DATE_MESSAGE)
        else:
            self._inform(UNREACHABLE_TITLE, UNREACHABLE_MESSAGE)

    def _decorate(self, box: QMessageBox, title: str) -> None:
        """Give a box its title and the application icon, when there is one."""
        box.setWindowTitle(title)
        if self._icon_path is not None and self._icon_path.exists():
            box.setWindowIcon(QIcon(str(self._icon_path)))

    def _inform(self, title: str, message: str) -> None:
        """Show a plain outcome the user asked for."""
        box = QMessageBox()
        self._decorate(box, title)
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Information)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        present(box)

    def _prompt(self, status: UpdateStatus) -> None:
        """Offer the update: download it, skip this version or decide later."""
        box = QMessageBox()
        self._decorate(box, UPDATE_TITLE)
        box.setText(
            UPDATE_MESSAGE.format(
                name=APP_NAME,
                latest=status.latest_version,
                current=status.current_version,
            )
        )
        box.setIcon(QMessageBox.Icon.Information)
        download = box.addButton(
            DOWNLOAD_BUTTON_TEXT, QMessageBox.ButtonRole.AcceptRole
        )
        # ActionRole rather than DestructiveRole: skipping a version destroys
        # nothing, it is simply the third choice. Qt lays the buttons out by
        # role in the platform's own order rather than in the order they are
        # added here, which is left to it deliberately.
        skip = box.addButton(SKIP_BUTTON_TEXT, QMessageBox.ButtonRole.ActionRole)
        later = box.addButton(LATER_BUTTON_TEXT, QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(later)

        present(box)
        clicked = box.clickedButton()

        if clicked is download:
            # The asset when the release carries one for this platform,
            # otherwise the release page, which always exists.
            target = status.download_url or status.page_url
            if target:
                QDesktopServices.openUrl(QUrl(target))
        elif clicked is skip and status.latest_version:
            self._save_skipped(status.latest_version)


def install_update_check(
    service: UpdateService,
    load_skipped: SkipReader,
    save_skipped: SkipWriter,
    icon_path: Path | None = None,
) -> UpdateCheckController:
    """Build the controller the tray hangs its Help action on.

    Kept beside the controller rather than inside the tray so that no tray
    module has to know how the check is assembled; the caller then has one
    thing to hold a reference to.
    """
    return UpdateCheckController(
        service=service,
        load_skipped=load_skipped,
        save_skipped=save_skipped,
        icon_path=icon_path,
    )


def default_update_check(icon_path: Path | None = None) -> UpdateCheckController:
    """Assemble the real update check: GitHub, the VERSION file, this platform.

    This is the composition step and it lives here, in the runtime layer,
    rather than in either tray: the trays are clients of a built controller and
    neither of them should know what a release source is. The imports are local
    so that a source checkout importing the tray modules does not pull the
    services package in before it is needed.
    """
    import sys

    try:
        from .. import __version__  # type: ignore[import-not-found]
        from ..services.github_release_source import (  # type: ignore[import-not-found]
            GitHubReleaseSource,
        )
        from ..services.update_service import (  # type: ignore[import-not-found]
            UpdateService,
            platform_key_for,
        )
        from ..services.update_state import (  # type: ignore[import-not-found]
            load_skipped_version,
            save_skipped_version,
        )
    except ImportError:  # pragma: no cover
        # The relative form fails only when this module runs as a top-level
        # script, which the frozen Nuitka build does. That is an ImportError;
        # anything else raised while importing is a real defect.
        from backend.src import __version__  # type: ignore[import-error]
        from backend.src.services.github_release_source import (
            GitHubReleaseSource,  # type: ignore[import-error]
        )
        from backend.src.services.update_service import (
            UpdateService,  # type: ignore[import-error]
            platform_key_for,
        )
        from backend.src.services.update_state import (
            load_skipped_version,  # type: ignore[import-error]
            save_skipped_version,
        )

    service = UpdateService(
        source=GitHubReleaseSource(),
        current_version=__version__,
        platform_key=platform_key_for(sys.platform),
    )
    return install_update_check(
        service=service,
        load_skipped=load_skipped_version,
        save_skipped=save_skipped_version,
        icon_path=icon_path,
    )


__all__ = [
    "LAUNCH_DELAY_MS",
    "RECHECK_INTERVAL_MS",
    "UpdateCheckController",
    "default_update_check",
    "install_update_check",
]
