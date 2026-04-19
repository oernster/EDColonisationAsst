"""In-process change notification bus for AJAX long-polling.

This replaces the WebSocket broadcast mechanism.

The backend maintains a monotonically increasing sequence number. Whenever
journal ingestion updates persistent state, it increments the sequence and
wakes any clients waiting on the long-poll endpoint.

This is intentionally in-memory. If the backend restarts, the sequence resets
and clients will refetch on their next poll.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeSnapshot:
    seq: int
    changed: bool


class ChangeBus:
    def __init__(self) -> None:
        self._seq = 0
        self._cond = asyncio.Condition()

    @property
    def seq(self) -> int:
        return self._seq

    async def bump(self) -> int:
        """Increment the change sequence and wake any waiters."""
        async with self._cond:
            self._seq += 1
            self._cond.notify_all()
            return self._seq

    async def wait_for_change(self, *, since: int, timeout_s: float) -> ChangeSnapshot:
        """Wait until the sequence advances beyond `since`, or timeout."""
        if self._seq > since:
            return ChangeSnapshot(seq=self._seq, changed=True)

        async with self._cond:
            if self._seq > since:
                return ChangeSnapshot(seq=self._seq, changed=True)

            async def _wait() -> None:
                await self._cond.wait_for(lambda: self._seq > since)

            try:
                await asyncio.wait_for(_wait(), timeout=timeout_s)
                return ChangeSnapshot(seq=self._seq, changed=True)
            except TimeoutError:
                return ChangeSnapshot(seq=self._seq, changed=False)


# Global singleton used by API routes.
change_bus = ChangeBus()

