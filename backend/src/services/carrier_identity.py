"""Reconstruction of a carrier identity from journal events.

A carrier's identity is spread across Docked, CarrierStats and
CarrierLocation events that arrive at different times and do not always
agree. This module holds the rules for reconciling them into one
:class:`CarrierIdentity`.
"""

from __future__ import annotations

from ..models.carriers import (
    CarrierIdentity,
    CarrierRole,
)
from ..models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    DockedEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


def build_identity_from_journal(
    docked_event: DockedEvent,
    stats: CarrierStatsEvent | None,
    location: CarrierLocationEvent | None,
) -> CarrierIdentity:
    """Construct a CarrierIdentity from journal events.

    Notes
    -----
    - CarrierStats is emitted for the commander's own carrier.
    - Current journal data does not reliably distinguish an official
      squadron carrier from a personal carrier with squadron docking
      access, so we do *not* infer CarrierRole.SQUADRON here.
    """
    # Fleet carriers expose both a Docked.MarketID and
    # CarrierStats/CarrierTradeOrder.CarrierID.
    # In most journals these match but some users report mismatches. Prefer:
    #   1) CarrierStats.MarketID when present,
    #   2) CarrierStats.CarrierID,
    #   3) Docked.MarketID.
    carrier_unique_id = (
        stats.market_id
        if stats is not None and isinstance(getattr(stats, "market_id", None), int)
        else (stats.carrier_id if stats is not None else docked_event.market_id)
    )
    last_seen_system = (
        location.star_system if location is not None else docked_event.star_system
    )
    last_seen_timestamp = (
        stats.timestamp
        if stats is not None and stats.timestamp is not None
        else docked_event.timestamp
    )

    # Determine role heuristically.
    role = CarrierRole.OTHER
    if stats is not None:
        # Treat any carrier for which we see CarrierStats as OWN.
        # We intentionally do *not* infer a dedicated squadron carrier
        # from the DockingAccess field, because that only controls who
        # may dock there and does not identify the squadron's official
        # carrier.
        role = CarrierRole.OWN

    # Docking access and services, when available.
    docking_access: str | None = None
    services: list[str] | None = None

    # Start with any activated crew roles from CarrierStats.Crew, which
    # represent the installed/active carrier services (e.g. Exploration,
    # Outfitting, PioneerSupplies, VistaGenomics, Bartender, etc.).
    service_names_set: set[str] = set()
    raw_services = None

    if stats is not None:
        docking_access = stats.raw_data.get("DockingAccess")

        crew_list = stats.raw_data.get("Crew") or []
        if isinstance(crew_list, list):
            for crew in crew_list:
                if not isinstance(crew, dict):
                    continue
                if not crew.get("Activated"):
                    continue
                crew_role = crew.get("CrewRole")
                if not isinstance(crew_role, str):
                    continue
                role_lower = crew_role.lower()
                # Ignore non-service roles such as Captain.
                if role_lower == "captain":
                    continue
                service_names_set.add(role_lower)

        # Some journal variants may also expose services directly on CarrierStats.
        raw_services = stats.raw_data.get("Services") or stats.raw_data.get(
            "StationServices"
        )

    # Fall back to StationServices on the Docked event if CarrierStats
    # does not expose a services list explicitly.
    if raw_services is None:
        raw_services = docked_event.raw_data.get("StationServices")

    if isinstance(raw_services, list):
        for item in raw_services:
            if isinstance(item, str):
                service_names_set.add(item.lower())
            elif isinstance(item, dict):
                name = item.get("Name") or item.get("name")
                if isinstance(name, str):
                    service_names_set.add(name.lower())

    if service_names_set:
        # Sort for stable output.
        services = sorted(service_names_set)

    # Choose the most descriptive name/callsign we have.
    name = stats.name if stats is not None and stats.name else docked_event.station_name
    callsign = stats.callsign if stats is not None else None

    return CarrierIdentity(
        carrier_id=carrier_unique_id,
        market_id=docked_event.market_id,
        name=name,
        callsign=callsign,
        role=role,
        docking_access=docking_access,
        last_seen_system=last_seen_system,
        last_seen_timestamp=last_seen_timestamp,
        services=services,
    )
