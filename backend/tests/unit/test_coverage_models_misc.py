"""Coverage tests for colonisation models, DataAggregator and SystemTracker.

Closes the remaining lines and branches in src/models/colonisation.py,
src/services/data_aggregator.py and src/services/system_tracker.py using
real components and hand-written fakes (no mock libraries).
"""

from __future__ import annotations

from datetime import datetime, UTC

import pytest

import src.services.data_aggregator as data_aggregator_module
from src.config import InaraConfig
from src.models.colonisation import (
    Commodity,
    CommodityAggregate,
    ConstructionSite,
    SystemColonisationData,
)
from src.models.journal_events import LocationEvent
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.data_aggregator import DataAggregator
from src.services.inara_service import InaraService
from src.services.system_tracker import SystemTracker


class _DummyInaraService:
    """Hand-written Inara stand-in that never touches the network."""

    def __init__(self, sites_by_system: dict[str, list[dict]] | None = None) -> None:
        self._sites_by_system = sites_by_system or {}

    async def get_system_colonisation_data(self, system_name: str) -> list[dict]:
        return self._sites_by_system.get(system_name, [])


def _make_site(
    market_id: int,
    system_name: str,
    commodities: list[Commodity] | None = None,
) -> ConstructionSite:
    """Build an incomplete construction site for aggregation tests."""
    return ConstructionSite(
        market_id=market_id,
        station_name=f"Depot {market_id}",
        station_type="Depot",
        system_name=system_name,
        system_address=market_id * 10,
        construction_progress=10.0,
        construction_complete=False,
        construction_failed=False,
        commodities=commodities or [],
        last_updated=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Colonisation models
# ---------------------------------------------------------------------------


def test_commodity_progress_is_full_when_nothing_required() -> None:
    """A commodity with zero required amount should report 100 percent."""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=0,
        provided_amount=0,
        payment=0,
    )
    assert commodity.progress_percentage == 100.0


def test_site_commodity_progress_is_full_when_total_required_is_zero() -> None:
    """A site whose commodities require nothing should report 100 percent."""
    site = _make_site(
        market_id=1,
        system_name="Zero System",
        commodities=[
            Commodity(
                name="Steel",
                name_localised="Steel",
                required_amount=0,
                provided_amount=0,
                payment=0,
            )
        ],
    )
    assert site.commodities_progress_percentage == 100.0


def test_system_completion_is_zero_without_sites() -> None:
    """An empty system should report zero percent completion."""
    system = SystemColonisationData(system_name="Empty System")
    assert system.completion_percentage == 0.0


def test_commodity_aggregate_progress_is_full_when_nothing_required() -> None:
    """An aggregate with zero required total should report 100 percent."""
    aggregate = CommodityAggregate(
        commodity_name="Steel",
        commodity_name_localised="Steel",
        total_required=0,
        total_provided=0,
        average_payment=0.0,
    )
    assert aggregate.progress_percentage == 100.0


# ---------------------------------------------------------------------------
# DataAggregator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregator_defaults_to_local_preference_on_config_failure(
    repository: ColonisationRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If config loading fails, the aggregator should prefer local data."""

    def _boom() -> None:
        raise RuntimeError("config unavailable")

    monkeypatch.setattr(data_aggregator_module, "get_config", _boom)

    aggregator = DataAggregator(repository, inara_service=_DummyInaraService())
    assert aggregator._prefer_local_for_commander_systems is True


@pytest.mark.asyncio
async def test_aggregator_skips_inara_for_commander_systems(
    repository: ColonisationRepository,
) -> None:
    """Local sites plus a real InaraService should short-circuit the Inara lookup."""
    site = _make_site(market_id=77, system_name="Commander System")
    await repository.add_construction_site(site)

    aggregator = DataAggregator(
        repository, inara_service=InaraService(inara_config=InaraConfig())
    )
    aggregator._prefer_local_for_commander_systems = True

    data = await aggregator.aggregate_by_system("Commander System")

    assert data.total_sites == 1
    assert data.construction_sites[0].market_id == 77
    assert data.construction_sites[0].construction_complete is False


@pytest.mark.asyncio
async def test_aggregator_merge_ignores_incomplete_inara_site(
    repository: ColonisationRepository,
) -> None:
    """Inara data that is not completed must not modify local sites."""
    site = _make_site(market_id=88, system_name="Merge System")
    await repository.add_construction_site(site)

    inara_payload = {
        "Merge System": [
            {
                "marketId": 88,
                "stationName": site.station_name,
                "stationType": site.station_type,
                "systemName": site.system_name,
                "systemAddress": site.system_address,
                "progress": 55.0,
                "isCompleted": False,
                "isFailed": False,
                "commodities": [],
            }
        ]
    }
    aggregator = DataAggregator(
        repository, inara_service=_DummyInaraService(inara_payload)
    )

    data = await aggregator.aggregate_by_system("Merge System")

    assert data.total_sites == 1
    merged = data.construction_sites[0]
    assert merged.construction_complete is False
    assert merged.construction_progress == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_aggregator_upgrade_leaves_completed_commodities_alone(
    repository: ColonisationRepository,
) -> None:
    """Upgrading a site should only top up commodities that are underfilled."""
    commodities = [
        Commodity(
            name="Steel",
            name_localised="Steel",
            required_amount=100,
            provided_amount=100,
            payment=10,
        ),
        Commodity(
            name="Aluminium",
            name_localised="Aluminium",
            required_amount=100,
            provided_amount=10,
            payment=10,
        ),
    ]
    site = _make_site(
        market_id=99, system_name="Upgrade Mix System", commodities=commodities
    )
    await repository.add_construction_site(site)

    inara_payload = {
        "Upgrade Mix System": [
            {
                "marketId": 99,
                "stationName": site.station_name,
                "stationType": site.station_type,
                "systemName": site.system_name,
                "systemAddress": site.system_address,
                "progress": 100.0,
                "isCompleted": True,
                "isFailed": False,
                "commodities": [],
            }
        ]
    }
    aggregator = DataAggregator(
        repository, inara_service=_DummyInaraService(inara_payload)
    )

    data = await aggregator.aggregate_by_system("Upgrade Mix System")

    assert data.total_sites == 1
    upgraded = data.construction_sites[0]
    assert upgraded.construction_complete is True

    steel = next(c for c in upgraded.commodities if c.name == "Steel")
    aluminium = next(c for c in upgraded.commodities if c.name == "Aluminium")
    assert steel.provided_amount == 100
    assert aluminium.provided_amount == aluminium.required_amount


@pytest.mark.asyncio
async def test_system_summary_without_commodities(
    repository: ColonisationRepository,
) -> None:
    """A system with no data should produce an empty summary."""
    aggregator = DataAggregator(repository, inara_service=_DummyInaraService())

    summary = await aggregator.get_system_summary("Ghost System")

    assert summary["system_name"] == "Ghost System"
    assert summary["total_sites"] == 0
    assert summary["unique_commodities"] == 0
    assert summary["most_needed_commodity"] is None


# ---------------------------------------------------------------------------
# SystemTracker
# ---------------------------------------------------------------------------


def test_update_from_location_with_unchanged_system() -> None:
    """A repeated Location event for the same system should not log a change."""
    tracker = SystemTracker()
    event = LocationEvent(
        timestamp=datetime.now(UTC),
        event="Location",
        star_system="Same System",
        system_address=42,
        docked=False,
    )

    tracker.update_from_location(event)
    # Second update with the identical system exercises the no-change branch.
    tracker.update_from_location(event)

    assert tracker.get_current_system() == "Same System"
    assert tracker.is_docked() is False
    assert tracker.get_current_station() is None
