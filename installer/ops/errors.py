"""The installer's typed exception hierarchy.

Every failure the setup program reports to the user is one of these, so the UI
can render a message without inspecting exception text. British spelling is used
in comments. No em dashes appear anywhere.
"""

from __future__ import annotations


class InstallerError(Exception):
    """Base class for every failure raised by the installer operations."""


class PayloadError(InstallerError):
    """The bundled application payload is missing or cannot be read.

    A payload that cannot be found is fatal rather than something to work
    around. The previous behaviour fell back to the project root, which after
    the move into a subpackage would have deployed the installer's own sources
    over the user's installation.
    """


class UnsafePayloadEntryError(PayloadError):
    """A payload entry would be written outside the install directory.

    The payload is staged by this project's own tooling, so this should never
    fire; it is the guard that makes that guarantee enforced rather than
    assumed, since the copy runs with the user's full privileges.
    """


class RuntimeExeError(InstallerError):
    """The runtime executable could not be written into the install directory.

    Raised rather than tolerated. This is the only path that delivers the
    application binary, so an install that swallows a failure here leaves the
    PREVIOUS version on disk with every data file around it updated, then
    reports success. That is not a degraded install; it is a wrong one that
    looks right, which cost a release cycle to spot.
    """


class AppRunningError(InstallerError):
    """The application is running, so its files cannot be replaced or removed."""


class AppStillRunningError(AppRunningError):
    """The application was asked to close but was still running afterwards."""
