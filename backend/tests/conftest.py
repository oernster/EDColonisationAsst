"""Pytest configuration and fixtures"""

import pytest
import pytest_asyncio
from pathlib import Path
from datetime import datetime, UTC
from src.models.colonisation import Commodity, ConstructionSite
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker
from src.services.data_aggregator import DataAggregator

# Not unused: re-exporting the api_app fixture here makes it injectable by name
# across the suite without per-module imports that flake8 flags as F401/F811.
from tests.unit._test_api_routes_support import api_app  # noqa: F401


@pytest.fixture
def sample_commodity() -> Commodity:
    """Create a sample commodity for testing"""
    return Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=500,
        payment=1234,
    )


@pytest.fixture
def sample_construction_site() -> ConstructionSite:
    """Create a sample construction site for testing"""
    return ConstructionSite(
        market_id=123456,
        station_name="Test Station",
        station_type="Planetary Construction Depot",
        system_name="Test System",
        system_address=987654,
        construction_progress=50.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=1000,
                provided_amount=500,
                payment=1234,
            ),
            Commodity(
                name="CMMComposite",
                name_localised="CMM Composite",
                required_amount=2000,
                provided_amount=2000,
                payment=5678,
            ),
        ],
        last_updated=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def repository() -> ColonisationRepository:
    """Create a fresh repository for testing"""
    repo = ColonisationRepository()
    yield repo
    await repo.clear_all()


@pytest.fixture
def parser() -> JournalParser:
    """Create a journal parser for testing"""
    return JournalParser()


@pytest.fixture
def system_tracker() -> SystemTracker:
    """Create a system tracker for testing"""
    return SystemTracker()


@pytest_asyncio.fixture
async def aggregator(repository: ColonisationRepository) -> DataAggregator:
    """Create a data aggregator for testing"""
    return DataAggregator(repository)


@pytest.fixture
def sample_journal_line() -> str:
    """Sample journal line for testing"""
    return (
        '{"timestamp":"2025-11-29T01:00:00Z","event":"ColonisationConstructionDepot",'
        '"MarketID":123456,"StationName":"Test Station",'
        '"StationType":"Planetary Construction Depot","StarSystem":"Test System",'
        '"SystemAddress":987654,"ConstructionProgress":50.0,'
        '"Commodities":[{"Name":"Steel","Name_Localised":"Steel","Total":1000,'
        '"Delivered":500,"Payment":1234}]}'
    )


@pytest.fixture
def temp_journal_dir(tmp_path: Path) -> Path:
    """Create a temporary journal directory for testing"""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    return journal_dir
