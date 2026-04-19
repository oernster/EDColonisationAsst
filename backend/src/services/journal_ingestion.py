"""Journal ingestion helpers for Elite Dangerous colonisation data.

This module contains the JournalFileHandler class which:

- Parses Journal.*.log files using an injected IJournalParser.
- Updates the SystemTracker with location/jump/docked events.
- Projects colonisation-related events into the ColonisationRepository.
- Notifies an optional callback with the set of systems that changed.

The FileWatcher in src.services.file_watcher wires filesystem events
(watchdog Observer) to this handler; keeping the ingestion logic here
helps keep file_watcher.py focused on watcher lifecycle concerns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Set

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler

from .journal_parser import IJournalParser
from .system_tracker import ISystemTracker
from ..models.colonisation import Commodity, ConstructionSite
from ..models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
    FSDJumpEvent,
    LocationEvent,
)
from ..repositories.colonisation_repository import IColonisationRepository
from ..utils.logger import get_logger

logger = get_logger(__name__)


class JournalFileHandler(FileSystemEventHandler):
    """Handler for journal file system events.

    Responsibilities:
    - Filter watchdog events down to Journal.*.log files.
    - Schedule asynchronous parsing and ingestion on the main event loop.
    - Update the system tracker and repository based on parsed events.
    - Invoke an optional update callback for each affected system.
    """

    def __init__(
        self,
        parser: IJournalParser,
        system_tracker: ISystemTracker,
        repository: IColonisationRepository,
        update_callback: Optional[Callable] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.parser = parser
        self.system_tracker = system_tracker
        self.repository = repository
        self.update_callback = update_callback
        # Legacy field kept for backward compatibility; we now track per-file
        # offsets for incremental processing instead.
        self._processed_files: Set[str] = set()
        # Incremental processing state: remember how many bytes we have already
        # processed per journal file so we only ingest appended lines.
        self._file_offsets: dict[str, int] = {}
        # Prevent concurrent incremental reads of the same file.
        self._process_lock = asyncio.Lock()
        # Event loop used to schedule async processing from watchdog threads
        self._loop = loop or asyncio.get_event_loop()

        # --- diagnostics (best-effort, for /api/watcher/status) ---
        self.last_watchdog_event_at: str | None = None
        self.last_watchdog_event_type: str | None = None
        self.last_watchdog_event_path: str | None = None
        self.last_processed_at: str | None = None
        self.last_processed_file: str | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ watchdog hooks

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process journal files
        if not file_path.name.startswith("Journal.") or not file_path.name.endswith(
            ".log"
        ):
            return

        logger.debug("Journal file modified: %s", file_path.name)

        # Diagnostics
        try:
            self.last_watchdog_event_at = datetime.now(timezone.utc).isoformat()
            self.last_watchdog_event_type = "modified"
            self.last_watchdog_event_path = str(file_path)
        except Exception:
            pass

        # Schedule processing on the main event loop from the watchdog thread
        asyncio.run_coroutine_threadsafe(
            self._process_file(file_path),
            self._loop,
        )

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        # Only process journal files
        if not file_path.name.startswith("Journal.") or not file_path.name.endswith(
            ".log"
        ):
            return

        logger.info("New journal file created: %s", file_path.name)

        # Diagnostics
        try:
            self.last_watchdog_event_at = datetime.now(timezone.utc).isoformat()
            self.last_watchdog_event_type = "created"
            self.last_watchdog_event_path = str(file_path)
        except Exception:
            pass

        # Schedule processing on the main event loop from the watchdog thread
        asyncio.run_coroutine_threadsafe(
            self._process_file(file_path),
            self._loop,
        )

    # ------------------------------------------------------------------ ingestion

    async def _process_file(self, file_path: Path) -> None:
        """Process a journal file.

        Args:
            file_path: path to the journal file to parse.
        """
        try:
            # Diagnostics
            try:
                self.last_processed_file = str(file_path)
                self.last_processed_at = datetime.now(timezone.utc).isoformat()
                self.last_error = None
            except Exception:
                pass

            # Parse the file incrementally (append-only journal semantics).
            # - First time we see a file: parse entire file via parse_file.
            # - Subsequent calls: only parse newly appended lines via parse_line.
            async with self._process_lock:
                offset = int(self._file_offsets.get(str(file_path), 0))

                try:
                    current_size = file_path.stat().st_size
                except OSError:
                    current_size = 0

                # Handle truncation/rotation edge case.
                if current_size < offset:
                    offset = 0

                events = []
                if offset <= 0:
                    events = self.parser.parse_file(file_path)
                    # After full parse, mark offset at EOF.
                    try:
                        self._file_offsets[str(file_path)] = file_path.stat().st_size
                    except OSError:
                        self._file_offsets[str(file_path)] = current_size
                else:
                    # Incremental tail parse from byte offset.
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            f.seek(offset)
                            for line in f:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    ev = self.parser.parse_line(line)
                                    if ev is not None:
                                        events.append(ev)
                                except Exception:
                                    # Keep processing; parser logs internally.
                                    continue
                            try:
                                self._file_offsets[str(file_path)] = f.tell()
                            except Exception:
                                self._file_offsets[str(file_path)] = current_size
                    except OSError:
                        # If we can't open/seek, fall back to full parse.
                        events = self.parser.parse_file(file_path)
                        try:
                            self._file_offsets[str(file_path)] = file_path.stat().st_size
                        except OSError:
                            self._file_offsets[str(file_path)] = current_size

            if not events:
                return

            # Process each event
            updated_systems: Set[str] = set()

            for event in events:
                # Update system tracker
                if isinstance(event, LocationEvent):
                    self.system_tracker.update_from_location(event)
                elif isinstance(event, FSDJumpEvent):
                    self.system_tracker.update_from_jump(event)
                elif isinstance(event, DockedEvent):
                    self.system_tracker.update_from_docked(event)
                    # Also check if this is a colonisation site
                    if (
                        "Colonisation" in event.station_type
                        or "Construction" in event.station_type
                    ):
                        await self._process_docked_at_construction_site(event)
                        updated_systems.add(event.star_system)

                # Process colonisation events
                if isinstance(event, ColonisationConstructionDepotEvent):
                    await self._process_construction_depot(event)
                    updated_systems.add(event.system_name)
                elif isinstance(event, ColonisationContributionEvent):
                    await self._process_contribution(event)
                    site = await self.repository.get_site_by_market_id(event.market_id)
                    if site:
                        updated_systems.add(site.system_name)

            # Notify about updates
            if updated_systems and self.update_callback:
                for system_name in updated_systems:
                    await self.update_callback(system_name)

        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing file %s: %s", file_path, exc)
            try:
                self.last_error = f"{type(exc).__name__}: {exc}"
            except Exception:
                pass

    async def _process_construction_depot(
        self,
        event: ColonisationConstructionDepotEvent,
    ) -> None:
        """Process ColonisationConstructionDepot event.

        Notes:
            - Elite can emit many snapshot events while you sit on the
              construction screen. They all share the same MarketID and
              mostly identical data. We treat them as *updates* of a single
              site, not separate sites.
            - Some ColonisationConstructionDepot events omit station/system
              fields; in that case we reuse metadata from any existing site
              with the same market_id (typically created from a Docked event),
              or fall back to the SystemTracker's current system/station.
            - New snapshots must never *lose* progress that was previously
              observed in either:
                • earlier depot snapshots, or
                • ColonisationContribution events.
              To ensure this we merge commodity progress with any existing
              site and take the maximum observed provided_amount/required_amount
              per commodity.
        """
        # Try to reuse existing site metadata and commodity state if we have it.
        existing_site = await self.repository.get_site_by_market_id(event.market_id)

        # Convert commodities from raw data to Commodity objects from the current
        # snapshot payload.
        snapshot_commodities: dict[str, Commodity] = {}
        for comm_data in event.commodities:
            name = comm_data.get("Name", "")
            commodity = Commodity(
                name=name,
                name_localised=comm_data.get("Name_Localised", name),
                required_amount=comm_data.get("Total", 0),
                provided_amount=comm_data.get("Delivered", 0),
                payment=comm_data.get("Payment", 0),
            )
            snapshot_commodities[name] = commodity

        # Also fall back to the currently tracked system/station when event fields are missing.
        try:
            current_system = self.system_tracker.get_current_system()
        except Exception:
            current_system = None

        try:
            # get_current_station only returns a value when docked
            current_station = self.system_tracker.get_current_station()
        except Exception:
            current_station = None

        # For depot snapshots, prefer any existing site metadata where present.
        # These events can be incomplete (missing station/system), so we do not
        # blindly overwrite good values with placeholders. Renames are handled
        # primarily via Docked events.
        station_name = (
            (existing_site.station_name if existing_site else event.station_name)
            or current_station
            or "Unknown Station"
        )
        station_type = (
            existing_site.station_type if existing_site else event.station_type
        ) or "Unknown"
        system_name = (
            (existing_site.system_name if existing_site else event.system_name)
            or current_system
            or "Unknown System"
        )
        system_address = (
            existing_site.system_address if existing_site else event.system_address
        ) or 0

        # Merge commodity progress with any existing site so that we never regress
        # provided_amount/required_amount due to a partial or stale snapshot.
        merged_commodities: list[Commodity] = []
        if existing_site is not None and existing_site.commodities:
            existing_by_name = {c.name: c for c in existing_site.commodities}

            # First, merge commodities that appear in the new snapshot.
            for name, snap_comm in snapshot_commodities.items():
                prev = existing_by_name.get(name)
                if prev is not None:
                    merged_commodities.append(
                        Commodity(
                            name=name,
                            name_localised=snap_comm.name_localised
                            or prev.name_localised,
                            required_amount=max(
                                prev.required_amount, snap_comm.required_amount
                            ),
                            provided_amount=max(
                                prev.provided_amount, snap_comm.provided_amount
                            ),
                            payment=snap_comm.payment or prev.payment,
                        )
                    )
                else:
                    merged_commodities.append(snap_comm)

            # Then, keep any commodities that were previously known but no longer
            # appear in the snapshot payload. This is defensive: journals should
            # normally continue to report all commodities, but we never want to
            # silently drop progress from the database.
            for name, prev in existing_by_name.items():
                if name not in snapshot_commodities:
                    merged_commodities.append(prev)
        else:
            merged_commodities = list(snapshot_commodities.values())

        # Build the updated site model
        site = ConstructionSite(
            market_id=event.market_id,
            station_name=station_name,
            station_type=station_type,
            system_name=system_name,
            system_address=system_address,
            construction_progress=event.construction_progress,
            construction_complete=event.construction_complete,
            construction_failed=event.construction_failed,
            commodities=merged_commodities,
        )

        # Persist (INSERT OR REPLACE on the same market_id)
        await self.repository.add_construction_site(site)

        logger.info(
            "Updated construction site: %s in %s (%.1f%% complete)",
            site.station_name,
            site.system_name,
            site.construction_progress,
        )

    async def _process_contribution(self, event: ColonisationContributionEvent) -> None:
        """Process ColonisationContribution event."""
        await self.repository.update_commodity(
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

    async def _process_docked_at_construction_site(self, event: DockedEvent) -> None:
        """Process a Docked event that occurs at a construction site.

        If a site already exists for this MarketID but has placeholder
        metadata (e.g. 'Unknown Station' / 'Unknown System'), we upgrade
        that metadata from the Docked event instead of returning early.
        Otherwise this creates a placeholder ConstructionSite.
        """
        existing_site = await self.repository.get_site_by_market_id(event.market_id)
        if existing_site:
            updated = False

            # Always trust the latest Docked metadata; this also allows renamed
            # construction sites to be reflected correctly.
            if event.station_name and event.station_name != existing_site.station_name:
                existing_site.station_name = event.station_name
                updated = True

            if event.station_type and event.station_type != existing_site.station_type:
                existing_site.station_type = event.station_type
                updated = True

            if event.star_system and event.star_system != existing_site.system_name:
                existing_site.system_name = event.star_system
                updated = True

            if (
                event.system_address
                and event.system_address != existing_site.system_address
            ):
                existing_site.system_address = event.system_address
                updated = True

            if updated:
                await self.repository.add_construction_site(existing_site)
                logger.info(
                    "Updated construction site metadata from Docked event: %s in %s",
                    existing_site.station_name,
                    existing_site.system_name,
                )
            return  # Either updated, or already matched the latest metadata

        # No existing site: create placeholder from Docked data
        site = ConstructionSite(
            market_id=event.market_id,
            station_name=event.station_name,
            station_type=event.station_type,
            system_name=event.star_system,
            system_address=event.system_address,
            # We do not have progress or commodity data from a simple Docked event.
            construction_progress=0,
            construction_complete=False,
            construction_failed=False,
            commodities=[],
        )
        await self.repository.add_construction_site(site)
        logger.info(
            "Discovered new construction site from Docked event: %s in %s",
            site.station_name,
            site.system_name,
        )
