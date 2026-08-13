"""
Where the application may write its own files.

Every packaged runtime needs somewhere to keep the things it produces: the
colonisation database, the recorded update state, the runtime log. The install
directory is not that place on every platform. Windows installs per user and is
writable; a flatpak mounts ``/app`` read-only; a distribution package puts the
application somewhere only root can touch.

This module is the single answer to that question, so the choice is made once
rather than in each module that happens to need a file. It reports a directory
and never creates it; the caller that writes there is the caller that knows
whether a failure to create it is fatal.

The sandbox needs no special case. Flatpak sets ``XDG_DATA_HOME`` to the
application's own data directory under ``~/.var/app``, which is one of the few
places the sandbox may write, so honouring XDG is the whole of the fix.
"""

from __future__ import annotations

import os
from pathlib import Path

# The per-user directory the application owns, under whichever base the platform
# gives it. The same name on every platform, so a user who moves between them
# recognises it.
APP_DIR_NAME = "EDColonisationAsst"

# Windows names its per-user data location here. Checked first because it is the
# platform where the application has actually shipped; a Windows machine sets it
# in every session.
_ENV_LOCAL_APPDATA = "LOCALAPPDATA"

# The XDG base directory specification's data location, which flatpak points at
# the sandbox's own writable directory.
_ENV_XDG_DATA_HOME = "XDG_DATA_HOME"

# What the specification says to use when XDG_DATA_HOME is unset, expressed as
# path segments so no separator is hardcoded.
_XDG_DATA_FALLBACK = (".local", "share")


def user_data_dir() -> Path:
    """Return the per-user directory this application may write into.

    Resolution order:

    1. ``%LOCALAPPDATA%\\EDColonisationAsst`` when LOCALAPPDATA is set, which is
       what the Windows runtime has always used and what keeps an existing
       installation's database exactly where it is.
    2. ``$XDG_DATA_HOME/EDColonisationAsst`` when that is set, which covers a
       flatpak, where it points inside the sandbox's writable data directory.
    3. ``~/.local/share/EDColonisationAsst``, the specification's own default.

    The directory is not created here. A caller that cannot proceed without it
    creates it and reports its own failure; a caller for which the write is a
    convenience, the runtime log being the example, lets the write fail quietly.
    """
    local_appdata = os.environ.get(_ENV_LOCAL_APPDATA)
    if local_appdata:
        return Path(local_appdata) / APP_DIR_NAME

    data_home = os.environ.get(_ENV_XDG_DATA_HOME)
    if data_home:
        return Path(data_home) / APP_DIR_NAME

    return Path.home().joinpath(*_XDG_DATA_FALLBACK) / APP_DIR_NAME
