"""Coverage tests for src.services.journal_ingestion.

These tests close the remaining statement and branch coverage gaps in
JournalFileHandler. They follow the house pattern: hand-written fakes,
real journal files written under tmp_path and pytest monkeypatch where
needed. No mock libraries are used.
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


# ------------------------------------------------------------------ fakes


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


# ------------------------------------------------------------------ helpers


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


# ------------------------------------------------------------------ watchdog hooks


async def test_on_modified_companion_export_triggers_refresh(tmp_path: Path) -> None:
    """A modified companion export schedules the __exports__ refresh callback."""
    loop = asyncio.get_running_loop()
    callback = RecordingCallback()
    handler = make_handler(loop, callback=callback)

    handler.on_modified(FileModifiedEvent(str(tmp_path / "Market.json")))
    await asyncio.sleep(0.05)

    assert callback.calls == ["__exports__"]


async def test_on_modified_companion_export_without_callback(tmp_path: Path) -> None:
    """Companion export changes with no callback registered are a no-op."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop, callback=None)

    handler.on_modified(FileModifiedEvent(str(tmp_path / "Status.json")))
    await asyncio.sleep(0.01)

    # No processing state should have been touched.
    assert handler.last_watchdog_event_at is None


async def test_on_modified_ignores_directories_and_other_files(tmp_path: Path) -> None:
    """Directory events and unrelated files are filtered out early."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop)

    dir_event = FileModifiedEvent(str(tmp_path))
    dir_event.is_directory = True
    handler.on_modified(dir_event)
    handler.on_modified(FileModifiedEvent(str(tmp_path / "random.txt")))
    await asyncio.sleep(0.01)

    assert handler.last_watchdog_event_at is None


async def test_on_modified_diagnostics_failure_is_swallowed(tmp_path: Path) -> None:
    """Diagnostic write failures in on_modified must never propagate."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop, cls=ExplodingDiagnosticsHandler)
    handler.explode = True

    handler.on_modified(
        FileModifiedEvent(str(tmp_path / "Journal.2026-01-01T000000.01.log"))
    )
    await asyncio.sleep(0.05)

    # Assignment was blocked, so the diagnostic field kept its initial value.
    assert handler.last_watchdog_event_at is None
    assert handler.last_events_parsed is None


async def test_on_created_diagnostics_failure_is_swallowed(tmp_path: Path) -> None:
    """Diagnostic write failures in on_created must never propagate."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop, cls=ExplodingDiagnosticsHandler)
    handler.explode = True

    handler.on_created(
        FileCreatedEvent(str(tmp_path / "Journal.2026-01-01T000000.01.log"))
    )
    await asyncio.sleep(0.05)

    assert handler.last_watchdog_event_at is None
    assert handler.last_watchdog_event_type is None


# ------------------------------------------------------------------ _process_file paths


async def test_process_file_diagnostics_failure_with_updates(tmp_path: Path) -> None:
    """last_updated_systems diagnostic failures are swallowed after processing."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    handler = make_handler(
        loop,
        parser=ListParser([depot_event()]),
        repo=repo,
        cls=ExplodingDiagnosticsHandler,
    )
    handler.explode = True

    await handler._process_file(tmp_path / "Journal.missing.log")

    # The depot event was still persisted despite the diagnostics failure.
    assert 1234 in repo.sites
    assert handler.last_updated_systems is None


async def test_process_file_error_and_last_error_diagnostic_failure(
    tmp_path: Path,
) -> None:
    """Errors during parsing are logged even if last_error cannot be recorded."""
    loop = asyncio.get_running_loop()
    handler = make_handler(
        loop,
        parser=RaisingFileParser([]),
        cls=ExplodingDiagnosticsHandler,
    )
    handler.explode = True

    await handler._process_file(tmp_path / "Journal.error.log")

    assert handler.last_error is None


async def test_process_file_truncated_file_resets_offset(tmp_path: Path) -> None:
    """A shrunken file resets incremental state and triggers a full re-parse."""
    loop = asyncio.get_running_loop()
    tracker = FakeSystemTracker()
    handler = make_handler(loop, parser=JournalParser(), tracker=tracker)

    path = tmp_path / "Journal.2026-01-01T000000.01.log"
    location_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "Location",
            "StarSystem": "Reset System",
            "SystemAddress": 11,
        }
    )
    path.write_text(location_line + "\n", encoding="utf-8")

    key = str(path)
    handler._file_offsets_bytes[key] = path.stat().st_size + 999
    handler._file_partial_bytes[key] = b"stale partial"

    await handler._process_file(path)

    assert handler._file_offsets_bytes[key] == path.stat().st_size
    assert handler._file_partial_bytes[key] == b""
    assert len(tracker.locations) == 1


async def test_process_file_incremental_tail_parse(tmp_path: Path) -> None:
    """Appended lines are parsed incrementally with partial lines retained."""
    loop = asyncio.get_running_loop()
    tracker = FakeSystemTracker()
    repo = FakeRepository()
    callback = RecordingCallback()
    handler = make_handler(
        loop,
        parser=MarkerRaisingLineParser(),
        tracker=tracker,
        repo=repo,
        callback=callback,
    )

    path = tmp_path / "Journal.2026-01-01T000000.01.log"
    key = str(path)

    location_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "Location",
            "StarSystem": "Start System",
            "SystemAddress": 1,
        }
    )
    path.write_text(location_line + "\n", encoding="utf-8")

    # First pass performs a full parse and records the EOF offset.
    await handler._process_file(path)
    assert handler._file_offsets_bytes[key] == path.stat().st_size
    assert len(tracker.locations) == 1

    depot_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:01:00Z",
            "event": "ColonisationConstructionDepot",
            "MarketID": 777,
            "StationName": "Tail Depot",
            "StationType": "Construction Depot",
            "StarSystem": "Tail System",
            "SystemAddress": 7,
            "ConstructionProgress": 20.0,
            "Commodities": [
                {
                    "Name": "steel",
                    "Name_Localised": "Steel",
                    "Total": 100,
                    "Delivered": 10,
                    "Payment": 5,
                }
            ],
        }
    )
    scan_line = json.dumps(
        {"timestamp": "2026-01-01T00:02:00Z", "event": "Scan", "BodyName": "X"}
    )
    jump_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:03:00Z",
            "event": "FSDJump",
            "StarSystem": "Jump System",
            "SystemAddress": 2,
            "JumpDist": 1.0,
            "FuelUsed": 0.5,
            "FuelLevel": 9.0,
        }
    ).encode("utf-8")
    jump_head, jump_tail = jump_line[:25], jump_line[25:]

    with open(path, "ab") as fh:
        fh.write(b"\n")  # empty part is skipped
        fh.write(b"   \n")  # whitespace-only line is skipped
        fh.write(scan_line.encode("utf-8") + b"\n")  # parses to None
        fh.write(b'BOOM {"broken": true}\n')  # parse_line raises, skipped
        fh.write(depot_line.encode("utf-8") + b"\n")
        fh.write(jump_head)  # partial line without newline

    await handler._process_file(path)

    assert handler._file_partial_bytes[key] == jump_head
    assert 777 in repo.sites
    assert "Tail System" in callback.calls
    assert len(tracker.jumps) == 0

    # Completing the partial line delivers the pending FSDJump event.
    with open(path, "ab") as fh:
        fh.write(jump_tail + b"\n")

    await handler._process_file(path)

    assert handler._file_partial_bytes[key] == b""
    assert len(tracker.jumps) == 1
    assert tracker.jumps[0].star_system == "Jump System"


async def test_process_file_incremental_decode_failure(tmp_path: Path) -> None:
    """Undecodable line parts are skipped without aborting the tail parse."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop)

    path = tmp_path / "Journal.decode.log"
    first = b'{"skip": 1}\n'
    path.write_bytes(first + b"second line\n")

    key = str(path)
    handler._file_offsets_bytes[key] = len(first)
    handler._file_partial_bytes[key] = _UndecodableBuffer(b"")

    await handler._process_file(path)

    assert handler._file_offsets_bytes[key] == path.stat().st_size
    assert handler.last_events_parsed == 0


async def test_process_file_incremental_open_failure_falls_back(
    tmp_path: Path,
) -> None:
    """OSError while opening for a tail read falls back to a full parse."""
    loop = asyncio.get_running_loop()
    tracker = FakeSystemTracker()
    event = LocationEvent(
        timestamp=TS, event="Location", star_system="Fallback System", system_address=3
    )
    handler = make_handler(loop, parser=ListParser([event]), tracker=tracker)

    fake_path = SequencedStatPath("Journal.fake.log", [100, 100])
    key = str(fake_path)
    handler._file_offsets_bytes[key] = 10

    await handler._process_file(fake_path)

    assert handler._file_offsets_bytes[key] == 100
    assert handler._file_partial_bytes[key] == b""
    assert tracker.locations == [event]


async def test_process_file_incremental_open_and_stat_failure(tmp_path: Path) -> None:
    """When stat also fails after the fallback parse, the cached size is used."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop, parser=ListParser([]))

    fake_path = SequencedStatPath("Journal.fake2.log", [64])
    key = str(fake_path)
    handler._file_offsets_bytes[key] = 10

    await handler._process_file(fake_path)

    assert handler._file_offsets_bytes[key] == 64
    assert handler._file_partial_bytes[key] == b""


# ------------------------------------------------------------------ event routing


async def test_docked_at_regular_station_is_not_a_site(tmp_path: Path) -> None:
    """Docking at a non-construction station never creates a site."""
    loop = asyncio.get_running_loop()
    tracker = FakeSystemTracker()
    repo = FakeRepository()
    handler = make_handler(loop, parser=JournalParser(), tracker=tracker, repo=repo)

    path = tmp_path / "Journal.docked.log"
    docked_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "Docked",
            "StationName": "Regular Station",
            "StationType": "Coriolis",
            "StarSystem": "Normal System",
            "SystemAddress": 12,
            "MarketID": 55,
            "StationFaction": {},
            "StationGovernment": "Democracy",
            "StationEconomy": "Industrial",
            "StationEconomies": [],
        }
    )
    path.write_text(docked_line + "\n", encoding="utf-8")

    await handler._process_file(path)

    assert len(tracker.docked) == 1
    assert repo.added == []


async def test_depot_with_unresolved_system_skips_notification(
    tmp_path: Path,
) -> None:
    """A falsy resolved system from depot processing suppresses callbacks."""
    loop = asyncio.get_running_loop()
    callback = RecordingCallback()
    handler = make_handler(loop, parser=ListParser([depot_event()]), callback=callback)

    async def unresolved_depot(event: ColonisationConstructionDepotEvent) -> str:
        return ""

    # Hand-written override of the helper; the real implementation always
    # returns a non-empty system name so this defensive branch needs a fake.
    handler._process_construction_depot = unresolved_depot  # type: ignore[method-assign]

    await handler._process_file(tmp_path / "Journal.unresolved.log")

    assert callback.calls == []
    assert handler.last_depot_market_ids == [1234]


async def test_contribution_without_known_site(tmp_path: Path) -> None:
    """Contributions for unknown market IDs update commodities but nothing else."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    callback = RecordingCallback()
    contribution = ColonisationContributionEvent(
        timestamp=TS,
        event="ColonisationContribution",
        market_id=321,
        commodity="steel",
        commodity_localised="Steel",
        quantity=30,
        total_quantity=30,
        credits_received=1000,
    )
    handler = make_handler(
        loop, parser=ListParser([contribution]), repo=repo, callback=callback
    )

    await handler._process_file(tmp_path / "Journal.contribution.log")

    assert repo.contributions == [(321, "steel", 30)]
    assert callback.calls == []


# ------------------------------------------------------------------ depot merging


async def test_depot_merges_new_and_stale_commodities() -> None:
    """Merging keeps snapshot-only and previously-known-only commodities."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[99] = ConstructionSite(
        market_id=99,
        station_name="Merge Depot",
        station_type="Construction Depot",
        system_name="Merge System",
        system_address=5,
        construction_progress=10.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="steel",
                name_localised="Steel",
                required_amount=100,
                provided_amount=40,
                payment=10,
            ),
            Commodity(
                name="oldthing",
                name_localised="Old Thing",
                required_amount=20,
                provided_amount=20,
                payment=3,
            ),
        ],
    )
    handler = make_handler(loop, repo=repo)

    event = depot_event(
        market_id=99,
        commodities=[
            {"Name": "steel", "Total": 100, "Delivered": 30, "Payment": 10},
            {"Name": "newthing", "Total": 50, "Delivered": 5, "Payment": 2},
        ],
    )

    system = await handler._process_construction_depot(event)

    assert system == "Merge System"
    merged = {c.name: c for c in repo.sites[99].commodities}
    assert set(merged) == {"steel", "newthing", "oldthing"}
    # Progress must never regress below the previously observed amount.
    assert merged["steel"].provided_amount == 40
    assert merged["newthing"].provided_amount == 5
    assert merged["oldthing"].provided_amount == 20


async def test_depot_fallbacks_when_tracker_raises() -> None:
    """Tracker failures fall back to placeholder station and system names."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    handler = make_handler(loop, tracker=RaisingSystemTracker(), repo=repo)

    event = depot_event(
        market_id=808,
        station_name="",
        station_type="",
        system_name="",
        system_address=0,
        commodities=[],
    )

    system = await handler._process_construction_depot(event)

    assert system == "Unknown System"
    site = repo.sites[808]
    assert site.station_name == "Unknown Station"
    assert site.station_type == "Unknown"
    assert site.system_name == "Unknown System"
    assert site.system_address == 0


# ------------------------------------------------------------------ docked metadata upgrades


async def test_docked_updates_station_type_only() -> None:
    """Only the station type changing still persists an updated site."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._process_docked_at_construction_site(
        docked_event(station_type="Construction Depot")
    )

    assert len(repo.added) == 1
    assert repo.sites[500].station_type == "Construction Depot"
    assert repo.sites[500].station_name == "Orbis Site"


async def test_docked_updates_system_name_only() -> None:
    """Only the system name changing still persists an updated site."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._process_docked_at_construction_site(
        docked_event(star_system="Renamed System")
    )

    assert len(repo.added) == 1
    assert repo.sites[500].system_name == "Renamed System"


async def test_docked_updates_system_address_only() -> None:
    """Only the system address changing still persists an updated site."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._process_docked_at_construction_site(docked_event(system_address=901))

    assert len(repo.added) == 1
    assert repo.sites[500].system_address == 901


async def test_docked_with_identical_metadata_is_a_no_op() -> None:
    """A Docked event matching the stored site exactly writes nothing."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._process_docked_at_construction_site(docked_event())

    assert repo.added == []
