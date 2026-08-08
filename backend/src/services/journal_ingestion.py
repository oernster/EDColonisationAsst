"""Journal ingestion for Elite Dangerous colonisation data.

This module contains the JournalFileHandler class which:

- Filters watchdog events down to Journal.*.log files and companion exports.
- Schedules asynchronous ingestion on the main event loop.
- Reads the newly appended lines through a JournalTailReader.
- Updates the SystemTracker from location, jump and docked events.
- Projects colonisation events through a ColonisationProjector.
- Notifies an optional callback with the set of systems that changed.

The handler is the watchdog boundary and little else. Incremental reading
lives in src.services.journal_tail_reader and the repository merge rules in
src.services.colonisation_projection, so what remains here is routing each
parsed event to its collaborator, plus the diagnostics that back the
/api/watcher/status endpoint.

The FileWatcher in src.services.file_watcher wires filesystem events
(watchdog Observer) to this handler; keeping the ingestion logic here helps
keep file_watcher.py focused on watcher lifecycle concerns.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler

from ..models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
    FSDJumpEvent,
    JournalEvent,
    LocationEvent,
)
from ..repositories.colonisation_repository import IColonisationRepository
from ..utils.logger import get_logger
from .colonisation_projection import ColonisationProjector
from .journal_parser import IJournalParser
from .journal_tail_reader import JournalTailReader
from .system_tracker import ISystemTracker

logger = get_logger(__name__)

_JOURNAL_PREFIX = "Journal."
_JOURNAL_SUFFIX = ".log"

# Files the game exports alongside the journal. They are not parsed here; a
# change to one still means the interface has something new to show.
_COMPANION_EXPORTS = frozenset({"Market.json", "Cargo.json", "Status.json"})
_COMPANION_REFRESH_KEY = "__exports__"

# Substrings that mark a docked station type as a colonisation build site.
_COLONISATION_MARKER = "Colonisation"
_CONSTRUCTION_MARKER = "Construction"


class JournalFileHandler(FileSystemEventHandler):
    """Handler for journal file system events.

    Responsibilities:
    - Filter watchdog events down to the files worth acting on.
    - Schedule asynchronous ingestion on the main event loop.
    - Route each parsed event to the tracker or the projector.
    - Invoke an optional update callback for each affected system.
    """

    def __init__(
        self,
        parser: IJournalParser,
        system_tracker: ISystemTracker,
        repository: IColonisationRepository,
        update_callback: Callable | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._system_tracker = system_tracker
        self._repository = repository
        self.update_callback = update_callback
        self._tail_reader = JournalTailReader(parser)
        self._projector = ColonisationProjector(system_tracker, repository)
        # Event loop used to schedule async processing from watchdog threads
        self._loop = loop or asyncio.get_event_loop()

        # --- diagnostics (best-effort, for /api/watcher/status) ---
        self.last_watchdog_event_at: str | None = None
        self.last_watchdog_event_type: str | None = None
        self.last_watchdog_event_path: str | None = None
        self.last_processed_at: str | None = None
        self.last_processed_file: str | None = None
        self.last_error: str | None = None
        self.last_events_parsed: int | None = None
        self.last_updated_systems: list[str] | None = None
        self.last_depot_market_ids: list[int] | None = None

    # ------------------------------------------------------------------ watchdog hooks

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if file_path.name in _COMPANION_EXPORTS:
            logger.debug("Companion export modified: %s", file_path.name)
            # Companion exports are not journals and are not parsed here;
            # they should still trigger an interface refresh (the carrier
            # market relies on Market.json).
            if self.update_callback is not None:
                asyncio.run_coroutine_threadsafe(
                    self.update_callback(_COMPANION_REFRESH_KEY),
                    self._loop,
                )
            return

        if not _is_journal(file_path):
            return

        logger.debug("Journal file modified: %s", file_path.name)
        self._schedule_processing(file_path, event_type="modified")

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if not _is_journal(file_path):
            return

        logger.info("New journal file created: %s", file_path.name)
        self._schedule_processing(file_path, event_type="created")

    def _schedule_processing(self, file_path: Path, event_type: str) -> None:
        """Record the watchdog event and queue the file on the event loop."""
        self._record_diagnostics(
            last_watchdog_event_at=datetime.now(UTC).isoformat(),
            last_watchdog_event_type=event_type,
            last_watchdog_event_path=str(file_path),
        )
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
            self._record_diagnostics(
                last_processed_file=str(file_path),
                last_processed_at=datetime.now(UTC).isoformat(),
                last_error=None,
            )

            events = await self._tail_reader.read_events(file_path)
            self._record_diagnostics(last_events_parsed=len(events))
            if not events:
                return

            updated_systems: set[str] = set()
            depot_market_ids: set[int] = set()

            for event in events:
                await self._route_event(event, updated_systems, depot_market_ids)

            if updated_systems and self.update_callback:
                for system_name in updated_systems:
                    await self.update_callback(system_name)

            self._record_diagnostics(
                last_updated_systems=sorted(updated_systems),
                last_depot_market_ids=sorted(depot_market_ids),
            )

        except Exception as exc:  # noqa: BLE001
            # Deliberately broad, per file. This is the whole ingestion of one
            # journal file: reading it while the game writes it, parsing lines
            # across years of format changes and persisting the results. One
            # bad file must not stop the watcher.
            logger.error("Error processing file %s: %s", file_path, exc)
            self._record_diagnostics(last_error=f"{type(exc).__name__}: {exc}")

    async def _route_event(
        self,
        event: JournalEvent,
        updated_systems: set[str],
        depot_market_ids: set[int],
    ) -> None:
        """Send one parsed event to the tracker, the projector or both.

        `updated_systems` collects the systems whose data changed, which the
        caller notifies once per file rather than once per event.
        """
        if isinstance(event, LocationEvent):
            self._system_tracker.update_from_location(event)
        elif isinstance(event, FSDJumpEvent):
            self._system_tracker.update_from_jump(event)
        elif isinstance(event, DockedEvent):
            self._system_tracker.update_from_docked(event)
            if _is_construction_station(event):
                await self._projector.project_docked(event)
                updated_systems.add(event.star_system)

        if isinstance(event, ColonisationConstructionDepotEvent):
            depot_market_ids.add(event.market_id)
            # Depot events often omit StarSystem, so the notification uses the
            # system the projector resolved from the site and the tracker.
            resolved_system = await self._projector.project_depot(event)
            if resolved_system:
                updated_systems.add(resolved_system)
        elif isinstance(event, ColonisationContributionEvent):
            await self._projector.project_contribution(event)
            site = await self._repository.get_site_by_market_id(event.market_id)
            if site:
                updated_systems.add(site.system_name)

    def _record_diagnostics(self, **fields: object) -> None:
        """Best-effort bookkeeping for the /api/watcher/status endpoint.

        Deliberately broad: one guard for every diagnostic write in the class.
        This is not ingestion. Losing a field here is invisible to the user,
        whereas raising would abandon journal processing that had already
        succeeded. Fields are applied in order, so a failure leaves the ones
        after it untouched.
        """
        try:
            for name, value in fields.items():
                setattr(self, name, value)
        except Exception:  # noqa: BLE001, S110
            pass


def _is_journal(file_path: Path) -> bool:
    """Whether the path names a journal file rather than anything else."""
    return file_path.name.startswith(_JOURNAL_PREFIX) and file_path.name.endswith(
        _JOURNAL_SUFFIX
    )


def _is_construction_station(event: DockedEvent) -> bool:
    """Whether a Docked event landed at a colonisation construction site."""
    return (
        _COLONISATION_MARKER in event.station_type
        or _CONSTRUCTION_MARKER in event.station_type
    )
