"""Tests for the carrier balance history.

This exists in place of the thing actually wanted, an upkeep bill, which the
journal does not record and which cannot be inferred: measured across six
months of real journals the reserve balance never moved once, and of seventy
downward movements not one fell on a weekly cadence. So what is pinned here is
that the history reports only what was observed, attaches no cause to any
movement, and is honest about the window it saw.

The other rule under test is that only MOVEMENTS are kept. The game writes the
same balance hundreds of times per session, and a list of unchanged numbers
tells a commander nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.src.models.journal_events import CarrierStatsEvent, JournalEvent
from backend.src.services.carrier_balance import derive_balance_history

CARRIER_ID = 3700569600
OTHER_CARRIER_ID = 1234567890
START = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _stats(
    minutes: int,
    balance: int | None,
    *,
    carrier_id: int = CARRIER_ID,
    finance: bool = True,
) -> CarrierStatsEvent:
    """A CarrierStats event reporting the given balance."""
    raw: dict[str, object] = {"CarrierID": carrier_id}
    if finance:
        block: dict[str, object] = {}
        if balance is not None:
            block["CarrierBalance"] = balance
        raw["Finance"] = block

    return CarrierStatsEvent(
        timestamp=START + timedelta(minutes=minutes),
        event="CarrierStats",
        carrier_id=carrier_id,
        name="MIDNIGHT ELOQUENCE",
        raw_data=raw,
    )


def test_no_readings_is_not_a_balance_of_zero() -> None:
    """An unseen carrier has no history, which is not the same as broke."""
    history = derive_balance_history([], CARRIER_ID)

    assert history.current_balance is None
    assert history.entries == []
    assert history.net_change is None
    assert history.movements == 0


def test_repeated_identical_readings_are_not_movements() -> None:
    """The game writes the same balance over and over; none of it is news."""
    events: list[JournalEvent] = [
        _stats(0, 1_000_000),
        _stats(5, 1_000_000),
        _stats(10, 1_000_000),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.movements == 0
    assert history.entries == []
    assert history.current_balance == 1_000_000
    assert history.net_change == 0


def test_a_movement_records_its_direction_and_size() -> None:
    """Money leaving is negative, which is the point of a signed change."""
    events: list[JournalEvent] = [
        _stats(0, 1_000_000),
        _stats(10, 750_000),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.movements == 1
    entry = history.entries[0]
    assert entry.change == -250_000
    assert entry.balance == 750_000
    assert entry.recorded_at == START + timedelta(minutes=10)


def test_movements_are_newest_first() -> None:
    """The recent few are what gets read, so they come first."""
    events: list[JournalEvent] = [
        _stats(0, 1_000),
        _stats(10, 2_000),
        _stats(20, 3_000),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert [entry.balance for entry in history.entries] == [3_000, 2_000]


def test_the_kept_entries_are_capped_but_the_count_is_not() -> None:
    """A truncated list must not understate how much happened."""
    events: list[JournalEvent] = [_stats(i, 1_000 + i) for i in range(20)]

    history = derive_balance_history(events, CARRIER_ID, limit=5)

    assert len(history.entries) == 5
    assert history.movements == 19
    # Capped from the newest end, not the oldest.
    assert history.entries[0].balance == 1_019


def test_the_observed_window_is_reported() -> None:
    """The journal is only written while playing, so the window matters."""
    events: list[JournalEvent] = [
        _stats(0, 1_000),
        _stats(120, 4_000),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.observed_from == START
    assert history.observed_to == START + timedelta(minutes=120)
    assert history.net_change == 3_000


def test_another_carriers_balance_is_not_counted() -> None:
    """A squadron mate's carrier is not this carrier's money."""
    events: list[JournalEvent] = [
        _stats(0, 1_000),
        _stats(10, 999_999, carrier_id=OTHER_CARRIER_ID),
        _stats(20, 2_000),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.current_balance == 2_000
    assert history.movements == 1


def test_an_event_with_no_finance_block_is_skipped() -> None:
    """Older journals omit it, and a missing balance is not a zero one."""
    events: list[JournalEvent] = [
        _stats(0, 1_000),
        _stats(10, None, finance=False),
        _stats(20, 1_500),
    ]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.movements == 1
    assert history.current_balance == 1_500


def test_a_finance_block_without_a_balance_is_skipped() -> None:
    """Present but silent on the balance is still no reading."""
    events: list[JournalEvent] = [_stats(0, None)]

    history = derive_balance_history(events, CARRIER_ID)

    assert history.current_balance is None


def test_a_flag_where_a_balance_belongs_is_not_one_credit() -> None:
    """True counts as 1 in Python, which would read as a bankrupt carrier."""
    events: list[JournalEvent] = [_stats(0, 1_000)]
    events[0].raw_data["Finance"] = {"CarrierBalance": True}

    history = derive_balance_history(events, CARRIER_ID)

    assert history.current_balance is None


def test_a_finance_block_of_the_wrong_shape_is_skipped() -> None:
    """Same defence as everywhere else in the carrier domain."""
    events: list[JournalEvent] = [_stats(0, 1_000)]
    events[0].raw_data["Finance"] = "unavailable"

    history = derive_balance_history(events, CARRIER_ID)

    assert history.current_balance is None
