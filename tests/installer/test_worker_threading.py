"""The worker seam, asserted on the one property that broke it: thread affinity.

A Qt signal connected to a bare callable has no receiver whose thread affinity
Qt can consult, so it degrades to a direct connection and the slot runs in the
sender's thread. OperationRunner used to connect the caller's callbacks and a
cleanup lambda straight to the worker's signals, so both ran on the worker
thread. The finish callback opened a modal dialog and closed the window from
there; the cleanup called QThread.wait() from inside the thread it was
waiting for.

These use QCoreApplication rather than QApplication: nothing here touches a
widget, so no display or platform plugin is involved and the test is not a
fragile UI test.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QThread, QTimer

from installer.ops.errors import InstallerError
from installer.ui.worker import OperationRunner

# Generous: a stuck run should fail the test rather than hang the suite.
_TEST_TIMEOUT_MS = 15_000

_HALFWAY_PCT = 50


@pytest.fixture(scope="module")
def qt_app() -> QCoreApplication:
    """One event loop for the module; Qt allows only a single instance."""
    return QCoreApplication.instance() or QCoreApplication([])


def _run(qt_app: QCoreApplication, operation) -> dict[str, object]:
    """Drive one operation through the runner and record where each step ran."""
    ui_thread = QThread.currentThread()
    seen: dict[str, object] = {}
    runner = OperationRunner()

    def on_progress(pct: int, message: str) -> None:
        seen["progress_on_ui"] = QThread.currentThread() is ui_thread
        seen["pct"] = pct
        seen["message"] = message

    def on_finished(error: str, result: object) -> None:
        seen["finished_on_ui"] = QThread.currentThread() is ui_thread
        seen["still_busy"] = runner.busy
        seen["error"] = error
        seen["result"] = result
        QTimer.singleShot(0, qt_app.quit)

    runner.start(operation, on_progress, on_finished)
    QTimer.singleShot(_TEST_TIMEOUT_MS, qt_app.quit)
    qt_app.exec()
    return seen


def test_the_operation_really_does_run_off_the_interface_thread(qt_app) -> None:
    """Without this the rest of the file would pass for the wrong reason."""

    def operation(report):
        return QThread.currentThread()

    seen = _run(qt_app, operation)

    assert seen["result"] is not QThread.currentThread()


def test_both_callbacks_arrive_on_the_interface_thread(qt_app) -> None:
    """Widget calls and modal dialogs happen in these, so they must be on it."""

    def operation(report):
        report(_HALFWAY_PCT, "halfway")
        return "done"

    seen = _run(qt_app, operation)

    assert seen["progress_on_ui"] is True
    assert seen["finished_on_ui"] is True
    assert seen["pct"] == _HALFWAY_PCT
    assert seen["message"] == "halfway"
    assert seen["error"] == ""
    assert seen["result"] == "done"


def test_the_worker_thread_is_retired_before_the_callback_runs(qt_app) -> None:
    """The callback may close the window, which must not race a live thread."""

    def operation(report):
        return "done"

    assert _run(qt_app, operation)["still_busy"] is False


def test_an_installer_error_is_delivered_as_a_message_on_the_interface_thread(
    qt_app,
) -> None:
    """A failure has to reach a dialog, which means reaching the right thread."""

    def operation(report):
        raise InstallerError("no room on the device")

    seen = _run(qt_app, operation)

    assert seen["finished_on_ui"] is True
    assert seen["error"] == "no room on the device"
    assert seen["result"] is None


def test_an_unexpected_failure_is_also_delivered_rather_than_lost(qt_app) -> None:
    """A bare exception would otherwise vanish with the thread."""

    def operation(report):
        raise RuntimeError("something unforeseen")

    seen = _run(qt_app, operation)

    assert seen["finished_on_ui"] is True
    assert "something unforeseen" in str(seen["error"])
    assert seen["result"] is None
