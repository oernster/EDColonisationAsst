"""Progress reporting for the long-running installer operations.

An install copies every file in the payload and an uninstall removes them
again, so both report their phase and a percentage rather than freezing behind
a single status line. The file copy is by far the longest phase, so it is given
a span of its own to report within rather than a single milestone, and the
per-file granularity the original installer had is preserved inside that span.
The callback is optional throughout: the operations are callable headlessly
with no reporter attached. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

from collections.abc import Callable

# A reporter receives a percentage and the message describing the current phase.
ProgressCallback = Callable[[int, str], None]

MINIMUM_PCT = 0
COMPLETE_PCT = 100

# Install phases, in the order they run. The copy reports continuously between
# its start and end; the rest are single milestones.
COUNT_PCT = 2
COUNT_MESSAGE = "Counting files..."
COPY_START_PCT = 5
COPY_END_PCT = 60
COPY_MESSAGE = "Copying files..."
RUNTIME_PCT = 68
RUNTIME_MESSAGE = "Placing the application..."
UNINSTALLER_PCT = 75
UNINSTALLER_MESSAGE = "Writing the uninstaller..."
REGISTER_PCT = 82
REGISTER_MESSAGE = "Registering the application..."
SHORTCUTS_PCT = 90
SHORTCUTS_MESSAGE = "Creating shortcuts..."
SETTINGS_PCT = 96
SETTINGS_MESSAGE = "Applying settings..."

# Uninstall phases.
REMOVE_SHORTCUTS_PCT = 10
REMOVE_SHORTCUTS_MESSAGE = "Removing shortcuts..."
REMOVE_REGISTRY_PCT = 20
REMOVE_REGISTRY_MESSAGE = "Removing registry entries..."
DELETE_START_PCT = 25
DELETE_END_PCT = 95
DELETE_MESSAGE = "Removing files..."

DONE_MESSAGE = "Done."


def report(callback: ProgressCallback | None, pct: int, message: str) -> None:
    """Send one progress update, doing nothing when no reporter is attached."""
    if callback is None:
        return
    callback(pct, message)


def scaled(done: int, total: int, start: int, end: int) -> int:
    """Return the percentage for ``done`` of ``total`` within a phase's span.

    A total of zero reports the end of the phase: there is nothing to wait for,
    so the phase is already complete.
    """
    if total <= 0:
        return end
    return start + ((end - start) * done) // total
