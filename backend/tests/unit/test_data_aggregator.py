"""Tests for DataAggregator service (no external mocking, in-memory data only)."""

import pytest
from datetime import datetime, UTC

from src.models.colonisation import Commodity, ConstructionSite, SystemColonisationData
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.data_aggregator import DataAggregator


class _DummyInaraService:
    """Simple stub for InaraService used only for tests.

    It mimics the `get_system_colonisation_data` coroutine but never
    touches the network.
    """

    def __init__(self, sites_by_system=None, should_fail: bool = False):
        # Dict[str, list[dict]]
        self._sites_by_system = sites_by_system or {}
        self._should_fail = should_fail

    async def get_system_colonisation_data(self, system_name: str):
        if self._should_fail:
            raise RuntimeError("Inara is temporarily unavailable")
        return self._sites_by_system.get(system_name, [])


@pytest.mark.asyncio
async def test_aggregate_by_system_local_only(
    repository: ColonisationRepository, sample_construction_site
):
    """When Inara has no data, aggregation should return local sites unchanged."""
    await repository.add_construction_site(sample_construction_site)

    aggregator = DataAggregator(repository)
    # Replace real Inara service with dummy that returns no data
    aggregator._inara_service = _DummyInaraService(sites_by_system={})

    system_data = await aggregator.aggregate_by_system("Test System")

    assert isinstance(system_data, SystemColonisationData)
    assert system_data.system_name == "Test System"
    assert len(system_data.construction_sites) == 1
    site = system_data.construction_sites[0]
    assert site.market_id == sample_construction_site.market_id
    assert site.station_name == sample_construction_site.station_name
    # No completion upgrade should have happened
    assert site.construction_complete is False


@pytest.mark.asyncio
async def test_aggregate_by_system_inara_upgrades_local(
    repository: ColonisationRepository, sample_construction_site
):
    """Inara data should upgrade completion/progress for existing local sites."""
    # Local site: incomplete, 50% progress, with one underfilled commodity
    await repository.add_construction_site(sample_construction_site)

    inara_payload = {
        "Lupus System": [
            {
                "marketId": sample_construction_site.market_id,
                "stationName": sample_construction_site.station_name,
                "stationType": sample_construction_site.station_type,
                "systemName": sample_construction_site.system_name,
                "systemAddress": sample_construction_site.system_address,
                "progress": 100.0,
                "isCompleted": True,
                "isFailed": False,
                "commodities": [
                    {
                        "name": "Steel",
                        "name_localised": "Steel",
                        "required": 1000,
                        "provided": 1000,
                        "payment": 1234,
                    }
                ],
            }
        ]
    }

    aggregator = DataAggregator(repository)
    aggregator._inara_service = _DummyInaraService(sites_by_system=inara_payload)

    system_data = await aggregator.aggregate_by_system("Lupus System")

    assert len(system_data.construction_sites) == 1
    site = system_data.construction_sites[0]

    # Completion should have been upgraded from Inara
    assert site.construction_complete is True
    assert site.construction_failed is False
    assert site.construction_progress == pytest.approx(100.0)

    # Commodities should appear fully provided
    steel = next(c for c in site.commodities if c.name == "Steel")
    assert steel.provided_amount == steel.required_amount
    assert steel.remaining_amount == 0


@pytest.mark.asyncio
async def test_aggregate_commodities_and_summary(repository: ColonisationRepository):
    """End-to-end test of commodity aggregation and system summary."""
    # Two sites in the same system with overlapping and distinct commodities
    site1 = ConstructionSite(
        market_id=1,
        station_name="Site A",
        station_type="Depot",
        system_name="Agg System",
        system_address=111,
        construction_progress=25.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=1000,
                provided_amount=200,
                payment=1000,
            ),
            Commodity(
                name="Aluminium",
                name_localised="Aluminium",
                required_amount=500,
                provided_amount=500,
                payment=2000,
            ),
        ],
        last_updated=datetime.now(UTC),
    )

    site2 = ConstructionSite(
        market_id=2,
        station_name="Site B",
        station_type="Depot",
        system_name="Agg System",
        system_address=111,
        construction_progress=75.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=500,
                provided_amount=500,
                payment=1500,
            ),
        ],
        last_updated=datetime.now(UTC),
    )

    await repository.add_construction_site(site1)
    await repository.add_construction_site(site2)

    aggregator = DataAggregator(repository)
    aggregator._inara_service = _DummyInaraService(sites_by_system={})

    system_data = await aggregator.aggregate_by_system("Agg System")
    assert system_data.total_sites == 2

    commodities = await aggregator.aggregate_commodities(system_data.construction_sites)
    # There should be at least Steel and Aluminium in the aggregates
    names = {c.commodity_name for c in commodities}
    assert {"Steel", "Aluminium"}.issubset(names)

    steel_agg = next(c for c in commodities if c.commodity_name == "Steel")
    # Steel totals: required 1500, provided 700
    assert steel_agg.total_required == 1500
    assert steel_agg.total_provided == 700
    assert steel_agg.total_remaining == 800
    # Both sites need Steel at some point
    assert (
        "Site A" in steel_agg.sites_requiring or "Site B" in steel_agg.sites_requiring
    )

    summary = await aggregator.get_system_summary("Agg System")
    assert summary["system_name"] == "Agg System"
    assert summary["total_sites"] == 2
    assert summary["completed_sites"] == 0
    assert summary["in_progress_sites"] == 2
    assert summary["total_commodities_needed"] == sum(
        c.total_remaining for c in commodities
    )
    assert summary["unique_commodities"] == len(commodities)


@pytest.mark.asyncio
async def test_aggregate_by_system_inara_failure_falls_back_to_local(
    repository: ColonisationRepository, sample_construction_site
):
    """If Inara fails, aggregate_by_system should still return local data without
    raising.
    """
    await repository.add_construction_site(sample_construction_site)

    aggregator = DataAggregator(repository)
    aggregator._inara_service = _DummyInaraService(should_fail=True)

    system_data = await aggregator.aggregate_by_system(
        sample_construction_site.system_name
    )
    assert system_data.total_sites == 1
    site = system_data.construction_sites[0]
    assert site.market_id == sample_construction_site.market_id
    assert site.construction_complete is False


@pytest.mark.asyncio
async def test_aggregate_by_system_inara_only_completed_site_added(
    repository: ColonisationRepository,
):
    """Completed sites that exist only in Inara should be added to the repository."""
    inara_payload = {
        "Remote System": [
            {
                "marketId": 9999,
                "stationName": "Remote Depot",
                "stationType": "Depot",
                "systemName": "Remote System",
                "systemAddress": 424242,
                "progress": 100.0,
                "isCompleted": True,
                "isFailed": False,
                "commodities": [],
            }
        ]
    }

    aggregator = DataAggregator(repository)
    aggregator._inara_service = _DummyInaraService(sites_by_system=inara_payload)

    system_data = await aggregator.aggregate_by_system("Remote System")
    assert system_data.total_sites == 1
    site = system_data.construction_sites[0]
    assert site.market_id == 9999
    assert site.construction_complete is True

    # Repository should now also know about this site
    stored = await repository.get_site_by_market_id(9999)
    assert stored is not None
    assert stored.system_name == "Remote System"


@pytest.mark.asyncio
async def test_aggregate_by_system_inara_upgrades_existing_local_site(
    repository: ColonisationRepository,
):
    """Inara should upgrade an existing local incomplete site to completed and fill
    commodities."""
    # Local site in the same system that we will query
    local_site = ConstructionSite(
        market_id=4242,
        station_name="Upgrade Depot",
        station_type="Depot",
        system_name="Upgrade System",
        system_address=111222,
        construction_progress=40.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=1000,
                provided_amount=100,
                payment=1000,
            )
        ],
        last_updated=datetime.now(UTC),
    )
    await repository.add_construction_site(local_site)

    inara_payload = {
        "Upgrade System": [
            {
                "marketId": local_site.market_id,
                "stationName": local_site.station_name,
                "stationType": local_site.station_type,
                "systemName": local_site.system_name,
                "systemAddress": local_site.system_address,
                "progress": 90.0,
                "isCompleted": True,
                "isFailed": False,
                "commodities": [
                    {
                        "name": "Steel",
                        "name_localised": "Steel",
                        "required": 1000,
                        "provided": 1000,
                        "payment": 1234,
                    }
                ],
            }
        ]
    }

    aggregator = DataAggregator(repository)
    aggregator._inara_service = _DummyInaraService(sites_by_system=inara_payload)

    system_data = await aggregator.aggregate_by_system("Upgrade System")
    assert system_data.total_sites == 1
    site = system_data.construction_sites[0]

    # Site should have been upgraded to completed
    assert site.construction_complete is True
    assert site.construction_failed is False
    assert site.construction_progress == pytest.approx(90.0)

    # Commodity should appear fully provided
    steel = next(c for c in site.commodities if c.name == "Steel")
    assert steel.provided_amount == steel.required_amount
    assert steel.remaining_amount == 0
