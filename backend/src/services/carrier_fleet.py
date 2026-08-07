"""The commander's own and squadron carriers, from journal events alone.

Distinct from the docked-carrier views: this walks the whole stream and
groups by carrier id rather than reconstructing one carrier's state.
"""

from __future__ import annotations

from ..models.api_models import (
    MyCarriersResponse,
)
from ..models.carriers import (
    CarrierIdentity,
)
from ..models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    DockedEvent,
    JournalEvent,
)
from ..utils.logger import get_logger
from .carrier_identity import build_identity_from_journal

logger = get_logger(__name__)


def build_my_carriers_response(events: list[JournalEvent]) -> MyCarriersResponse:
    """Build MyCarriersResponse listing the commander's Fleet carriers.

    This mirrors the behaviour of the original /api/carriers/mine logic:

    - Uses CarrierStats as the authoritative source for the commander's
      carriers.
    - Uses CarrierLocation to enrich carriers with last-known system and
      address.
    - Prefers a real Docked event (with StationServices) when available to
      construct CarrierIdentity; falls back to a synthetic DockedEvent
      otherwise.
    - Does not infer an explicit separate 'squadron carrier' list from
      DockingAccess; squadron_carriers remains empty.
    """
    if not events:
        return MyCarriersResponse(own_carriers=[], squadron_carriers=[])

    latest_location_by_id: dict[int, CarrierLocationEvent] = {}
    latest_docked_by_market_id: dict[int, DockedEvent] = {}

    for event in events:
        if isinstance(event, CarrierLocationEvent):
            latest_location_by_id[event.carrier_id] = event
        elif isinstance(event, DockedEvent) and event.station_type == "FleetCarrier":
            latest_docked_by_market_id[event.market_id] = event

    own_carriers: list[CarrierIdentity] = []
    squadron_carriers: list[CarrierIdentity] = []

    seen_ids: set[int] = set()
    for event in events:
        if not isinstance(event, CarrierStatsEvent):
            continue

        carrier_id = event.carrier_id
        if carrier_id in seen_ids:
            continue
        seen_ids.add(carrier_id)

        location = latest_location_by_id.get(carrier_id)
        docked = latest_docked_by_market_id.get(carrier_id)

        if docked is not None:
            identity = build_identity_from_journal(docked, event, location)
        else:
            fake_docked = DockedEvent(
                timestamp=event.timestamp,
                event=event.event,
                station_name=event.name or "Unknown Carrier",
                station_type="FleetCarrier",
                star_system=location.star_system if location is not None else "",
                system_address=location.system_address if location is not None else 0,
                market_id=carrier_id,
                station_faction={},
                station_government="",
                station_economy="",
                station_economies=[],
                raw_data=event.raw_data,
            )
            identity = build_identity_from_journal(fake_docked, event, location)

        own_carriers.append(identity)

    return MyCarriersResponse(
        own_carriers=own_carriers, squadron_carriers=squadron_carriers
    )
