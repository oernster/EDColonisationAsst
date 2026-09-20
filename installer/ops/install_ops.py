"""Install, upgrade, reinstall, downgrade and repair.

Every one of these is the same sequence: put the payload down, extract the
runtime archive over it, register the uninstaller, record the installation,
then apply the user's options. They differ only in what the button
said and in whether the target is already populated, as it is for a repair. That
is deliberate: the previous flow branched on an older installed version, ran an
uninstall and then returned without installing anything, so the user had to
relaunch the setup program and press the button a second time. British spelling
is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from installer.constants import APP_DISPLAY_NAME, FALLBACK_VERSION
from installer.ops.commands import CommandRunner, default_runner
from installer.ops.copy_tree import copy_tree, count_files, safe_destination
from installer.ops.errors import AppRunningError, RuntimeExeError
from installer.ops.paths import (
    directory_size_kb,
    installed_exe,
    original_installer_exe,
    uninstaller_path,
)
from installer.ops.payload import (
    app_version,
    bundled_runtime_archive,
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
    RUNTIME_END_PCT,
    RUNTIME_MESSAGE,
    RUNTIME_START_PCT,
    SETTINGS_MESSAGE,
    SETTINGS_PCT,
    SHORTCUTS_MESSAGE,
    SHORTCUTS_PCT,
    UNINSTALLER_MESSAGE,
    UNINSTALLER_PCT,
    ProgressCallback,
    report,
    scaled,
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


def extract_runtime(
    install_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> Path | None:
    """Extract the bundled runtime archive into an install directory.

    The archive carries the whole application: the interpreter, the
    dependencies, the sources and the built front end. It therefore overwrites
    rather than skipping what is already there, because on a reinstall or an
    upgrade every one of those files is the PREVIOUS version's. Skipping
    because the target existed is the defect that once left a 3.0.0 install
    whose splash reported 2.9.0.

    A missing archive is not fatal: whatever is already installed is left alone
    rather than a working install being broken. An extraction that fails is
    fatal, because the alternative is reporting success over a stale install.

    Every member is resolved against the install directory before it is
    written, so an archive entry that climbs out of the target is refused
    rather than followed.
    """
    target = installed_exe(install_dir)
    source = bundled_runtime_archive()
    if source is None:
        return target if target.is_file() else None

    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source) as archive:
            members = [entry for entry in archive.infolist() if not entry.is_dir()]
            for index, entry in enumerate(members, start=1):
                destination = safe_destination(
                    install_dir, install_dir / entry.filename
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as reader, destination.open("wb") as writer:
                    shutil.copyfileobj(reader, writer)
                report(
                    progress,
                    scaled(index, len(members), RUNTIME_START_PCT, RUNTIME_END_PCT),
                    RUNTIME_MESSAGE,
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise RuntimeExeError(RUNTIME_EXE_FAILED_MESSAGE.format(target=target)) from exc
    return target if target.is_file() else None


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

    report(progress, RUNTIME_START_PCT, RUNTIME_MESSAGE)
    exe_path = extract_runtime(target, progress=progress)

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
    the installer put down; the Run entry is a preference rather than part
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
