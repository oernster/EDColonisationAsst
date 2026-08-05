"""Detecting, closing and launching the installed application.

An install replaces every file in the deployment, so it must not run while the
application holds its own executable open. The setup program therefore detects
a running instance and offers to end it, rather than firing a blind unconditional
kill on uninstall and leaving install and repair unprotected.

Ending it is a forced termination rather than a polite close request. EDCA
minimises to the system tray on close, so asking its window to close leaves the
process alive and the file still locked. The wait afterwards polls for the lock
to release and gives up on a bounded deadline, so a stuck process reports a
typed failure instead of hanging the setup program. British spelling is used in
comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from installer.constants import APP_DISPLAY_NAME, EXE_NAME
from installer.ops.commands import CommandRunner, default_runner
from installer.ops.errors import AppStillRunningError

_TASKLIST = "tasklist"
_TASKLIST_FILTER = "/fi"
_TASKLIST_NO_HEADER = "/nh"
_TASKKILL = "taskkill"
_TASKKILL_IMAGE = "/im"
_TASKKILL_PID = "/pid"
_TASKKILL_FORCE = "/f"
_TASKKILL_TREE = "/t"

TASKLIST_TIMEOUT_S = 10.0
TASKKILL_TIMEOUT_S = 15.0

# How long to wait for the process to disappear after it has been ended, so a
# stuck process cannot hang the setup program indefinitely.
CLOSE_POLL_ATTEMPTS = 50
CLOSE_POLL_INTERVAL_S = 0.1

# The legacy tray controller records its process id here under the install
# directory. The runtime now hosts the tray in process, so this is only for an
# installation made by an older build.
PID_FILE_NAME = "tray.pid"

STILL_RUNNING_MESSAGE = (
    f"{APP_DISPLAY_NAME} could not be closed. Please exit it from the system "
    "tray, then try again."
)

# Injected so the wait can be exercised without spending real time.
Sleeper = Callable[[float], None]


def is_app_running(runner: CommandRunner | None = None) -> bool:
    """Return True when the application appears in the task list.

    Best effort: a task list that cannot be read reports not running, so a
    transient failure never blocks a legitimate install.
    """
    active = runner or default_runner()
    result = active.run(
        [_TASKLIST, _TASKLIST_FILTER, f"imagename eq {EXE_NAME}", _TASKLIST_NO_HEADER],
        timeout=TASKLIST_TIMEOUT_S,
    )
    return EXE_NAME.lower() in result.stdout.lower()


def read_legacy_pid(install_dir: Path) -> int | None:
    """Return the process id an older tray controller recorded, if any."""
    pid_file = install_dir / PID_FILE_NAME
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _terminate(runner: CommandRunner, install_dir: Path | None) -> None:
    """End the legacy tray process if one is recorded, then the runtime."""
    if install_dir is not None:
        pid = read_legacy_pid(install_dir)
        if pid is not None:
            runner.run(
                [_TASKKILL, _TASKKILL_FORCE, _TASKKILL_TREE, _TASKKILL_PID, str(pid)],
                timeout=TASKKILL_TIMEOUT_S,
            )
    runner.run(
        [_TASKKILL, _TASKKILL_FORCE, _TASKKILL_TREE, _TASKKILL_IMAGE, EXE_NAME],
        timeout=TASKKILL_TIMEOUT_S,
    )


def close_running_app(
    runner: CommandRunner | None = None,
    *,
    install_dir: Path | None = None,
    sleep: Sleeper | None = None,
) -> None:
    """End every running instance and wait for its file lock to release.

    Raises AppStillRunningError when the application is still present after the
    wait, so the caller does not proceed onto a locked file.
    """
    active = runner or default_runner()
    wait = sleep or time.sleep
    _terminate(active, install_dir)
    for _ in range(CLOSE_POLL_ATTEMPTS):
        if not is_app_running(active):
            return
        wait(CLOSE_POLL_INTERVAL_S)
    if is_app_running(active):
        raise AppStillRunningError(STILL_RUNNING_MESSAGE)


def launch(exe_path: Path, runner: CommandRunner | None = None) -> None:
    """Start the installed application detached, so it outlives the installer."""
    active = runner or default_runner()
    active.start_detached([str(exe_path)], cwd=str(exe_path.parent))
