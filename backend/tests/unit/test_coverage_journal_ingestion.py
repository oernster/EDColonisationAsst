"""Diagnostics and incremental tail parsing.

Split out of test_coverage_journal_ingestion.py; the scaffolding lives in _test_coverage_journal_ingestion_support.py.
"""

import asyncio
import json
from pathlib import Path
from watchdog.events import FileCreatedEvent, FileModifiedEvent
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
    JournalEvent,
    LocationEvent,
)
from src.services.journal_parser import JournalParser

from tests.unit._test_coverage_journal_ingestion_support import (
    ExplodingDiagnosticsHandler,
    FakeRepository,
    FakeSystemTracker,
    ListParser,
    MarkerRaisingLineParser,
    RaisingFileParser,
    RecordingCallback,
    SequencedStatPath,
    TS,
    _UndecodableBuffer,
    depot_event,
    make_handler,
)


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
    handler._tail_reader.offsets[key] = path.stat().st_size + 999
    handler._tail_reader.partials[key] = b"stale partial"

    await handler._process_file(path)

    assert handler._tail_reader.offsets[key] == path.stat().st_size
    assert handler._tail_reader.partials[key] == b""
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
    assert handler._tail_reader.offsets[key] == path.stat().st_size
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

    assert handler._tail_reader.partials[key] == jump_head
    assert 777 in repo.sites
    assert "Tail System" in callback.calls
    assert len(tracker.jumps) == 0

    # Completing the partial line delivers the pending FSDJump event.
    with open(path, "ab") as fh:
        fh.write(jump_tail + b"\n")

    await handler._process_file(path)

    assert handler._tail_reader.partials[key] == b""
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
    handler._tail_reader.offsets[key] = len(first)
    handler._tail_reader.partials[key] = _UndecodableBuffer(b"")

    await handler._process_file(path)

    assert handler._tail_reader.offsets[key] == path.stat().st_size
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
    handler._tail_reader.offsets[key] = 10

    await handler._process_file(fake_path)

    assert handler._tail_reader.offsets[key] == 100
    assert handler._tail_reader.partials[key] == b""
    assert tracker.locations == [event]


async def test_process_file_incremental_open_and_stat_failure(tmp_path: Path) -> None:
    """When stat also fails after the fallback parse, the cached size is used."""
    loop = asyncio.get_running_loop()
    handler = make_handler(loop, parser=ListParser([]))

    fake_path = SequencedStatPath("Journal.fake2.log", [64])
    key = str(fake_path)
    handler._tail_reader.offsets[key] = 10

    await handler._process_file(fake_path)

    assert handler._tail_reader.offsets[key] == 64
    assert handler._tail_reader.partials[key] == b""
