"""Coverage tests for src.services.change_bus.

These tests exercise every path through ChangeBus without any mocking
libraries: real asyncio primitives drive the condition variable and the
long-poll wait logic.
"""

from __future__ import annotations

import asyncio

from src.services.change_bus import ChangeBus, ChangeSnapshot, change_bus


async def test_seq_property_and_bump_increment() -> None:
    """seq starts at zero and bump increments it while returning the new value."""
    bus = ChangeBus()
    assert bus.seq == 0

    new_seq = await bus.bump()
    assert new_seq == 1
    assert bus.seq == 1


async def test_wait_for_change_fast_path_returns_immediately() -> None:
    """When the sequence already advanced past `since` no waiting occurs."""
    bus = ChangeBus()
    await bus.bump()

    snapshot = await bus.wait_for_change(since=0, timeout_s=0.01)
    assert snapshot == ChangeSnapshot(seq=1, changed=True)


async def test_wait_for_change_recheck_under_lock_detects_advance() -> None:
    """A bump that lands while the waiter is acquiring the lock is detected.

    We hold the condition lock so the waiter blocks on acquisition, advance
    the sequence while the lock is held, then release. The waiter must see
    the advance in its post-acquisition recheck rather than blocking.
    """
    bus = ChangeBus()

    await bus._cond.acquire()
    waiter = asyncio.create_task(bus.wait_for_change(since=0, timeout_s=5.0))
    # Let the waiter run until it blocks on the condition lock.
    await asyncio.sleep(0)
    # Advance the sequence while we still hold the lock; this mirrors what
    # bump does but happens before the waiter can proceed.
    bus._seq = 1
    bus._cond.release()

    snapshot = await waiter
    assert snapshot.changed is True
    assert snapshot.seq == 1


async def test_wait_for_change_wakes_on_bump() -> None:
    """A waiter parked inside wait_for is woken by a concurrent bump."""
    bus = ChangeBus()

    waiter = asyncio.create_task(bus.wait_for_change(since=0, timeout_s=5.0))
    # Give the waiter time to reach the condition wait.
    await asyncio.sleep(0.01)

    await bus.bump()

    snapshot = await waiter
    assert snapshot.changed is True
    assert snapshot.seq == 1


async def test_wait_for_change_times_out_without_change() -> None:
    """With no bump the wait times out and reports changed False."""
    bus = ChangeBus()

    snapshot = await bus.wait_for_change(since=0, timeout_s=0.01)
    assert snapshot.changed is False
    assert snapshot.seq == 0


def test_module_level_singleton_exists() -> None:
    """The module exposes a shared ChangeBus singleton for API routes."""
    assert isinstance(change_bus, ChangeBus)
