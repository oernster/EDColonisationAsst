"""Docked and depot metadata rules.

Split out of test_coverage_journal_ingestion.py; the scaffolding lives in _test_coverage_journal_ingestion_support.py.
"""

import asyncio
import json
from pathlib import Path
from src.models.colonisation import Commodity, ConstructionSite
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
    JournalEvent,
    LocationEvent,
)
from src.services.journal_parser import JournalParser

from tests.unit._test_coverage_journal_ingestion_support import (
    FakeRepository,
    FakeSystemTracker,
    ListParser,
    RaisingSystemTracker,
    RecordingCallback,
    TS,
    depot_event,
    docked_event,
    make_handler,
    seeded_site,
)


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
    handler._projector.project_depot = unresolved_depot  # type: ignore[method-assign]

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

    system = await handler._projector.project_depot(event)

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

    system = await handler._projector.project_depot(event)

    assert system == "Unknown System"
    site = repo.sites[808]
    assert site.station_name == "Unknown Station"
    assert site.station_type == "Unknown"
    assert site.system_name == "Unknown System"
    assert site.system_address == 0


async def test_docked_updates_station_type_only() -> None:
    """Only the station type changing still persists an updated site."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._projector.project_docked(
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

    await handler._projector.project_docked(docked_event(star_system="Renamed System"))

    assert len(repo.added) == 1
    assert repo.sites[500].system_name == "Renamed System"


async def test_docked_updates_system_address_only() -> None:
    """Only the system address changing still persists an updated site."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._projector.project_docked(docked_event(system_address=901))

    assert len(repo.added) == 1
    assert repo.sites[500].system_address == 901


async def test_docked_with_identical_metadata_is_a_no_op() -> None:
    """A Docked event matching the stored site exactly writes nothing."""
    loop = asyncio.get_running_loop()
    repo = FakeRepository()
    repo.sites[500] = seeded_site()
    handler = make_handler(loop, repo=repo)

    await handler._projector.project_docked(docked_event())

    assert repo.added == []
