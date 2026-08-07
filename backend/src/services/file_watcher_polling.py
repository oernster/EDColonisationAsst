"""The journal polling fallback, kept beside the watcher that mixes it in.

`FileWatcher` prefers watchdog and falls back to polling in the packaged
runtime, where OS notification APIs have proved unreliable. That fallback is a
self-contained capability: a task, an interval and three pieces of last-seen
state. It lives here as a mixin rather than a collaborator so the state stays
on the watcher instance, which is where the status endpoint and the tests
already look for it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC
from pathlib import Path

from ..utils.logger import get_logger
from ..utils.runtime import is_frozen

logger = get_logger(__name__)


class PollingFallbackMixin:
    """Polling half of :class:`FileWatcher`.

    Reads and writes ``_poll_*`` attributes and ``_handler``, all of which the
    watcher's ``__init__`` owns.
    """

    def _start_polling_if_enabled(self, directory: Path) -> None:
        """Start the polling fallback task (packaged runtime only)."""
        # Only enable in frozen runtime to avoid duplicate work during dev.
        if not is_frozen():
            return
        if self._poll_task is not None and not self._poll_task.done():
            return

        try:
            self._poll_task = asyncio.create_task(
                self._poll_for_latest_changes(directory),
                name="edca-journal-poller",
            )
            logger.info(
                "Started journal polling fallback (interval=%ss) for %s",
                self._poll_interval_s,
                directory,
            )
        except Exception:
            # Polling is best-effort; watchdog remains the primary mechanism.
            logger.exception("Failed to start polling fallback")

    async def _poll_for_latest_changes(self, directory: Path) -> None:
        """Periodically process the newest Journal.*.log when it changes."""
        # Small epsilon to avoid float edge cases.
        epsilon = 1e-6
        while True:
            try:
                # Diagnostics: remember we are alive.
                try:
                    from datetime import datetime

                    self._poll_last_checked_at = datetime.now(UTC).isoformat()
                except Exception:  # noqa: BLE001, S110
                    # Deliberately broad. This only stamps a last-checked time for
                    # diagnostics; the poll itself has already done its work.
                    pass

                journal_files = list(directory.glob("Journal.*.log"))
                if journal_files:
                    # Newest file by modified time.
                    latest = max(journal_files, key=lambda p: p.stat().st_mtime)
                    latest_mtime = latest.stat().st_mtime

                    prev, prev_t = self._poll_last_path, self._poll_last_mtime
                    stale = prev_t is not None and latest_mtime > prev_t + epsilon
                    changed = prev is None or prev_t is None or latest != prev or stale

                    if changed and self._handler is not None:
                        self._poll_last_path = latest
                        self._poll_last_mtime = latest_mtime
                        self._poll_last_error = None
                        await self._handler._process_file(latest)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Deliberately broad, around one poll iteration. This stats journal
                # files that the game is actively writing, so a file vanishing mid-scan
                # is normal. The loop must survive it and try again.
                logger.exception("Polling fallback encountered an error")
                try:
                    self._poll_last_error = (
                        "Polling fallback encountered an error; see logs"
                    )
                except Exception:  # noqa: BLE001, S110
                    # Deliberately broad. This records the error text for the status
                    # endpoint; failing to record it must not end the polling loop.
                    pass

            await asyncio.sleep(self._poll_interval_s)
