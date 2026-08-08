"""Running an installer operation off the UI thread.

Install, repair and uninstall all move thousands of files, so running them on
the UI thread froze the window for the whole operation. The previous code faked
responsiveness by calling processEvents() after every file, which repaints but
also re-enters the event loop from inside the copy, so a click during an install
was dispatched half way through it. Each operation runs on a worker thread
instead and reports back through signals. British spelling is used in comments.
No em dashes appear anywhere.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from installer.ops.errors import InstallerError
from installer.ops.progress import ProgressCallback

# An operation receives a progress reporter and returns whatever the caller
# needs afterwards: the installed executable path or nothing at all.
Operation = Callable[[ProgressCallback], object]

NO_ERROR = ""
UNEXPECTED_ERROR = "The operation failed: {detail}"

# Bound so a worker that will not retire cannot hang the setup program on exit.
# Nothing here should take anywhere near this long; it is a backstop, not a
# budget.
THREAD_JOIN_TIMEOUT_MS = 10_000


class OperationWorker(QObject):
    """Runs one operation and reports its progress, then its outcome."""

    progressed = Signal(int, str)
    finished = Signal(str, object)

    def __init__(self, operation: Operation) -> None:
        super().__init__()
        self._operation = operation

    @Slot()
    def run(self) -> None:
        """Run the operation, reporting failure as a message rather than raising.

        A worker thread that raises would tear down the thread with nothing
        shown, so every failure is turned into the message the window displays.
        """
        try:
            result = self._operation(self._report)
        except InstallerError as error:
            self.finished.emit(str(error), None)
            return
        except Exception as error:  # noqa: BLE001
            # Last resort: an unexpected failure must still reach the user
            # rather than disappearing with the thread.
            self.finished.emit(UNEXPECTED_ERROR.format(detail=error), None)
            return
        self.finished.emit(NO_ERROR, result)

    def _report(self, pct: int, message: str) -> None:
        """Forward one progress update to the UI thread."""
        self.progressed.emit(pct, message)


class OperationRunner(QObject):
    """Owns the worker thread for one operation and cleans it up afterwards.

    Every worker signal is connected to a bound method of this runner, never to
    the callables the caller passes in. That is the whole point of this class.

    A Qt signal connected to a bare callable (a lambda or any target that is
    not a QObject method) gives Qt no receiver whose thread affinity it can
    consult, so the connection degrades to a direct one and the slot runs in the
    SENDER's thread. The sender here is the worker, so the caller's callbacks
    ran off the interface thread: they touched widgets and opened modal dialogs
    there, which is undefined behaviour; the cleanup then called
    ``QThread.wait()`` from inside the very thread it was waiting for. That is a
    crash and a self-join, which is what was seen.

    This runner is a QObject living on the interface thread, so routing through
    its own slots restores a queued connection and delivers on the right thread.
    Both halves of that are measured rather than assumed; see
    ``test_worker_runs_callbacks_on_the_interface_thread``.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: OperationWorker | None = None
        self._on_progress: Callable[[int, str], None] | None = None
        self._on_finished: Callable[[str, object], None] | None = None

    @property
    def busy(self) -> bool:
        """Whether a worker thread is still live."""
        return self._thread is not None

    def start(
        self,
        operation: Operation,
        on_progress: Callable[[int, str], None],
        on_finished: Callable[[str, object], None],
    ) -> None:
        """Run ``operation`` on a worker thread and report back on the UI thread."""
        thread = QThread(self)
        worker = OperationWorker(operation)
        worker.moveToThread(thread)

        self._on_progress = on_progress
        self._on_finished = on_finished

        thread.started.connect(worker.run)
        worker.progressed.connect(self._handle_progress)
        worker.finished.connect(self._handle_finished)

        self._thread = thread
        self._worker = worker
        thread.start()

    @Slot(int, str)
    def _handle_progress(self, pct: int, message: str) -> None:
        """Forward progress to the caller, now on the interface thread."""
        if self._on_progress is not None:
            self._on_progress(pct, message)

    @Slot(str, object)
    def _handle_finished(self, error: str, result: object) -> None:
        """Retire the thread, then hand the outcome to the caller.

        The thread is joined BEFORE the callback runs. The callback is free to
        open a modal dialog or close the window; neither should happen with
        a worker thread still live behind it.
        """
        self._stop()
        callback = self._on_finished
        self._on_progress = None
        self._on_finished = None
        if callback is not None:
            callback(error, result)

    def _stop(self) -> None:
        """Quit and wait for the worker thread, then release both objects."""
        thread = self._thread
        if thread is not None:
            thread.quit()
            thread.wait(THREAD_JOIN_TIMEOUT_MS)
        self._thread = None
        self._worker = None
