"""Install, upgrade, reinstall, downgrade and repair.

Every one of these is the same sequence: put the files down, make sure the
runtime executable is among them, register the uninstaller, record the
installation, then apply the user's options. They differ only in what the button
said and, for a repair, in the fact that the target is already populated. That
is deliberate: the previous flow branched on an older installed version, ran an
uninstall and then returned without installing anything, so the user had to
relaunch the setup program and press the button a second time. British spelling
is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from installer.constants import APP_DISPLAY_NAME, FALLBACK_VERSION
from installer.ops.commands import CommandRunner, default_runner
from installer.ops.copy_tree import copy_tree, count_files
from installer.ops.errors import AppRunningError, RuntimeExeError
from installer.ops.paths import (
    directory_size_kb,
    installed_exe,
    original_installer_exe,
    uninstaller_path,
)
from installer.ops.payload import (
    app_version,
    bundled_runtime_exe,
    installed_icon,
    payload_root,
)
from installer.ops.progress import (
    COMPLETE_PCT,
    COUNT_MESSAGE,
    COUNT_PCT,
    DONE_MESSAGE,
    REGISTER_MESSAGE,
    REGISTER_PCT,
    RUNTIME_MESSAGE,
    RUNTIME_PCT,
    SETTINGS_MESSAGE,
    SETTINGS_PCT,
    SHORTCUTS_MESSAGE,
    SHORTCUTS_PCT,
    UNINSTALLER_MESSAGE,
    UNINSTALLER_PCT,
    ProgressCallback,
    report,
)
from installer.ops.running_app import is_app_running
from installer.ops.shortcuts import apply_shortcuts
from installer.state.registry import (
    DEFAULT_KEYS,
    RegistryKeys,
    set_autostart,
    write_uninstall_entry,
)

APP_RUNNING_MESSAGE = (
    f"{APP_DISPLAY_NAME} is running and its files cannot be replaced while it "
    "is open. Close it from the system tray, then try again."
)

RUNTIME_EXE_FAILED_MESSAGE = (
    f"{APP_DISPLAY_NAME} could not write its program file to {{target}}. The "
    "installation is incomplete and would still run the previous version, so "
    "it has been stopped rather than reported as finished. Close the "
    "application if it is open, then run this installer again."
)


@dataclass(frozen=True, slots=True)
class InstallOptions:
    """The user's choices for one install, upgrade, reinstall or downgrade."""

    target_dir: Path
    desktop: bool
    start_menu: bool
    autostart: bool


def guard_not_running(runner: CommandRunner | None = None) -> None:
    """Refuse to proceed while the application holds its own files open."""
    if is_app_running(runner):
        raise AppRunningError(APP_RUNNING_MESSAGE)


def ensure_runtime_exe(install_dir: Path) -> Path | None:
    """Write the bundled runtime executable into an install directory.

    Nuitka strips loose executables out of an included data directory, so the
    copied payload arrives WITHOUT one and this is the only path that delivers
    the application binary. It therefore overwrites rather than skipping what
    is already there: on a reinstall or an upgrade, the executable at the
    target is the PREVIOUS version's.

    Skipping the copy because the target existed is the defect this replaces,
    since that target is exactly the file needing replacement. It made a
    first install correct and every reinstall a no-op for the one file that
    carries the code, so the user kept running the old build while VERSION, the
    icon and the licence beside it were all refreshed. In the field that showed
    up as a 3.0.0 install whose splash reported 2.9.0, against an executable
    months older than the files next to it.

    A missing bundled runtime is not fatal: whatever is already installed is
    left alone rather than a working install being broken. A copy that fails is
    fatal, because the alternative is reporting success over a stale binary.
    """
    target = installed_exe(install_dir)
    source = bundled_runtime_exe()
    if source is None:
        return target if target.is_file() else None

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    except OSError as exc:
        raise RuntimeExeError(RUNTIME_EXE_FAILED_MESSAGE.format(target=target)) from exc
    return target


def copy_uninstaller(install_dir: Path) -> Path:
    """Copy the setup program into the install root to act as the uninstaller.

    Best effort: the application is already deployed by the time this runs, so
    a failure here degrades to registering the running executable as the
    uninstall source rather than failing the whole install.
    """
    source = original_installer_exe()
    destination = uninstaller_path(install_dir)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    except OSError:
        return source
    return destination


def register(
    install_dir: Path,
    uninstaller: Path,
    version: str,
    keys: RegistryKeys = DEFAULT_KEYS,
) -> None:
    """Record the installation so it appears in Apps and features."""
    icon = installed_icon(install_dir)
    write_uninstall_entry(
        install_dir,
        uninstaller,
        version,
        display_icon=icon if icon is not None else install_dir,
        estimated_kb=directory_size_kb(install_dir),
        keys=keys,
    )


def _deploy(
    target: Path,
    *,
    progress: ProgressCallback | None,
    keys: RegistryKeys,
) -> Path | None:
    """Put the files down and register the installation, reporting as it goes."""
    source = payload_root()
    report(progress, COUNT_PCT, COUNT_MESSAGE)
    total = count_files(source)
    copy_tree(source, target, progress=progress, total=total)

    report(progress, RUNTIME_PCT, RUNTIME_MESSAGE)
    exe_path = ensure_runtime_exe(target)

    report(progress, UNINSTALLER_PCT, UNINSTALLER_MESSAGE)
    uninstaller = copy_uninstaller(target)

    report(progress, REGISTER_PCT, REGISTER_MESSAGE)
    register(target, uninstaller, app_version() or FALLBACK_VERSION, keys)
    return exe_path


def _finish(
    exe_path: Path | None,
    *,
    desktop: bool,
    start_menu: bool,
    progress: ProgressCallback | None,
    runner: CommandRunner,
) -> None:
    """Create the shortcuts once there is an executable to point them at."""
    report(progress, SHORTCUTS_PCT, SHORTCUTS_MESSAGE)
    if exe_path is None:
        return
    apply_shortcuts(exe_path, desktop=desktop, start_menu=start_menu, runner=runner)


def install(
    options: InstallOptions,
    *,
    progress: ProgressCallback | None = None,
    runner: CommandRunner | None = None,
    keys: RegistryKeys = DEFAULT_KEYS,
) -> Path:
    """Run one install, upgrade, reinstall or downgrade in a single pass."""
    active = runner or default_runner()
    guard_not_running(active)

    target = options.target_dir
    exe_path = _deploy(target, progress=progress, keys=keys)
    _finish(
        exe_path,
        desktop=options.desktop,
        start_menu=options.start_menu,
        progress=progress,
        runner=active,
    )

    report(progress, SETTINGS_PCT, SETTINGS_MESSAGE)
    set_autostart(options.autostart, installed_exe(target), keys)

    report(progress, COMPLETE_PCT, DONE_MESSAGE)
    return installed_exe(target)


def repair(
    install_dir: Path,
    *,
    progress: ProgressCallback | None = None,
    runner: CommandRunner | None = None,
    keys: RegistryKeys = DEFAULT_KEYS,
) -> Path:
    """Re-deploy over an existing install and restore its shortcuts.

    The user's sign-in setting is left exactly as it is. A repair restores what
    the installer put down, and the Run entry is a preference rather than part
    of the deployed application; rewriting it from an unread checkbox is how a
    repair used to silently switch that preference off.
    """
    active = runner or default_runner()
    guard_not_running(active)

    exe_path = _deploy(install_dir, progress=progress, keys=keys)
    _finish(
        exe_path,
        desktop=True,
        start_menu=True,
        progress=progress,
        runner=active,
    )

    report(progress, COMPLETE_PCT, DONE_MESSAGE)
    return installed_exe(install_dir)
