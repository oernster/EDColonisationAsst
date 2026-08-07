"""Shared scaffolding for the test_coverage_journal_ingestion modules.

Split out of test_coverage_journal_ingestion.py when that file passed the module cap. Not named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from watchdog.events import FileCreatedEvent, FileModifiedEvent
from src.models.colonisation import Commodity, ConstructionSite
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
    JournalEvent,
    LocationEvent,
)
from src.services.journal_ingestion import JournalFileHandler
from src.services.journal_parser import JournalParser


TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeSystemTracker:
    """Hand-written system tracker recording every update call."""

    def __init__(
        self,
        current_system: Optional[str] = None,
        current_station: Optional[str] = None,
    ) -> None:
        self.current_system = current_system
        self.current_station = current_station
        self.locations: list[Any] = []
        self.jumps: list[Any] = []
        self.docked: list[Any] = []

    def get_current_system(self) -> Optional[str]:
        return self.current_system

    def get_current_station(self) -> Optional[str]:
        return self.current_station

    def update_from_location(self, event: Any) -> None:
        self.locations.append(event)

    def update_from_jump(self, event: Any) -> None:
        self.jumps.append(event)

    def update_from_docked(self, event: Any) -> None:
        self.docked.append(event)


class RaisingSystemTracker(FakeSystemTracker):
    """Tracker whose current system and station lookups always fail."""

    def get_current_system(self) -> Optional[str]:
        raise RuntimeError("tracker offline")

    def get_current_station(self) -> Optional[str]:
        raise RuntimeError("tracker offline")


class FakeRepository:
    """In-memory repository fake for construction sites and contributions."""

    def __init__(self) -> None:
        self.sites: dict[int, ConstructionSite] = {}
        self.added: list[ConstructionSite] = []
        self.contributions: list[tuple[int, str, int]] = []

    async def get_site_by_market_id(self, market_id: int) -> Optional[ConstructionSite]:
        return self.sites.get(market_id)

    async def add_construction_site(self, site: ConstructionSite) -> None:
        self.sites[site.market_id] = site
        self.added.append(site)

    async def update_commodity(
        self, market_id: int, commodity_name: str, provided_amount: int
    ) -> None:
        self.contributions.append((market_id, commodity_name, provided_amount))


class ListParser:
    """Parser fake that returns a fixed list of events from parse_file."""

    def __init__(self, events: List[JournalEvent]) -> None:
        self.events = list(events)

    def parse_file(self, file_path: Any) -> List[JournalEvent]:
        return list(self.events)

    def parse_line(self, line: str) -> Optional[JournalEvent]:
        return None


class RaisingFileParser(ListParser):
    """Parser fake whose parse_file always raises."""

    def parse_file(self, file_path: Any) -> List[JournalEvent]:
        raise RuntimeError("parse boom")


class MarkerRaisingLineParser(JournalParser):
    """Real parser except that lines containing BOOM raise.

    The real JournalParser never raises from parse_line; this subclass lets
    us exercise the defensive per-line exception handling in the handler's
    incremental tail parse.
    """

    def parse_line(self, line: str) -> Optional[JournalEvent]:
        if "BOOM" in line:
            raise RuntimeError("line boom")
        return super().parse_line(line)


class ExplodingDiagnosticsHandler(JournalFileHandler):
    """Handler whose diagnostic attribute writes raise once armed.

    The diagnostics blocks in JournalFileHandler are wrapped in defensive
    try/except so failures never break ingestion. The production attribute
    assignments cannot realistically fail, so this subclass makes them fail
    on demand to prove the except paths swallow the error.
    """

    explode: bool = False
    _DIAG_FIELDS = frozenset(
        {
            "last_watchdog_event_at",
            "last_processed_file",
            "last_events_parsed",
            "last_updated_systems",
            "last_error",
        }
    )

    def __setattr__(self, name: str, value: Any) -> None:
        if self.explode and name in self._DIAG_FIELDS:
            raise RuntimeError("diagnostics unavailable")
        super().__setattr__(name, value)


class RecordingCallback:
    """Async callback recording each system name it is invoked with."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, system_name: str) -> None:
        self.calls.append(system_name)


class _UndecodablePart(bytes):
    """Bytes whose decode always fails, to hit the decode except path."""

    def decode(self, *args: Any, **kwargs: Any) -> str:
        raise UnicodeDecodeError("utf-8", b"x", 0, 1, "forced failure")


class _UndecodableBuffer(bytes):
    """Bytes buffer producing undecodable parts when split.

    Seeded into the handler's partial-line state so that the incremental
    read path receives parts whose decode raises.
    """

    def __add__(self, other: bytes) -> "_UndecodableBuffer":
        return _UndecodableBuffer(bytes(self) + bytes(other))

    def split(self, sep: Any = None, maxsplit: int = -1) -> list:
        return [_UndecodablePart(p) for p in bytes(self).split(sep, maxsplit)]


class SequencedStatPath:
    """Path-like fake with scripted stat sizes and an unopenable fspath.

    stat() returns each size in turn and raises OSError once exhausted.
    __fspath__ raises OSError so open() fails with an OSError, driving the
    handler's incremental-read fallback branch.
    """

    def __init__(self, name: str, sizes: list[int]) -> None:
        self._name = name
        self._sizes = list(sizes)

    def stat(self) -> SimpleNamespace:
        if not self._sizes:
            raise OSError("stat gone")
        return SimpleNamespace(st_size=self._sizes.pop(0))

    def __fspath__(self) -> str:
        raise OSError("cannot open")

    def __str__(self) -> str:
        return self._name


def make_handler(
    loop: asyncio.AbstractEventLoop,
    parser: Any = None,
    tracker: Any = None,
    repo: Any = None,
    callback: Any = None,
    cls: type = JournalFileHandler,
) -> Any:
    """Build a handler wired with fakes unless real collaborators are given."""
    return cls(
        parser=parser or ListParser([]),
        system_tracker=tracker or FakeSystemTracker(),
        repository=repo or FakeRepository(),
        update_callback=callback,
        loop=loop,
    )


def depot_event(**overrides: Any) -> ColonisationConstructionDepotEvent:
    """Construct a depot event with sensible defaults."""
    values: dict[str, Any] = {
        "timestamp": TS,
        "event": "ColonisationConstructionDepot",
        "market_id": 1234,
        "station_name": "Depot Alpha",
        "station_type": "Construction Depot",
        "system_name": "Alpha System",
        "system_address": 42,
        "construction_progress": 10.0,
        "commodities": [
            {"Name": "steel", "Total": 10, "Delivered": 1, "Payment": 5},
        ],
    }
    values.update(overrides)
    return ColonisationConstructionDepotEvent(**values)


def docked_event(**overrides: Any) -> DockedEvent:
    """Construct a Docked event with sensible defaults."""
    values: dict[str, Any] = {
        "timestamp": TS,
        "event": "Docked",
        "station_name": "Orbis Site",
        "station_type": "Colonisation Ship",
        "star_system": "Base System",
        "system_address": 900,
        "market_id": 500,
        "station_faction": {},
        "station_government": "Democracy",
        "station_economy": "Industrial",
        "station_economies": [],
    }
    values.update(overrides)
    return DockedEvent(**values)


def seeded_site(**overrides: Any) -> ConstructionSite:
    """Construct an existing construction site matching docked_event defaults."""
    values: dict[str, Any] = {
        "market_id": 500,
        "station_name": "Orbis Site",
        "station_type": "Colonisation Ship",
        "system_name": "Base System",
        "system_address": 900,
        "construction_progress": 5.0,
        "construction_complete": False,
        "construction_failed": False,
        "commodities": [],
    }
    values.update(overrides)
    return ConstructionSite(**values)
