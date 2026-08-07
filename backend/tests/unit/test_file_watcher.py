"""Tests for journal file watcher internals (no external mocking frameworks)."""

from __future__ import annotations

import asyncio
from datetime import datetime, UTC
from pathlib import Path

import pytest

import src.services.file_watcher as fw_module
from src.models.colonisation import ConstructionSite, Commodity
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
)
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.file_watcher import FileWatcher, JournalFileHandler
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker


class _DummyParser:
    """Minimal parser implementation for JournalFileHandler tests."""

    def parse_file(self, file_path: Path):
        return []

    def parse_line(self, line: str):
        return None


@pytest.mark.asyncio
async def test_process_construction_depot_creates_site(
    repository: ColonisationRepository,
):
    """_process_construction_depot should create a ConstructionSite with commodities."""
    system_tracker = SystemTracker()
    handler = JournalFileHandler(
        parser=_DummyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    event = ColonisationConstructionDepotEvent(
        timestamp=datetime.now(UTC),
        event="ColonisationConstructionDepot",
        market_id=1,
        station_name="Alpha Depot",
        station_type="Depot",
        system_name="Alpha System",
        system_address=111,
        construction_progress=25.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            {
                "Name": "Steel",
                "Name_Localised": "Steel",
                "Total": 1000,
                "Delivered": 250,
                "Payment": 1000,
            }
        ],
        raw_data={},
    )

    await handler._process_construction_depot(event)

    site = await repository.get_site_by_market_id(1)
    assert site is not None
    assert site.station_name == "Alpha Depot"
    assert site.system_name == "Alpha System"
    assert site.construction_progress == pytest.approx(25.0)
    assert len(site.commodities) == 1
    steel = site.commodities[0]
    assert steel.name == "Steel"
    assert steel.required_amount == 1000
    assert steel.provided_amount == 250


@pytest.mark.asyncio
async def test_process_construction_depot_reuses_existing_metadata(
    repository: ColonisationRepository,
):
    """When a site already exists, depot snapshots should reuse its metadata."""
    # Seed repository with a site that has good metadata
    seed_site = ConstructionSite(
        market_id=42,
        station_name="Seed Station",
        station_type="Planetary Construction Depot",
        system_name="Seed System",
        system_address=999,
        construction_progress=10.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[],
        last_updated=datetime.now(UTC),
    )
    await repository.add_construction_site(seed_site)

    system_tracker = SystemTracker()
    handler = JournalFileHandler(
        parser=_DummyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    # Event with missing/placeholder metadata for the same MarketID
    event = ColonisationConstructionDepotEvent(
        timestamp=datetime.now(UTC),
        event="ColonisationConstructionDepot",
        market_id=42,
        station_name="",  # should be ignored in favour of existing metadata
        station_type="",
        system_name="",
        system_address=0,
        construction_progress=50.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[],
        raw_data={},
    )

    await handler._process_construction_depot(event)

    site = await repository.get_site_by_market_id(42)
    assert site is not None
    # Metadata should still come from the original seeded site
    assert site.station_name == "Seed Station"
    assert site.system_name == "Seed System"
    assert site.system_address == 999
    # Progress should have been updated from the new snapshot
    assert site.construction_progress == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_process_contribution_updates_commodity(
    repository: ColonisationRepository,
):
    """_process_contribution should update commodity provided_amount via repository.update_commodity."""
    # Seed repository with a site that has a single commodity
    site = ConstructionSite(
        market_id=7,
        station_name="Contribution Depot",
        station_type="Depot",
        system_name="Gamma System",
        system_address=777,
        construction_progress=0.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=1000,
                provided_amount=100,
                payment=1234,
            )
        ],
        last_updated=datetime.now(UTC),
    )
    await repository.add_construction_site(site)

    system_tracker = SystemTracker()
    handler = JournalFileHandler(
        parser=_DummyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    event = ColonisationContributionEvent(
        timestamp=datetime.now(UTC),
        event="ColonisationContribution",
        market_id=7,
        commodity="Steel",
        commodity_localised="Steel",
        quantity=50,
        total_quantity=600,
        credits_received=9999,
        raw_data={},
    )

    await handler._process_contribution(event)

    updated_site = await repository.get_site_by_market_id(7)
    assert updated_site is not None
    steel = next(c for c in updated_site.commodities if c.name == "Steel")
    # JournalFileHandler passes total_quantity through to update_commodity
    assert steel.provided_amount == 600


@pytest.mark.asyncio
async def test_process_docked_at_construction_site_updates_existing_metadata(
    repository: ColonisationRepository,
):
    """Docked events should upgrade existing construction site metadata."""
    # Existing site with placeholder metadata
    placeholder_site = ConstructionSite(
        market_id=999,
        station_name="Unknown Station",
        station_type="Unknown",
        system_name="Unknown System",
        system_address=0,
        construction_progress=0.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[],
        last_updated=datetime.now(UTC),
    )
    await repository.add_construction_site(placeholder_site)

    system_tracker = SystemTracker()
    handler = JournalFileHandler(
        parser=_DummyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    dock_event = DockedEvent(
        timestamp=datetime.now(UTC),
        event="Docked",
        station_name="Real Station",
        station_type="Outpost",
        star_system="Real System",
        system_address=1234,
        market_id=999,
        station_faction={"Name": "Faction"},
        station_government="Democracy",
        station_economy="Industrial",
        station_economies=[],
        raw_data={},
    )

    await handler._process_docked_at_construction_site(dock_event)

    updated_site = await repository.get_site_by_market_id(999)
    assert updated_site is not None
    assert updated_site.station_name == "Real Station"
    assert updated_site.station_type == "Outpost"
    assert updated_site.system_name == "Real System"
    assert updated_site.system_address == 1234


@pytest.mark.asyncio
async def test_process_docked_at_construction_site_creates_placeholder_when_missing(
    repository: ColonisationRepository,
):
    """If no site exists, Docked events should create a placeholder ConstructionSite."""
    system_tracker = SystemTracker()
    handler = JournalFileHandler(
        parser=_DummyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    dock_event = DockedEvent(
        timestamp=datetime.now(UTC),
        event="Docked",
        station_name="New Station",
        station_type="Coriolis",
        star_system="New System",
        system_address=4321,
        market_id=12345,
        station_faction={"Name": "Faction"},
        station_government="Dictatorship",
        station_economy="HighTech",
        station_economies=[],
        raw_data={},
    )

    await handler._process_docked_at_construction_site(dock_event)

    site = await repository.get_site_by_market_id(12345)
    assert site is not None
    assert site.station_name == "New Station"
    assert site.system_name == "New System"
    assert site.construction_progress == 0
    assert site.commodities == []


class _DummyObserver:
    """Lightweight stand-in for watchdog.observers.Observer used in FileWatcher tests."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[object, str, bool]] = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, handler, path: str, recursive: bool) -> None:
        self.scheduled.append((handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True


@pytest.mark.asyncio
async def test_file_watcher_start_and_stop(
    tmp_path: Path, repository: ColonisationRepository
):
    """FileWatcher.start_watching and stop_watching should manage the observer lifecycle."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    orig_observer = fw_module.Observer
    try:
        # Replace real watchdog Observer with dummy implementation
        fw_module.Observer = _DummyObserver  # type: ignore[assignment]

        parser = JournalParser()
        system_tracker = SystemTracker()
        watcher = FileWatcher(
            parser=parser,
            system_tracker=system_tracker,
            repository=repository,
            loop=asyncio.get_running_loop(),
        )

        await watcher.start_watching(journal_dir)
        # Observer should have been created and started
        assert isinstance(watcher._observer, _DummyObserver)
        dummy_observer = watcher._observer  # type: ignore[assignment]
        assert dummy_observer.started is True
        # With an empty directory, _process_existing_files will log a warning and return

        await watcher.stop_watching()
        # stop_watching should have stopped and joined the observer, then cleared it
        assert dummy_observer.stopped is True
        assert dummy_observer.joined is True
        assert watcher._observer is None
    finally:
        fw_module.Observer = orig_observer  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_file_watcher_start_raises_for_missing_directory(
    repository: ColonisationRepository,
):
    """FileWatcher.start_watching should raise FileNotFoundError when directory is missing."""
    missing_dir = Path("does_not_exist_12345")

    parser = JournalParser()
    system_tracker = SystemTracker()
    watcher = FileWatcher(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        loop=asyncio.get_running_loop(),
    )

    with pytest.raises(FileNotFoundError):
        await watcher.start_watching(missing_dir)


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_updates_tracker_and_repository(
    repository: ColonisationRepository,
):
    """_process_file should drive tracker updates, site creation and callbacks for legacy schema."""
    from src.models.journal_events import (
        LocationEvent,
        FSDJumpEvent,
        ColonisationConstructionDepotEvent,
        ColonisationContributionEvent,
    )
    from src.services.system_tracker import SystemTracker as RealSystemTracker

    system_tracker = RealSystemTracker()

    # Build a small sequence of events:
    #  - Location in Alpha
    #  - Jump to Beta
    #  - Dock at a construction station in Beta
    #  - Construction depot snapshot in Beta
    #  - Contribution at that depot (legacy flat ColonisationContribution schema)
    ts = datetime.now(UTC)

    location = LocationEvent(
        timestamp=ts,
        event="Location",
        star_system="Alpha System",
        system_address=111,
        star_pos=[0.0, 0.0, 0.0],
        station_name=None,
        station_type=None,
        market_id=None,
        docked=False,
        raw_data={},
    )

    jump = FSDJumpEvent(
        timestamp=ts,
        event="FSDJump",
        star_system="Beta System",
        system_address=222,
        star_pos=[1.0, 2.0, 3.0],
        jump_dist=10.0,
        fuel_used=2.0,
        fuel_level=5.0,
        raw_data={},
    )

    dock = DockedEvent(
        timestamp=ts,
        event="Docked",
        station_name="Beta Construction Site",
        station_type="Colonisation Depot",
        star_system="Beta System",
        system_address=222,
        market_id=555,
        station_faction={"Name": "Test Faction"},
        station_government="Democracy",
        station_economy="Industrial",
        station_economies=[],
        raw_data={},
    )

    depot = ColonisationConstructionDepotEvent(
        timestamp=ts,
        event="ColonisationConstructionDepot",
        market_id=555,
        station_name="Beta Construction Site",
        station_type="Depot",
        system_name="Beta System",
        system_address=222,
        construction_progress=50.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            {
                "Name": "Steel",
                "Name_Localised": "Steel",
                "Total": 1000,
                "Delivered": 250,
                "Payment": 1000,
            }
        ],
        raw_data={},
    )

    contribution = ColonisationContributionEvent(
        timestamp=ts,
        event="ColonisationContribution",
        market_id=555,
        commodity="Steel",
        commodity_localised="Steel",
        quantity=50,
        total_quantity=300,
        credits_received=12345,
        raw_data={},
    )

    events = [location, jump, dock, depot, contribution]

    class _Parser:
        def __init__(self, events):
            self._events = events
            self.calls: list[Path] = []

        def parse_file(self, file_path: Path):
            self.calls.append(file_path)
            return list(self._events)

    updated_systems: list[str] = []

    async def _callback(system_name: str) -> None:
        updated_systems.append(system_name)

    parser = _Parser(events)
    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=_callback,
        loop=asyncio.get_running_loop(),
    )

    fake_path = Path("Journal.2025-01-01T000000.01.log")
    await handler._process_file(fake_path)

    # Tracker should now reflect the final docked state in Beta System
    assert system_tracker.get_current_system() == "Beta System"
    assert system_tracker.get_current_station() == "Beta Construction Site"
    assert system_tracker.is_docked() is True

    # Repository should contain the site created/updated via depot and contribution events
    site = await repository.get_site_by_market_id(555)
    assert site is not None
    assert site.system_name == "Beta System"
    assert site.station_name == "Beta Construction Site"
    # Contribution should have bumped provided amount
    steel = next(c for c in site.commodities if c.name == "Steel")
    assert steel.provided_amount == 300

    # Callback should have been invoked for the updated system
    assert "Beta System" in updated_systems


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_handles_colonisation_contributions_array(
    repository: ColonisationRepository,
):
    """_process_file should handle ColonisationContribution with Contributions array schema."""
    from src.models.journal_events import (
        LocationEvent,
        FSDJumpEvent,
        ColonisationConstructionDepotEvent,
        ColonisationContributionEvent,
    )
    from src.services.system_tracker import SystemTracker as RealSystemTracker

    system_tracker = RealSystemTracker()

    ts = datetime.now(UTC)

    # Location + jump to the target system
    location = LocationEvent(
        timestamp=ts,
        event="Location",
        star_system="Lupus Dark Region BQ-Y d66",
        system_address=2278253693331,
        star_pos=[0.0, 0.0, 0.0],
        station_name=None,
        station_type=None,
        market_id=None,
        docked=False,
        raw_data={},
    )

    jump = FSDJumpEvent(
        timestamp=ts,
        event="FSDJump",
        star_system="Lupus Dark Region BQ-Y d66",
        system_address=2278253693331,
        star_pos=[1.0, 2.0, 3.0],
        jump_dist=10.0,
        fuel_used=2.0,
        fuel_level=5.0,
        raw_data={},
    )

    # Dock at a colonisation construction site
    dock = DockedEvent(
        timestamp=ts,
        event="Docked",
        station_name="Orbital Construction Site: Blast Furnace Vista",
        station_type="Colonisation Depot",
        star_system="Lupus Dark Region BQ-Y d66",
        system_address=2278253693331,
        market_id=3960951554,
        station_faction={"Name": "Test Faction"},
        station_government="Democracy",
        station_economy="Industrial",
        station_economies=[],
        raw_data={},
    )

    # Initial depot snapshot using ResourcesRequired with zero provided amount
    initial_depot = ColonisationConstructionDepotEvent(
        timestamp=ts,
        event="ColonisationConstructionDepot",
        market_id=3960951554,
        station_name="Orbital Construction Site: Blast Furnace Vista",
        station_type="Colonisation Depot",
        system_name="Lupus Dark Region BQ-Y d66",
        system_address=2278253693331,
        construction_progress=0.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            {
                "Name": "$titanium_name;",
                "Name_Localised": "Titanium",
                "Total": 1594,
                "Delivered": 0,
                "Payment": 5360,
            }
        ],
        raw_data={},
    )

    # ColonisationContribution in the new schema (we still use the model but simulate the payload)
    contribution = ColonisationContributionEvent(
        timestamp=ts,
        event="ColonisationContribution",
        market_id=3960951554,
        commodity="$Titanium_name;",
        commodity_localised="Titanium",
        quantity=23,
        total_quantity=23,
        credits_received=0,
        raw_data={
            "MarketID": 3960951554,
            "Contributions": [
                {
                    "Name": "$Titanium_name;",
                    "Name_Localised": "Titanium",
                    "Amount": 23,
                }
            ],
        },
    )

    # Follow-up depot snapshot with ProvidedAmount = 23
    updated_depot = ColonisationConstructionDepotEvent(
        timestamp=ts,
        event="ColonisationConstructionDepot",
        market_id=3960951554,
        station_name="Orbital Construction Site: Blast Furnace Vista",
        station_type="Colonisation Depot",
        system_name="Lupus Dark Region BQ-Y d66",
        system_address=2278253693331,
        construction_progress=0.34,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            {
                "Name": "$titanium_name;",
                "Name_Localised": "Titanium",
                "Total": 1594,
                "Delivered": 23,
                "Payment": 5360,
            }
        ],
        raw_data={},
    )

    events = [location, jump, dock, initial_depot, contribution, updated_depot]

    class _Parser:
        def __init__(self, events):
            self._events = events
            self.calls: list[Path] = []

        def parse_file(self, file_path: Path):
            self.calls.append(file_path)
            return list(self._events)

    updated_systems: list[str] = []

    async def _callback(system_name: str) -> None:
        updated_systems.append(system_name)

    parser = _Parser(events)
    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=_callback,
        loop=asyncio.get_running_loop(),
    )

    fake_path = Path("Journal.2025-12-15T203720.01.log")
    await handler._process_file(fake_path)

    # Tracker should now reflect the final docked state in the construction system
    assert system_tracker.get_current_system() == "Lupus Dark Region BQ-Y d66"
    assert (
        system_tracker.get_current_station()
        == "Orbital Construction Site: Blast Furnace Vista"
    )
    assert system_tracker.is_docked() is True

    # Repository should contain the site with Titanium progress from both depot and contribution
    site = await repository.get_site_by_market_id(3960951554)
    assert site is not None
    assert site.system_name == "Lupus Dark Region BQ-Y d66"
    assert site.station_name == "Orbital Construction Site: Blast Furnace Vista"

    titanium = next(c for c in site.commodities if c.name_localised == "Titanium")
    # Provided amount should reflect at least the 23 units delivered
    assert titanium.provided_amount >= 23
    assert titanium.required_amount == 1594

    # Callback should have been invoked for the updated system
    assert "Lupus Dark Region BQ-Y d66" in updated_systems


def test_journal_file_handler_on_modified_schedules_for_journal_files(monkeypatch):
    """on_modified should schedule processing for valid Journal.*.log files."""
    from types import SimpleNamespace

    parser = _DummyParser()
    system_tracker = SystemTracker()
    repository = ColonisationRepository()
    loop = asyncio.get_event_loop()
    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=loop,
    )

    scheduled: list[tuple[object, object]] = []

    def fake_run_coroutine_threadsafe(coro, target_loop):
        """
        Test stub for asyncio.run_coroutine_threadsafe.

        We record the scheduled coroutine/loop pair and then immediately
        close the coroutine so Python does not emit a 'coroutine was never
        awaited' RuntimeWarning. The real function would submit the coroutine
        to the loop; here we only care that scheduling was attempted.
        """
        scheduled.append((coro, target_loop))
        try:
            # Best-effort: if this is a coroutine object, close it to silence
            # resource warnings in the test environment.
            coro.close()  # type: ignore[func-returns-value]
        except Exception:
            pass

        class DummyFuture:
            def cancel(self) -> None:
                pass

        return DummyFuture()

    orig_run = asyncio.run_coroutine_threadsafe
    asyncio.run_coroutine_threadsafe = fake_run_coroutine_threadsafe
    try:
        # Directory events should be ignored
        dir_event = SimpleNamespace(
            is_directory=True, src_path=str(Path("Journal.2025-01-01T000000.01.log"))
        )
        handler.on_modified(dir_event)
        assert scheduled == []

        # Non-journal files should be ignored
        non_journal_event = SimpleNamespace(
            is_directory=False, src_path=str(Path("notes.txt"))
        )
        handler.on_modified(non_journal_event)
        assert scheduled == []

        # Valid journal file should schedule processing
        journal_event = SimpleNamespace(
            is_directory=False,
            src_path=str(Path("Journal.2025-01-01T000000.01.log")),
        )
        handler.on_modified(journal_event)
        assert len(scheduled) == 1
        _, target_loop = scheduled[0]
        assert target_loop is loop
    finally:
        asyncio.run_coroutine_threadsafe = orig_run


def test_journal_file_handler_on_created_schedules_for_journal_files(monkeypatch):
    """on_created should schedule processing for valid Journal.*.log files."""
    from types import SimpleNamespace

    parser = _DummyParser()
    system_tracker = SystemTracker()
    repository = ColonisationRepository()
    loop = asyncio.get_event_loop()
    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=loop,
    )

    scheduled: list[tuple[object, object]] = []

    def fake_run_coroutine_threadsafe(coro, target_loop):
        """
        Test stub for asyncio.run_coroutine_threadsafe for on_created.
        """
        scheduled.append((coro, target_loop))
        try:
            coro.close()  # type: ignore[func-returns-value]
        except Exception:
            pass

        class DummyFuture:
            def cancel(self) -> None:
                pass

        return DummyFuture()

    orig_run = asyncio.run_coroutine_threadsafe
    asyncio.run_coroutine_threadsafe = fake_run_coroutine_threadsafe
    try:
        # Directory events should be ignored
        dir_event = SimpleNamespace(
            is_directory=True, src_path=str(Path("Journal.2025-01-01T000000.01.log"))
        )
        handler.on_created(dir_event)
        assert scheduled == []

        # Non-journal files should be ignored
        non_journal_event = SimpleNamespace(
            is_directory=False, src_path=str(Path("notes.txt"))
        )
        handler.on_created(non_journal_event)
        assert scheduled == []

        # Valid journal file should schedule processing
        journal_event = SimpleNamespace(
            is_directory=False,
            src_path=str(Path("Journal.2025-01-01T000000.01.log")),
        )
        handler.on_created(journal_event)
        assert len(scheduled) == 1
        _, target_loop = scheduled[0]
        assert target_loop is loop
    finally:
        asyncio.run_coroutine_threadsafe = orig_run


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_with_no_events_does_not_invoke_callback(
    repository: ColonisationRepository,
):
    """_process_file should return early when parser yields no events."""
    system_tracker = SystemTracker()

    class EmptyParser:
        def parse_file(self, file_path: Path):
            return []

        def parse_line(self, line: str):
            return None

    callback_called: list[str] = []

    async def _callback(system_name: str) -> None:
        callback_called.append(system_name)

    handler = JournalFileHandler(
        parser=EmptyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=_callback,
        loop=asyncio.get_running_loop(),
    )

    await handler._process_file(Path("Journal.empty.log"))
    # No systems should have been reported because there were no events
    assert callback_called == []


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_handles_parser_exception(
    repository: ColonisationRepository,
):
    """_process_file should catch and log exceptions from parser.parse_file."""
    system_tracker = SystemTracker()

    class FailingParser:
        def parse_file(self, file_path: Path):
            raise RuntimeError("boom")

        def parse_line(self, line: str):
            return None

    handler = JournalFileHandler(
        parser=FailingParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    # Should not raise despite the parser throwing
    await handler._process_file(Path("Journal.failure.log"))


@pytest.mark.asyncio
async def test_file_watcher_process_existing_files_invokes_handler_for_journals(
    tmp_path: Path,
    repository: ColonisationRepository,
):
    """_process_existing_files should call the handler for each existing Journal.*.log file."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    # Non-journal file should be ignored
    (journal_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    j1 = journal_dir / "Journal.2025-01-01T000000.01.log"
    j2 = journal_dir / "Journal.2025-01-02T000000.01.log"
    j1.write_text("one", encoding="utf-8")
    j2.write_text("two", encoding="utf-8")

    parser = JournalParser()
    system_tracker = SystemTracker()
    watcher = FileWatcher(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        loop=asyncio.get_running_loop(),
    )

    called_paths: list[Path] = []

    class DummyHandler:
        async def _process_file(self, file_path: Path) -> None:
            called_paths.append(file_path)

    # Inject our dummy handler so we can observe calls
    watcher._handler = DummyHandler()  # type: ignore[assignment]

    await watcher._process_existing_files(journal_dir)

    assert {p.name for p in called_paths} == {j1.name, j2.name}
