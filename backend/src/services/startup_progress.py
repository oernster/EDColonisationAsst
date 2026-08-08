"""What the backend is doing while the splash is still up.

The startup splash used to show an indeterminate bar: a barber pole that says
"something is happening" and nothing else. On a first run that is the wrong
answer twice over. It cannot say how far along the import is, and it cannot
say why a first run is slow at all when later runs are not.

Both are answerable. The first-run backfill lists every journal file before it
starts reading them, so the total count and the total size are known up front,
and the per-file loop already yields control between files. Publishing into
this tracker from that loop costs nothing and turns the bar determinate.

Shaped after change_bus: a module-level instance the API reads and the
ingestion writes. Unlike change_bus there is no async in it, because the
writer already holds the event loop and the reader is a plain GET.

The formatting lives here rather than in the splash because backend/src/runtime
is outside the coverage gate and this is the part with rules worth pinning:
what to say at each stage, and how to talk about a total of zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

BYTES_PER_MB = 1024 * 1024

# Below this, a size in megabytes rounds to something useless like "0 MB".
_SMALL_IMPORT_BYTES = BYTES_PER_MB

_PERCENT = 100


class StartupStage(str, Enum):
    """The coarse phases of getting the backend ready.

    Coarse on purpose: these exist to be read off a splash screen in passing,
    not to trace execution.
    """

    STARTING = "starting"
    IMPORTING_JOURNALS = "importing_journals"
    CATCHING_UP = "catching_up"
    READY = "ready"


@dataclass(frozen=True)
class StartupSnapshot:
    """An immutable reading of startup progress."""

    stage: StartupStage = StartupStage.STARTING
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0

    @property
    def percent(self) -> int | None:
        """Completion as a percentage, or None when it cannot be known.

        Measured in bytes rather than in files. Journal files vary in size by
        more than an order of magnitude, so counting files makes the bar lurch;
        counting bytes makes it move at something like a constant rate.
        """
        if self.bytes_total <= 0:
            return None
        ratio = self.bytes_done / self.bytes_total
        return max(0, min(_PERCENT, round(ratio * _PERCENT)))


def _megabytes(value: int) -> str:
    """Render a byte count for a splash screen, not for an audit."""
    return f"{round(value / BYTES_PER_MB)} MB"


def startup_progress_message(snapshot: StartupSnapshot) -> str | None:
    """The status line for this snapshot, or None when there is nothing to add.

    None means the caller should keep whatever it was already showing. The
    starting and ready stages both have perfectly good messages of their own
    on the splash, and overwriting them with a vaguer one helps nobody.
    """
    if snapshot.stage is StartupStage.CATCHING_UP:
        return "Catching up on your recent flights..."

    if snapshot.stage is not StartupStage.IMPORTING_JOURNALS:
        return None

    if snapshot.files_total <= 0:
        return "Reading your journals..."

    # The file being read, not the count already finished, so the line opens
    # at "1 of 72" rather than the "0 of 72" a completed count would show.
    # Clamped, so the last file does not read as one past the total.
    reading = min(snapshot.files_done + 1, snapshot.files_total)
    progress = f"Reading journal {reading} of {snapshot.files_total}"
    if snapshot.bytes_total < _SMALL_IMPORT_BYTES:
        # Rounding a small import to megabytes would read as "0 MB of 0 MB".
        return f"{progress}..."

    return (
        f"{progress} "
        f"({_megabytes(snapshot.bytes_done)} of {_megabytes(snapshot.bytes_total)})"
    )


def startup_explanation(snapshot: StartupSnapshot) -> str | None:
    """Why this is taking a moment, when there is a reason worth giving.

    Only the first-run import earns one. It is the single slow path, it is
    slow for a reason the user cannot guess, and it does not happen again.
    """
    if snapshot.stage is StartupStage.IMPORTING_JOURNALS:
        return (
            "First run only: building your colonisation history from the "
            "journals already on this machine."
        )
    return None


class StartupProgressTracker:
    """Records how far backend startup has got.

    Written from the ingestion path and read by the health endpoint. Plain
    attribute assignment throughout: every writer runs on the event loop, and
    a reader that catches a half-updated pair of counters shows one stale
    frame on a splash screen, which is not worth a lock.
    """

    def __init__(self) -> None:
        self._stage = StartupStage.STARTING
        self._files_done = 0
        self._files_total = 0
        self._bytes_done = 0
        self._bytes_total = 0

    def begin_import(self, file_sizes: list[int]) -> None:
        """Start the first-run import of the given files.

        Args:
            file_sizes: The size in bytes of every file about to be read, which
                the caller already has from listing them.
        """
        self._stage = StartupStage.IMPORTING_JOURNALS
        self._files_done = 0
        self._files_total = len(file_sizes)
        self._bytes_done = 0
        self._bytes_total = sum(file_sizes)

    def file_imported(self, size: int) -> None:
        """Record one file read, whether or not it parsed cleanly.

        A file that failed to parse still took its time and still moves the
        import along, so it counts. A bar that stalls on a bad file would be
        reporting the wrong thing.
        """
        self._files_done += 1
        self._bytes_done += max(0, size)

    def begin_catch_up(self) -> None:
        """Switch to the repeat-run path, which reads only the newest files."""
        self._stage = StartupStage.CATCHING_UP

    def finish(self) -> None:
        """Mark startup work complete."""
        self._stage = StartupStage.READY

    def snapshot(self) -> StartupSnapshot:
        """Take an immutable reading of where startup has got to."""
        return StartupSnapshot(
            stage=self._stage,
            files_done=self._files_done,
            files_total=self._files_total,
            bytes_done=self._bytes_done,
            bytes_total=self._bytes_total,
        )


# Read by the health endpoint, written by startup ingestion. Mirrors the
# change_bus singleton beside it.
startup_progress = StartupProgressTracker()


__all__ = [
    "StartupProgressTracker",
    "StartupSnapshot",
    "StartupStage",
    "startup_explanation",
    "startup_progress",
    "startup_progress_message",
]
