"""The setup program's command line.

The only caller that passes arguments is Windows itself: the UninstallString
recorded in the registry re-invokes a copy of this program with --uninstall,
and the ModifyPath re-invokes it with none. The quiet flag exists so that same
entry point can run headlessly. British spelling is used in comments. No em
dashes appear anywhere.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from installer.constants import APP_DISPLAY_NAME, UNINSTALL_FLAG

_QUIET_FLAG = "--quiet"
_STORE_TRUE = "store_true"

DESCRIPTION = f"Set up {APP_DISPLAY_NAME}."
UNINSTALL_HELP = "remove an existing installation instead of showing the window"
QUIET_HELP = "run the requested action with no window at all"


@dataclass(frozen=True, slots=True)
class Options:
    """The parsed command line."""

    uninstall: bool
    quiet: bool


def build_parser() -> argparse.ArgumentParser:
    """Return the parser, which also provides the --help output."""
    parser = argparse.ArgumentParser(description=DESCRIPTION, add_help=True)
    parser.add_argument(
        UNINSTALL_FLAG, dest="uninstall", action=_STORE_TRUE, help=UNINSTALL_HELP
    )
    parser.add_argument(_QUIET_FLAG, action=_STORE_TRUE, help=QUIET_HELP)
    return parser


def parse_args(argv: list[str]) -> Options:
    """Parse the installer command line into an immutable Options."""
    parsed = build_parser().parse_args(argv)
    return Options(uninstall=parsed.uninstall, quiet=parsed.quiet)
