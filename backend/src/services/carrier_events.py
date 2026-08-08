"""Latest-event lookups over a journal event stream.

Every one of these answers the same shape of question: of the events
given, which is the most recent of this type for this carrier. They are
pure and take the stream as an argument, so the callers stay testable
without a journal on disk.
"""

from __future__ import annotations

from ..models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    DockedEvent,
    FSDJumpEvent,
    JournalEvent,
    LocationEvent,
    UndockedEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


_FLEET_CARRIER = "FleetCarrier"


def find_latest_docked_carrier(events: list[JournalEvent]) -> DockedEvent | None:
    """Return the most recent DockedEvent at a Fleet carrier, if any.

    Historical: this answers "when was the commander last at a carrier", NOT
    "are they at one now". For the second question use
    :func:`find_current_carrier_docking`, which is what the API asks.
    """
    for event in reversed(events):
        if isinstance(event, DockedEvent) and event.station_type == _FLEET_CARRIER:
            return event
    return None


def _docked_event_for_market(
    events: list[JournalEvent],
    market_id: int | None,
) -> DockedEvent | None:
    """Return the newest Docked event for a given market, if one was seen."""
    if market_id is None:
        return None
    for event in reversed(events):
        if isinstance(event, DockedEvent) and event.market_id == market_id:
            return event
    return None


def _docking_from_location(
    events: list[JournalEvent],
    location: LocationEvent,
) -> DockedEvent | None:
    """Read a Location event as a docking, when it reports one at a carrier.

    A Location arrives on starting the game and on returning to the main menu,
    and it states where the commander is and whether they are docked. When
    that place is a carrier it is the only evidence of the docking, because
    the Docked event happened in a previous session.
    """
    if not location.docked or location.station_type != _FLEET_CARRIER:
        return None

    # Prefer the real Docked event, which carries the full station services.
    existing = _docked_event_for_market(events, location.market_id)
    if existing is not None:
        return existing

    return DockedEvent(
        timestamp=location.timestamp,
        event=location.event,
        station_name=location.station_name or "",
        station_type=_FLEET_CARRIER,
        star_system=location.star_system,
        system_address=location.system_address,
        market_id=location.market_id or 0,
        station_faction={},
        station_government="",
        station_economy="",
        station_economies=[],
        raw_data=location.raw_data,
    )


def find_current_carrier_docking(events: list[JournalEvent]) -> DockedEvent | None:
    """Return the carrier the commander is docked at RIGHT NOW, if any.

    The newest event that settles the question decides it, and the search
    stops there. Anything older describes a docking that has since ended.

    This distinction is the whole point. Asking only for the newest
    Docked-at-a-carrier event answers a different question, and answers this
    one wrongly the moment the commander docks anywhere else: the application
    went on reporting a commander as standing on their carrier while they
    were docked at a station in another system entirely.

    Four events settle it. A Docked names where they are, and only counts if
    that place is a carrier. An Undocked ends any docking. An FSDJump means
    they are in open space in another system. A Location states both where
    they are and whether they are docked, which is how a session that began
    with the commander already aboard is recognised.
    """
    for event in reversed(events):
        if isinstance(event, DockedEvent):
            return event if event.station_type == _FLEET_CARRIER else None
        if isinstance(event, UndockedEvent):
            return None
        if isinstance(event, FSDJumpEvent):
            return None
        if isinstance(event, LocationEvent):
            return _docking_from_location(events, event)
    return None


def find_latest_carrier_stats_for_id(
    events: list[JournalEvent],
    carrier_id: int,
) -> CarrierStatsEvent | None:
    """Return the latest CarrierStatsEvent for the given carrier id, if any."""
    for event in reversed(events):
        if isinstance(event, CarrierStatsEvent) and event.carrier_id == carrier_id:
            return event
    return None


def find_latest_carrier_stats_for_market_id(
    events: list[JournalEvent],
    market_id: int,
) -> CarrierStatsEvent | None:
    """Return the latest CarrierStatsEvent for the given carrier market id.

    CarrierStats uses CarrierID, which is usually the same as Docked.MarketID,
    but not always. Prefer explicit matching when possible.
    """
    for event in reversed(events):
        if not isinstance(event, CarrierStatsEvent):
            continue
        if event.carrier_id == market_id:
            return event
        # Some journals may include MarketID inside raw_data.
        raw_market_id = event.raw_data.get("MarketID")
        if isinstance(raw_market_id, int) and raw_market_id == market_id:
            return event
    return None


def find_latest_carrier_stats_for_callsign(
    events: list[JournalEvent],
    callsign: str,
) -> CarrierStatsEvent | None:
    """Return the latest CarrierStatsEvent matching the given callsign.

    Some users report Fleet carrier ids differing between Docked.MarketID and
    CarrierStats/CarrierTradeOrder.CarrierID. In those cases, matching on the
    callsign (Docked.StationName) is a practical fallback.
    """

    target = (callsign or "").strip().lower()
    if not target:
        return None

    for event in reversed(events):
        if not isinstance(event, CarrierStatsEvent):
            continue

        cs = event.callsign or event.raw_data.get("Callsign")
        if isinstance(cs, str) and cs.strip().lower() == target:
            return event

    return None


def find_latest_carrier_location_for_id(
    events: list[JournalEvent],
    carrier_id: int,
) -> CarrierLocationEvent | None:
    """Return the latest CarrierLocationEvent for the given carrier id, if any."""
    for event in reversed(events):
        if isinstance(event, CarrierLocationEvent) and event.carrier_id == carrier_id:
            return event
    return None
