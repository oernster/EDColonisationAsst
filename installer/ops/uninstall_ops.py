"""Removing the application, its shortcuts and its registration.

The registered uninstaller is a copy of the setup program living inside the
directory it has to remove, so it cannot delete its own running executable. The
previous code unlinked in place, swallowed the failure on the running image and
then failed the final rmdir just as silently, which is why uninstalling from
Add/Remove Programs left the tree behind. The last step now hands whatever
remains to a detached helper that polls for the lock to release rather than
racing a fixed delay. British spelling is used in comments. No em dashes appear
anywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from installer.ops.commands import (
    CommandRunner,
    default_runner,
    powershell_command,
)
from installer.ops.copy_tree import count_files, delete_tree
from installer.ops.paths import install_target, running_from_inside
from installer.ops.progress import (
    COMPLETE_PCT,
    DONE_MESSAGE,
    REMOVE_REGISTRY_MESSAGE,
    REMOVE_REGISTRY_PCT,
    REMOVE_SHORTCUTS_MESSAGE,
    REMOVE_SHORTCUTS_PCT,
    ProgressCallback,
    report,
)
from installer.ops.running_app import close_running_app, is_app_running
from installer.ops.shortcuts import remove_all_shortcuts
from installer.state.registry import (
    DEFAULT_KEYS,
    RegistryKeys,
    delete_uninstall_entry,
    installed_location,
    set_autostart,
)

# The detached helper polls rather than sleeping once, so the directory goes as
# soon as the lock on the running uninstaller is released.
DEFERRED_DELETE_ATTEMPTS = 30
DEFERRED_DELETE_INTERVAL_MS = 500

# Answers whether this process is running from inside the directory being
# removed, which is the case the deferral exists for.
RunningInsideCheck = Callable[[Path], bool]

_QUOTE = "'"
_ESCAPED_QUOTE = "''"


def deferred_delete_script(install_dir: Path) -> str:
    """Return the script that removes the directory once the lock is released."""
    escaped = str(install_dir).replace(_QUOTE, _ESCAPED_QUOTE)
    return (
        f"$d = '{escaped}'; "
        f"for ($i = 0; $i -lt {DEFERRED_DELETE_ATTEMPTS}; $i++) {{ "
        "if (-not (Test-Path -LiteralPath $d)) { break } "
        "Remove-Item -LiteralPath $d -Recurse -Force "
        "-ErrorAction SilentlyContinue; "
        "if (-not (Test-Path -LiteralPath $d)) { break } "
        f"Start-Sleep -Milliseconds {DEFERRED_DELETE_INTERVAL_MS} "
        "}"
    )


def schedule_delete_after_exit(
    install_dir: Path,
    runner: CommandRunner | None = None,
) -> None:
    """Delete the install directory from a detached helper once this exits."""
    active = runner or default_runner()
    active.start_detached(
        powershell_command(deferred_delete_script(install_dir), hidden=True)
    )


def remove_install_dir(
    install_dir: Path,
    runner: CommandRunner | None = None,
    *,
    progress: ProgressCallback | None = None,
    is_running_inside: RunningInsideCheck = running_from_inside,
) -> None:
    """Remove the install directory, deferring when it holds the running exe.

    The files are still deleted here first, so the progress bar reports real
    work and almost everything has gone by the time the window closes. Only
    what is genuinely locked is left to the helper, which polls for the lock
    rather than racing a fixed delay.

    The running-inside check is injected so a test can exercise the deferral
    against a temporary directory. Calling the real check would mean pointing
    the deletion at the directory holding the running interpreter.
    """
    if not install_dir.exists():
        return
    delete_tree(install_dir, progress=progress, total=count_files(install_dir))
    if install_dir.exists() or is_running_inside(install_dir):
        schedule_delete_after_exit(install_dir, runner)


def uninstall(
    *,
    progress: ProgressCallback | None = None,
    runner: CommandRunner | None = None,
    keys: RegistryKeys = DEFAULT_KEYS,
    install_dir: Path | None = None,
) -> None:
    """Remove the shortcuts, the registration and then the files."""
    active = runner or default_runner()
    target = install_dir or installed_location(keys) or install_target()
    if is_app_running(active):
        close_running_app(active, install_dir=target)

    report(progress, REMOVE_SHORTCUTS_PCT, REMOVE_SHORTCUTS_MESSAGE)
    remove_all_shortcuts()
    set_autostart(False, Path(), keys)

    report(progress, REMOVE_REGISTRY_PCT, REMOVE_REGISTRY_MESSAGE)
    delete_uninstall_entry(keys)

    remove_install_dir(target, active, progress=progress)

    report(progress, COMPLETE_PCT, DONE_MESSAGE)
