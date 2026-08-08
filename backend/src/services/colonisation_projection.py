"""Projection of colonisation journal events into the repository.

Three journal events describe a construction site and each carries a
different slice of the truth:

- `ColonisationConstructionDepot` is a snapshot of progress. Elite emits many
  of them while the commander sits on the construction screen, all sharing a
  MarketID; they frequently omit the station and system fields.
- `ColonisationContribution` records a single delivery of one commodity.
- `Docked` carries authoritative station and system names. It is how a site
  first seen through a nameless depot snapshot acquires a real one and how a
  renamed site is picked up.

Because the snapshots repeat and arrive incomplete, projection is a merge and
not a write: a later event must never lose progress or metadata that an
earlier one already established. Those merge rules are the substance of this
module. Persistence itself belongs to the repository behind
`IColonisationRepository`; this module holds no state of its own.
"""

from __future__ import annotations

from ..models.colonisation import Commodity, ConstructionSite
from ..models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
)
from ..repositories.colonisation_repository import IColonisationRepository
from ..utils.logger import get_logger
from .system_tracker import ISystemTracker

logger = get_logger(__name__)

_UNKNOWN_STATION = "Unknown Station"
_UNKNOWN_STATION_TYPE = "Unknown"
_UNKNOWN_SYSTEM = "Unknown System"


class ColonisationProjector:
    """Writes colonisation events into the repository without losing state.

    Responsibilities:
    - Merge depot snapshots with the stored site so progress never regresses.
    - Record contributions against the commodity they deliver.
    - Upgrade placeholder site metadata from Docked events.
    """

    def __init__(
        self,
        system_tracker: ISystemTracker,
        repository: IColonisationRepository,
    ) -> None:
        self._system_tracker = system_tracker
        self._repository = repository

    async def project_depot(
        self,
        event: ColonisationConstructionDepotEvent,
    ) -> str:
        """Merge a ColonisationConstructionDepot snapshot into the store.

        Args:
            event: the depot snapshot to project.

        Returns:
            The system name the site resolved to, which the caller uses to
            address the update notification. Depot events often omit
            StarSystem, so this is not simply `event.system_name`.
        """
        existing_site = await self._repository.get_site_by_market_id(event.market_id)
        snapshot = _snapshot_commodities(event)

        station_name, station_type, system_name, system_address = _resolve_metadata(
            event,
            existing_site,
            current_system=self._current_system(),
            current_station=self._current_station(),
        )

        await self._repository.add_construction_site(
            ConstructionSite(
                market_id=event.market_id,
                station_name=station_name,
                station_type=station_type,
                system_name=system_name,
                system_address=system_address,
                construction_progress=event.construction_progress,
                construction_complete=event.construction_complete,
                construction_failed=event.construction_failed,
                commodities=_merge_commodities(existing_site, snapshot),
            )
        )

        return system_name

    async def project_contribution(
        self,
        event: ColonisationContributionEvent,
    ) -> None:
        """Record a ColonisationContribution against its commodity."""
        await self._repository.update_commodity(
            market_id=event.market_id,
            commodity_name=event.commodity,
            provided_amount=event.total_quantity,
        )

        logger.info(
            "Contribution recorded: %s %s (total: %s, credits: %s)",
            event.quantity,
            event.commodity_localised or event.commodity,
            event.total_quantity,
            event.credits_received,
        )

    async def project_docked(self, event: DockedEvent) -> None:
        """Project a Docked event that occurred at a construction site.

        An existing site has its metadata upgraded from the event, which is
        what replaces placeholder names and reflects a rename. With no
        existing site this creates a placeholder one, since a Docked event
        carries no progress or commodity data.
        """
        existing_site = await self._repository.get_site_by_market_id(event.market_id)
        if existing_site is not None:
            await self._upgrade_site_metadata(existing_site, event)
            return

        site = ConstructionSite(
            market_id=event.market_id,
            station_name=event.station_name,
            station_type=event.station_type,
            system_name=event.star_system,
            system_address=event.system_address,
            # A simple Docked event carries neither progress nor commodities.
            construction_progress=0,
            construction_complete=False,
            construction_failed=False,
            commodities=[],
        )
        await self._repository.add_construction_site(site)
        logger.info(
            "Discovered new construction site from Docked event: %s in %s",
            site.station_name,
            site.system_name,
        )

    async def _upgrade_site_metadata(
        self,
        site: ConstructionSite,
        event: DockedEvent,
    ) -> None:
        """Persist any Docked metadata that differs from the stored site.

        The latest Docked metadata is always trusted, which is what allows a
        renamed construction site to be reflected correctly.
        """
        updated = False

        if event.station_name and event.station_name != site.station_name:
            site.station_name = event.station_name
            updated = True

        if event.station_type and event.station_type != site.station_type:
            site.station_type = event.station_type
            updated = True

        if event.star_system and event.star_system != site.system_name:
            site.system_name = event.star_system
            updated = True

        if event.system_address and event.system_address != site.system_address:
            site.system_address = event.system_address
            updated = True

        if not updated:
            return  # Already matched the latest metadata.

        await self._repository.add_construction_site(site)
        logger.info(
            "Updated construction site metadata from Docked event: %s in %s",
            site.station_name,
            site.system_name,
        )

    def _current_system(self) -> str | None:
        """The tracked system; None when the tracker cannot say."""
        try:
            return self._system_tracker.get_current_system()
        except Exception:  # noqa: BLE001
            # Deliberately broad. The tracker is an injected collaborator, so
            # its failure modes belong to the implementation behind the
            # interface. None means 'unknown system', which the metadata
            # resolution already handles.
            return None

    def _current_station(self) -> str | None:
        """The tracked station; None when not docked or unavailable."""
        try:
            return self._system_tracker.get_current_station()
        except Exception:  # noqa: BLE001
            # Deliberately broad, as above, for the station.
            return None


def _snapshot_commodities(
    event: ColonisationConstructionDepotEvent,
) -> dict[str, Commodity]:
    """Commodities carried by one depot snapshot, keyed by name."""
    snapshot: dict[str, Commodity] = {}
    for comm_data in event.commodities:
        name = comm_data.get("Name", "")
        snapshot[name] = Commodity(
            name=name,
            name_localised=comm_data.get("Name_Localised", name),
            required_amount=comm_data.get("Total", 0),
            provided_amount=comm_data.get("Delivered", 0),
            payment=comm_data.get("Payment", 0),
        )
    return snapshot


def _resolve_metadata(
    event: ColonisationConstructionDepotEvent,
    existing_site: ConstructionSite | None,
    current_system: str | None,
    current_station: str | None,
) -> tuple[str, str, str, int]:
    """Station name, station type, system name and address for a snapshot.

    Existing site metadata is preferred where present. Depot events can be
    incomplete, so a good stored value is never overwritten with a
    placeholder; renames arrive through Docked events instead. The tracker is
    the next fallback and a placeholder the last.
    """
    station_name = (
        (existing_site.station_name if existing_site else event.station_name)
        or current_station
        or _UNKNOWN_STATION
    )
    station_type = (
        existing_site.station_type if existing_site else event.station_type
    ) or _UNKNOWN_STATION_TYPE
    system_name = (
        (existing_site.system_name if existing_site else event.system_name)
        or current_system
        or _UNKNOWN_SYSTEM
    )
    system_address = (
        existing_site.system_address if existing_site else event.system_address
    ) or 0
    return station_name, station_type, system_name, system_address


def _merge_commodities(
    existing_site: ConstructionSite | None,
    snapshot: dict[str, Commodity],
) -> list[Commodity]:
    """Merge a snapshot with the stored commodities, never regressing.

    A snapshot can be partial or stale, so for every commodity the larger of
    the stored and observed amounts wins; a commodity the snapshot has
    dropped is kept rather than silently losing its progress.
    """
    if existing_site is None or not existing_site.commodities:
        return list(snapshot.values())

    existing_by_name = {c.name: c for c in existing_site.commodities}
    merged: list[Commodity] = []

    for name, snap_comm in snapshot.items():
        prev = existing_by_name.get(name)
        if prev is None:
            merged.append(snap_comm)
            continue
        merged.append(
            Commodity(
                name=name,
                name_localised=snap_comm.name_localised or prev.name_localised,
                required_amount=max(prev.required_amount, snap_comm.required_amount),
                provided_amount=max(prev.provided_amount, snap_comm.provided_amount),
                payment=snap_comm.payment or prev.payment,
            )
        )

    # Defensive: journals should keep reporting every commodity. Progress
    # already in the database must never be dropped because one did not appear.
    merged.extend(
        prev for name, prev in existing_by_name.items() if name not in snapshot
    )
    return merged
