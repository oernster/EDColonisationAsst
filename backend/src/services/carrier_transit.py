"""Where a fleet carrier actually is, derived from its jump events.

A carrier is never docked anywhere. It is holding station in a star system,
or it is between two of them for the fifteen to twenty minutes a jump takes.
The journals never state which, so this module reconstructs it from three
events: `CarrierJumpRequest` opens a transit, `CarrierJumpCancelled` abandons
it, and a `CarrierLocation` at the requested system address closes it.

Two rules here were settled against the real journals rather than guessed,
and both matter:

- Arrival is matched on the destination SystemAddress, never on "any later
  CarrierLocation". The game writes a CarrierLocation for the carrier's
  *current* system when the commander logs in, so a login inside the pending
  window would otherwise clear a transit that is still running. That case is
  present in the journals; it is not hypothetical.
- The elapsed guard below exists for the opposite failure. Arrival is
  recorded reliably while the game is running, so the guard almost never
  fires; what it covers is the commander booking a jump and then quitting,
  which would otherwise leave the carrier reading as in transit forever.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ..models.carriers import CarrierTransit, CarrierTransitState
from ..models.journal_events import (
    CarrierJumpCancelledEvent,
    CarrierJumpRequestEvent,
    CarrierLocationEvent,
    JournalEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# How long after DepartureTime a transit is still believed without an arrival
# event to confirm it. Across the journals every recorded arrival landed within
# seven minutes of DepartureTime and almost all landed exactly on it, so this
# is well clear of normal behaviour and only catches a jump the application
# never saw finish.
ARRIVAL_GRACE = timedelta(minutes=15)


def _parked() -> CarrierTransit:
    """A fresh parked state.

    Built per call rather than shared: these models are mutable, and one
    instance handed to every carrier is one instance for a caller to edit.
    """
    return CarrierTransit(state=CarrierTransitState.PARKED)


def _as_utc(moment: datetime) -> datetime:
    """Return an aware UTC datetime, assuming UTC for a naive one.

    Journal timestamps are aware, but a caller building events by hand need
    not be, and comparing the two kinds raises.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _latest_jump_request(
    events: list[JournalEvent],
    carrier_id: int,
) -> CarrierJumpRequestEvent | None:
    """Return the most recent jump booked for this carrier, if any."""
    for event in reversed(events):
        if (
            isinstance(event, CarrierJumpRequestEvent)
            and event.carrier_id == carrier_id
        ):
            return event
    return None


def _was_cancelled(
    events: list[JournalEvent],
    carrier_id: int,
    request: CarrierJumpRequestEvent,
) -> bool:
    """Whether a cancellation for this carrier post-dates the request.

    Only the newest request can be outstanding, so time order is all that is
    needed to say which jump a cancellation refers to.
    """
    for event in reversed(events):
        if not isinstance(event, CarrierJumpCancelledEvent):
            continue
        if event.carrier_id != carrier_id:
            continue
        if event.timestamp >= request.timestamp:
            return True
    return False


def _has_arrived(
    events: list[JournalEvent],
    carrier_id: int,
    request: CarrierJumpRequestEvent,
) -> bool:
    """Whether the carrier has been seen at the system it jumped to."""
    for event in reversed(events):
        if not isinstance(event, CarrierLocationEvent):
            continue
        if event.carrier_id != carrier_id:
            continue
        if event.timestamp < request.timestamp:
            continue
        if event.system_address == request.system_address:
            return True
    return False


def _departure_elapsed(
    request: CarrierJumpRequestEvent,
    now: datetime | None,
) -> bool:
    """Whether the booked departure is far enough past to presume arrival."""
    if now is None or request.departure_time is None:
        return False
    return _as_utc(now) > _as_utc(request.departure_time) + ARRIVAL_GRACE


def derive_carrier_transit(
    events: list[JournalEvent],
    carrier_id: int,
    *,
    now: datetime | None = None,
) -> CarrierTransit | None:
    """Derive whether a carrier is parked or in transit.

    Args:
        events: The journal event stream, oldest first.
        carrier_id: The carrier to derive movement for.
        now: Current time, used only to retire a booked jump the application
            never saw complete. Omitted, that guard does not apply and the
            derivation rests on journal events alone.

    Returns:
        The carrier's movement state, or None when the journals carry no jump
        history for it at all, which is not the same as knowing it is parked.
    """
    request = _latest_jump_request(events, carrier_id)
    if request is None:
        return None

    if _was_cancelled(events, carrier_id, request):
        return _parked()

    if _has_arrived(events, carrier_id, request):
        return _parked()

    if _departure_elapsed(request, now):
        return _parked()

    return CarrierTransit(
        state=CarrierTransitState.IN_TRANSIT,
        destination_system=request.system_name,
        destination_body=request.body,
        departure_time=request.departure_time,
    )


__all__ = ["ARRIVAL_GRACE", "derive_carrier_transit"]
