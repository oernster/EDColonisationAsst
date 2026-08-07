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
    JournalEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


def find_latest_docked_carrier(events: list[JournalEvent]) -> DockedEvent | None:
    """Return the most recent DockedEvent at a Fleet carrier, if any."""
    for event in reversed(events):
        if isinstance(event, DockedEvent) and event.station_type == "FleetCarrier":
            return event
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
