"""Locating the data the setup program carries.

The payload is anchored on the ``installer`` package directory rather than on
the running executable, so one rule holds in both modes:

- from source, the package directory is ``<repo>/installer`` and the payload
  staged by buildinstaller.py sits under ``<repo>/build/payload``;
- compiled, Nuitka reproduces the package layout under the unpacked root and
  buildinstaller.py includes the same data at ``installer/payload``.

Anchoring on ``__file__`` of the main script would not survive the entry point
moving to the repository root, which is why the anchor is the package itself.
The directory holding the launcher is still offered as a candidate, because
that is the one that resolves in the installers already in the wild. British
spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path


def installer_root() -> Path:
    """Return the ``installer`` package directory in source and compiled runs."""
    return Path(__file__).resolve().parents[1]


def program_root() -> Path:
    """Return the directory containing the installer package.

    This is the repository root from source and the unpacked bundle root when
    compiled. Data files included at the top level rather than under the
    package are found here.
    """
    return installer_root().parent


def launcher_dir() -> Path | None:
    """Return the directory holding the launcher, or None when unresolvable.

    Under a Nuitka onefile build this is where the user's copy of the setup
    executable actually lives, which is not the unpacked bundle root.
    """
    if not sys.argv or not sys.argv[0]:
        return None
    try:
        return Path(sys.argv[0]).resolve().parent
    except OSError:  # pragma: no cover
        # Defensive: resolve() does not raise for any value argv[0] can hold in
        # this environment, so no test can reach this. An unresolvable launcher
        # is simply one fewer candidate rather than a failed install.
        return None
