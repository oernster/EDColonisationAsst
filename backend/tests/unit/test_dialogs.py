"""What `runtime.dialogs` guarantees about a dialog the tray opens.

A packaged EDCA has no main window, so a dialog raised from the tray menu has
no parent and no active window to sit over. The Exit confirmation opened behind
whatever the user was looking at, which for this application is a full-screen
game; they pressed Exit, saw nothing and reported that the application would
not quit.

Qt is not mocked here and no window is opened. `present` is written against a
narrow protocol precisely so the ordering it depends on can be asserted against
a recording stand-in, which is the property whose absence caused the defect:
setting the stays-on-top flag after the window exists recreates that window and
drops it back down the z-order; raising a window before `show()` has created it
does nothing at all.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from src.runtime.dialogs import present

_ON_TOP = Qt.WindowType.WindowStaysOnTopHint

_EXEC_RESULT = 4242


class RecordingDialog:
    """A stand-in that records the order it is driven in."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.flags: dict[Qt.WindowType, bool] = {}

    def setWindowFlag(self, flag: Qt.WindowType, on: bool) -> None:  # noqa: N802
        self.calls.append("setWindowFlag")
        self.flags[flag] = on

    def show(self) -> None:
        self.calls.append("show")

    def raise_(self) -> None:
        self.calls.append("raise_")

    def activateWindow(self) -> None:  # noqa: N802
        self.calls.append("activateWindow")

    def exec(self) -> int:
        self.calls.append("exec")
        return _EXEC_RESULT


def test_present_asks_to_stay_on_top() -> None:
    """Without this flag the dialog opens behind a full-screen game."""
    dialog = RecordingDialog()

    present(dialog)

    assert dialog.flags[_ON_TOP] is True


def test_present_sets_the_flag_before_the_window_exists() -> None:
    """Changing it after show() recreates the window lower in the z-order."""
    dialog = RecordingDialog()

    present(dialog)

    assert dialog.calls.index("setWindowFlag") < dialog.calls.index("show")


def test_present_raises_and_activates_after_showing() -> None:
    """There is no window to raise or give focus to until show() has run."""
    dialog = RecordingDialog()

    present(dialog)

    shown = dialog.calls.index("show")
    assert shown < dialog.calls.index("raise_") < dialog.calls.index("activateWindow")


def test_present_runs_the_modal_loop_last() -> None:
    """exec() blocks, so anything after it would not run until the user replies."""
    dialog = RecordingDialog()

    present(dialog)

    assert dialog.calls[-1] == "exec"


def test_present_returns_the_dialog_result() -> None:
    """Callers decide on this, so it must be the dialog's own answer."""
    assert present(RecordingDialog()) == _EXEC_RESULT


def test_present_drives_every_step_exactly_once() -> None:
    """The whole sequence, pinned. A bare exec() is what shipped the defect."""
    dialog = RecordingDialog()

    present(dialog)

    assert dialog.calls == [
        "setWindowFlag",
        "show",
        "raise_",
        "activateWindow",
        "exec",
    ]
