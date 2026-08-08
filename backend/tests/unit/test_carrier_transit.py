"""Tests for the carrier transit derivation.

The rules pinned here were settled by measuring the real journals, not by
reading the schema. Two of them are worth stating outright, because both are
cases where the obvious implementation is wrong:

- Arrival must match the destination SystemAddress. The game writes a
  CarrierLocation for the carrier's *current* system when the commander logs
  in, and one such event lands inside a pending jump window in the journals,
  so accepting "any later CarrierLocation" would clear a live transit.
- A booked jump that the application never saw finish has to expire against
  the wall clock, because the journal simply stops when the game is closed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.src.models.carriers import CarrierTransitState
from backend.src.models.journal_events import (
    CarrierJumpCancelledEvent,
    CarrierJumpRequestEvent,
    CarrierLocationEvent,
    CarrierStatsEvent,
    JournalEvent,
)
from backend.src.services.carrier_transit import (
    ARRIVAL_GRACE,
    derive_carrier_transit,
)

CARRIER_ID = 3700569600
OTHER_CARRIER_ID = 1234567890

ORIGIN_ADDRESS = 2278253693331
DESTINATION_ADDRESS = 3274669295979
DESTINATION = "Fong Wang"
DESTINATION_BODY = "Fong Wang 4"

REQUESTED_AT = datetime(2026, 6, 16, 19, 53, 56, tzinfo=UTC)
DEPARTS_AT = datetime(2026, 6, 16, 20, 9, 10, tzinfo=UTC)


def _request(
    *,
    carrier_id: int = CARRIER_ID,
    stamp: datetime = REQUESTED_AT,
    departure: datetime | None = DEPARTS_AT,
    body: str | None = DESTINATION_BODY,
) -> CarrierJumpRequestEvent:
    """A booked jump to the destination system."""
    return CarrierJumpRequestEvent(
        timestamp=stamp,
        event="CarrierJumpRequest",
        carrier_id=carrier_id,
        system_name=DESTINATION,
        system_address=DESTINATION_ADDRESS,
        body=body,
        departure_time=departure,
    )


def _cancelled(
    *,
    carrier_id: int = CARRIER_ID,
    stamp: datetime,
) -> CarrierJumpCancelledEvent:
    """An abandoned jump."""
    return CarrierJumpCancelledEvent(
        timestamp=stamp,
        event="CarrierJumpCancelled",
        carrier_id=carrier_id,
    )


def _location(
    *,
    carrier_id: int = CARRIER_ID,
    stamp: datetime,
    address: int = DESTINATION_ADDRESS,
    system: str = DESTINATION,
) -> CarrierLocationEvent:
    """The carrier being seen in a system."""
    return CarrierLocationEvent(
        timestamp=stamp,
        event="CarrierLocation",
        carrier_id=carrier_id,
        star_system=system,
        system_address=address,
    )


def test_no_jump_history_is_not_the_same_as_parked() -> None:
    """None says the journals cannot answer, which the UI shows as nothing."""
    events: list[JournalEvent] = [_location(stamp=REQUESTED_AT)]

    assert derive_carrier_transit(events, CARRIER_ID) is None


def test_a_booked_jump_reads_as_in_transit() -> None:
    """With no arrival and no cancel, the jump is still outstanding."""
    transit = derive_carrier_transit([_request()], CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT
    assert transit.destination_system == DESTINATION
    assert transit.destination_body == DESTINATION_BODY
    assert transit.departure_time == DEPARTS_AT


def test_arriving_at_the_destination_ends_the_transit() -> None:
    """A CarrierLocation at the requested address is the arrival."""
    events: list[JournalEvent] = [
        _request(),
        _location(stamp=DEPARTS_AT),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.PARKED
    assert transit.destination_system is None


def test_a_login_in_the_origin_system_does_not_clear_the_transit() -> None:
    """The case the journals proved: match the address, not merely the time.

    Logging in during the pending window writes a CarrierLocation for where
    the carrier still is. Treating that as an arrival would report the jump
    finished a quarter of an hour before it happened.
    """
    events: list[JournalEvent] = [
        _request(),
        _location(
            stamp=REQUESTED_AT + timedelta(minutes=2),
            address=ORIGIN_ADDRESS,
            system="Lupus Dark Region BQ-Y d66",
        ),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT
    assert transit.destination_system == DESTINATION


def test_cancelling_returns_the_carrier_to_parked() -> None:
    """A cancel after the request abandons it."""
    events: list[JournalEvent] = [
        _request(),
        _cancelled(stamp=REQUESTED_AT + timedelta(minutes=1)),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.PARKED


def test_an_older_cancel_does_not_touch_a_newer_request() -> None:
    """Only the newest request can be outstanding, so order decides."""
    events: list[JournalEvent] = [
        _cancelled(stamp=REQUESTED_AT - timedelta(hours=2)),
        _request(),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_another_carriers_events_are_ignored() -> None:
    """A squadron mate's carrier must not cancel or complete this one's jump."""
    events: list[JournalEvent] = [
        _request(),
        _cancelled(
            carrier_id=OTHER_CARRIER_ID, stamp=REQUESTED_AT + timedelta(minutes=1)
        ),
        _location(
            carrier_id=OTHER_CARRIER_ID, stamp=REQUESTED_AT + timedelta(minutes=2)
        ),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_a_jump_still_pending_before_departure_survives_the_clock() -> None:
    """The wall clock only retires a jump once the grace period is spent."""
    transit = derive_carrier_transit(
        [_request()],
        CARRIER_ID,
        now=DEPARTS_AT + ARRIVAL_GRACE - timedelta(minutes=1),
    )

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_a_jump_the_application_never_saw_finish_expires() -> None:
    """Booking a jump then quitting must not read as in transit forever."""
    transit = derive_carrier_transit(
        [_request()],
        CARRIER_ID,
        now=DEPARTS_AT + ARRIVAL_GRACE + timedelta(minutes=1),
    )

    assert transit is not None
    assert transit.state is CarrierTransitState.PARKED


def test_the_clock_cannot_expire_a_jump_with_no_departure_time() -> None:
    """Older journals omit DepartureTime, which costs the guard, not the state."""
    transit = derive_carrier_transit(
        [_request(departure=None)],
        CARRIER_ID,
        now=DEPARTS_AT + timedelta(days=30),
    )

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT
    assert transit.departure_time is None


def test_without_a_clock_the_derivation_rests_on_events_alone() -> None:
    """Omitting now leaves the expiry guard inactive."""
    transit = derive_carrier_transit([_request()], CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_a_naive_clock_is_read_as_utc() -> None:
    """Comparing an aware journal stamp with a naive now would otherwise raise."""
    transit = derive_carrier_transit(
        [_request()],
        CARRIER_ID,
        now=(DEPARTS_AT + ARRIVAL_GRACE + timedelta(minutes=1)).replace(tzinfo=None),
    )

    assert transit is not None
    assert transit.state is CarrierTransitState.PARKED


def test_a_naive_departure_time_is_read_as_utc() -> None:
    """The same, for a caller that built the event without a timezone."""
    transit = derive_carrier_transit(
        [_request(departure=DEPARTS_AT.replace(tzinfo=None))],
        CARRIER_ID,
        now=DEPARTS_AT + ARRIVAL_GRACE + timedelta(minutes=1),
    )

    assert transit is not None
    assert transit.state is CarrierTransitState.PARKED


def test_a_location_before_the_request_is_not_an_arrival() -> None:
    """The carrier having been there before says nothing about this jump."""
    events: list[JournalEvent] = [
        _location(stamp=REQUESTED_AT - timedelta(days=1)),
        _request(),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_unrelated_events_in_the_stream_are_stepped_over() -> None:
    """The stream carries every event type, not only the three that matter."""
    events: list[JournalEvent] = [
        CarrierStatsEvent(
            timestamp=REQUESTED_AT,
            event="CarrierStats",
            carrier_id=CARRIER_ID,
            name="MIDNIGHT ELOQUENCE",
        ),
        _request(),
        CarrierStatsEvent(
            timestamp=DEPARTS_AT,
            event="CarrierStats",
            carrier_id=CARRIER_ID,
            name="MIDNIGHT ELOQUENCE",
        ),
    ]

    transit = derive_carrier_transit(events, CARRIER_ID)

    assert transit is not None
    assert transit.state is CarrierTransitState.IN_TRANSIT


def test_each_parked_result_is_its_own_object() -> None:
    """A shared instance would let one caller's edit reach every carrier."""
    events: list[JournalEvent] = [
        _request(),
        _cancelled(stamp=REQUESTED_AT + timedelta(minutes=1)),
    ]

    first = derive_carrier_transit(events, CARRIER_ID)
    second = derive_carrier_transit(events, CARRIER_ID)

    assert first is not None
    assert second is not None
    assert first is not second
