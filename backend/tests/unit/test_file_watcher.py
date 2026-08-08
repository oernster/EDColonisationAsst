"""Depot, contribution and docking event processing.

Split out of test_file_watcher.py; the scaffolding lives in _test_file_watcher_support.py.
"""

import asyncio
from datetime import datetime, UTC
import pytest
from src.models.colonisation import ConstructionSite, Commodity
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
async def test_process_construction_depot_creates_site(
    repository: ColonisationRepository,
):
    """project_depot should create a ConstructionSite with commodities."""
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

    await handler._projector.project_depot(event)

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

    await handler._projector.project_depot(event)

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
    """project_contribution should update commodity provided_amount via repository.update_commodity."""
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

    await handler._projector.project_contribution(event)

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

    await handler._projector.project_docked(dock_event)

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

    await handler._projector.project_docked(dock_event)

    site = await repository.get_site_by_market_id(12345)
    assert site is not None
    assert site.station_name == "New Station"
    assert site.system_name == "New System"
    assert site.construction_progress == 0
    assert site.commodities == []
