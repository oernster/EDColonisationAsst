"""Lifecycle and full-file ingestion.

Split out of test_file_watcher.py; the scaffolding lives in
_test_file_watcher_support.py.
"""

import asyncio
from datetime import datetime, UTC
from pathlib import Path
import pytest
import src.services.file_watcher as fw_module
from src.models.journal_events import DockedEvent
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.file_watcher import FileWatcher, JournalFileHandler
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker

from tests.unit._test_file_watcher_support import (
    _DummyObserver,
)


@pytest.mark.asyncio
async def test_file_watcher_start_and_stop(
    tmp_path: Path, repository: ColonisationRepository
):
    """FileWatcher.start_watching and stop_watching should manage the observer
    lifecycle.
    """
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
    """FileWatcher.start_watching should raise FileNotFoundError when directory is
    missing.
    """
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
    """_process_file should drive tracker updates, site creation and callbacks for
    legacy
    schema."""
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

    # Repository should contain the site created/updated via depot and contribution
    # events
    site = await repository.get_site_by_market_id(555)
    assert site is not None
    assert site.system_name == "Beta System"
    assert site.station_name == "Beta Construction Site"
    # Contribution should have bumped provided amount
    steel = next(c for c in site.commodities if c.name == "Steel")
    assert steel.provided_amount == 300

    # Callback should have been invoked for the updated system
    assert "Beta System" in updated_systems
