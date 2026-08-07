"""Contribution arrays and modification events.

Split out of test_file_watcher.py; the scaffolding lives in _test_file_watcher_support.py.
"""

import asyncio
from datetime import datetime, UTC
from pathlib import Path
import pytest
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
)
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.file_watcher import FileWatcher, JournalFileHandler
from src.services.system_tracker import SystemTracker

from tests.unit._test_file_watcher_support import (
    _DummyParser,
)


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
