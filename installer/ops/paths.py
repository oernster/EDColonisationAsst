"""The per-user locations the installer reads and writes.

Everything lives under the current user's profile, so no step of the install
needs administrator rights. The locations come from environment variables
rather than from hardcoded profile paths, which is what lets the test suite
redirect the whole profile into a temporary tree. British spelling is used in
comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from installer.constants import (
    APP_ID,
    APP_SHORT_NAME,
    DESKTOP_DIR_NAME,
    ENV_APPDATA,
    ENV_LOCALAPPDATA,
    ENV_PROGRAM_FILES,
    ENV_PROGRAM_FILES_X86,
    ENV_USERPROFILE,
    EXE_NAME,
    EXE_SUFFIX,
    LINUX_SHARE_SUBPATH,
    MAC_APPS_DIR_NAME,
    MACOS_PLATFORM,
    NUITKA_ONEFILE_ENV,
    SHORTCUT_EXT,
    START_MENU_SUBPATH,
    UNINSTALLER_NAME,
    UNINSTALLER_SUBDIR,
    WINDOWS_PREFIX,
)

_LOCAL_APPDATA_FALLBACK = ("AppData", "Local")
_KIB = 1024


def is_windows() -> bool:
    """Return True when running on Windows."""
    return sys.platform.startswith(WINDOWS_PREFIX)


def is_macos() -> bool:
    """Return True when running on macOS."""
    return sys.platform == MACOS_PLATFORM


def _local_appdata() -> Path:
    """Return %LOCALAPPDATA%, falling back to its conventional location."""
    base = os.environ.get(ENV_LOCALAPPDATA)
    if base:
        return Path(base)
    appdata = os.environ.get(ENV_APPDATA)
    if appdata:
        return Path(appdata).parent / _LOCAL_APPDATA_FALLBACK[-1]
    return Path.home().joinpath(*_LOCAL_APPDATA_FALLBACK)


def _user_profile() -> Path:
    """Return the user's home directory, honouring %USERPROFILE% when set."""
    profile = os.environ.get(ENV_USERPROFILE)
    if profile:
        return Path(profile)
    return Path.home()


def install_target() -> Path:
    """Return the per-user install directory for the current platform."""
    if is_windows():
        return _local_appdata() / APP_ID
    if is_macos():
        return Path.home() / MAC_APPS_DIR_NAME / APP_ID
    return Path.home().joinpath(*LINUX_SHARE_SUBPATH) / APP_ID


def installed_exe(install_dir: Path) -> Path:
    """Return the application executable inside an install directory."""
    return install_dir / EXE_NAME


def uninstaller_path(install_dir: Path) -> Path:
    """Return where the registered uninstaller copy lives under an install."""
    return install_dir / UNINSTALLER_SUBDIR / UNINSTALLER_NAME


def desktop_link() -> Path:
    """Return the per-user Desktop shortcut path."""
    return _user_profile() / DESKTOP_DIR_NAME / f"{APP_SHORT_NAME}{SHORTCUT_EXT}"


def start_menu_link() -> Path | None:
    """Return the Start Menu shortcut path, or None when APPDATA is unset."""
    appdata = os.environ.get(ENV_APPDATA)
    if not appdata:
        return None
    programs = Path(appdata).joinpath(*START_MENU_SUBPATH)
    folder = programs / APP_SHORT_NAME
    return folder / f"{APP_SHORT_NAME}{SHORTCUT_EXT}"


def is_under_program_files(path: Path) -> bool:
    """Return True when a path sits under a Program Files directory.

    A previous installation recorded there cannot be written to without
    elevation, so it is never adopted as the default install location.
    """
    if not is_windows():
        return False
    try:
        resolved = path.resolve()
    except OSError:  # pragma: no cover
        # Defensive: resolve() does not raise for a path read back out of the
        # registry in this environment. An unresolvable path is treated as not
        # under Program Files, which is the direction that keeps the install
        # location the user's own choice.
        return False
    for variable in (ENV_PROGRAM_FILES, ENV_PROGRAM_FILES_X86):
        base = os.environ.get(variable)
        if not base:
            continue
        if resolved.is_relative_to(Path(base)):
            return True
    return False


def launcher_candidates() -> tuple[str, ...]:
    """Return the places the original launcher's path may be found, in order."""
    return (
        os.environ.get(NUITKA_ONEFILE_ENV, ""),
        sys.argv[0] if sys.argv else "",
    )


def original_installer_exe(
    candidates: tuple[str, ...] | None = None,
    temp_root: Path | None = None,
) -> Path:
    """Return the setup executable the user actually launched.

    Under a Nuitka onefile build ``sys.executable`` is the unpacked temporary
    bootstrap rather than the launcher, and registering that as the uninstaller
    would record a path that disappears when the process exits. The real
    launcher is exposed through NUITKA_ONEFILE_BINARY and as ``sys.argv[0]``,
    so those are preferred and ``sys.executable`` is the last resort.
    """
    root = (
        temp_root.resolve()
        if temp_root is not None
        else Path(tempfile.gettempdir()).resolve()
    )
    sources = candidates if candidates is not None else launcher_candidates()
    for raw in sources:
        if not raw:
            continue
        try:
            path = Path(raw).resolve()
        except OSError:  # pragma: no cover
            # Defensive: resolve() does not raise for any malformed value this
            # environment can produce, so no test can reach this. A candidate
            # that cannot be resolved is skipped rather than allowed to fail
            # the install.
            continue
        if path.suffix.lower() != EXE_SUFFIX or not path.is_file():
            continue
        if path == root or root in path.parents:
            continue
        return path
    return Path(sys.executable)


def running_from_inside(install_dir: Path) -> bool:
    """Return True when this process's executable lives inside ``install_dir``.

    A path that cannot be resolved answers True, which is the safe direction:
    the caller then defers the deletion instead of attempting it in place.
    """
    try:
        running = Path(sys.executable).resolve()
        root = install_dir.resolve()
    except OSError:  # pragma: no cover
        # Defensive: resolve() does not raise for any path this environment can
        # produce, so no test can reach this. It is kept because answering True
        # defers the deletion, which is the safe direction.
        return True
    return running == root or root in running.parents


def directory_size_kb(path: Path) -> int | None:
    """Return the total size of a directory in KiB, or None when unreadable.

    A path that is not a directory walks to nothing and reports zero, which is
    the honest answer for an install that is not there.
    """
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:  # pragma: no cover
        # Defensive: the walk swallows a missing or non-directory path, so this
        # fires only if a file vanishes between being listed and being sized.
        return None
    return total // _KIB
