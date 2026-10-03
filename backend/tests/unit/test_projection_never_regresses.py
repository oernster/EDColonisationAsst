"""Construction-site projection: what a later event may and may not undo.

The projector's own contract is that "a later event must never lose progress".
Three ways it did, each reproduced here before the fix:

- A stale depot snapshot projected after the completing one (files are taken
  in modification order, which the game does not promise matches event order)
  turned a completed site back into one at 25% and "in progress", while every
  commodity still read as fully delivered.
- A ColonisationContribution in the newer `Contributions` array shape carrying
  several commodities recorded only the first.
- Depot commodities with no `Name` all landed under the empty key, so they
  collapsed into one row; a delivered amount above the required one reported
  progress over 100%.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.colonisation import (
    Commodity,
    CommodityAggregate,
    ConstructionSite,
)
from src.models.journal_events import ColonisationConstructionDepotEvent
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.colonisation_projection import ColonisationProjector
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker

_MARKET_ID = 3960951554
_FULL = 100.0


def _depot(progress: float, complete: bool, resources: list[dict]):
    return ColonisationConstructionDepotEvent(
        timestamp=datetime(2025, 1, 1, tzinfo=UTC),
        event="ColonisationConstructionDepot",
        market_id=_MARKET_ID,
        station_name="Depot",
        station_type="Outpost",
        system_name="Sol",
        system_address=1,
        construction_progress=progress,
        construction_complete=complete,
        construction_failed=False,
        commodities=resources,
    )


_STEEL_DONE = [{"Name": "$steel_name;", "Total": 1000, "Delivered": 1000}]
_STEEL_QUARTER = [{"Name": "$steel_name;", "Total": 1000, "Delivered": 250}]


@pytest.fixture
async def projector(repository: ColonisationRepository) -> ColonisationProjector:
    await repository.clear_all()
    return ColonisationProjector(SystemTracker(), repository)


@pytest.mark.asyncio
async def test_a_stale_snapshot_never_reopens_a_completed_site(
    projector: ColonisationProjector, repository: ColonisationRepository
) -> None:
    await projector.project_depot(_depot(1.0, True, _STEEL_DONE))
    await projector.project_depot(_depot(0.25, False, _STEEL_QUARTER))

    site = await repository.get_site_by_market_id(_MARKET_ID)
    assert site.construction_complete is True
    assert site.construction_progress == 1.0


@pytest.mark.asyncio
async def test_a_failure_once_reported_stays_reported(
    projector: ColonisationProjector, repository: ColonisationRepository
) -> None:
    failed = _depot(0.5, False, _STEEL_QUARTER)
    failed.construction_failed = True
    await projector.project_depot(failed)
    await projector.project_depot(_depot(0.25, False, _STEEL_QUARTER))

    site = await repository.get_site_by_market_id(_MARKET_ID)
    assert site.construction_failed is True


@pytest.mark.asyncio
async def test_every_item_of_a_multi_item_contribution_is_recorded(
    projector: ColonisationProjector, repository: ColonisationRepository
) -> None:
    await projector.project_depot(
        _depot(
            0.0,
            False,
            [
                {"Name": "$titanium_name;", "Total": 500, "Delivered": 0},
                {"Name": "$steel_name;", "Total": 500, "Delivered": 0},
            ],
        )
    )
    line = (
        '{"timestamp":"2025-01-01T00:01:00Z","event":"ColonisationContribution",'
        f'"MarketID":{_MARKET_ID},"Contributions":['
        '{"Name":"$titanium_name;","Name_Localised":"Titanium","Amount":23},'
        '{"Name":"$steel_name;","Name_Localised":"Steel","Amount":40}]}'
    )
    event = JournalParser().parse_line(line)

    await projector.project_contribution(event)

    site = await repository.get_site_by_market_id(_MARKET_ID)
    provided = {c.name: c.provided_amount for c in site.commodities}
    assert provided == {"$titanium_name;": 23, "$steel_name;": 40}


def test_unusable_contribution_entries_are_skipped_not_fatal() -> None:
    line = (
        '{"timestamp":"2025-01-01T00:01:00Z","event":"ColonisationContribution",'
        f'"MarketID":{_MARKET_ID},"Contributions":['
        '"junk",{"Amount":5},{"Name":"$steel_name;","Amount":40}]}'
    )

    event = JournalParser().parse_line(line)

    assert [item.commodity for item in event.deliveries()] == ["$steel_name;"]


@pytest.mark.asyncio
async def test_commodities_without_a_name_do_not_collapse_into_one_row(
    projector: ColonisationProjector, repository: ColonisationRepository
) -> None:
    await projector.project_depot(
        _depot(
            0.0,
            False,
            [
                {"Name_Localised": "Titanium", "Total": 500, "Delivered": 1},
                {"Name_Localised": "Steel", "Total": 700, "Delivered": 2},
                {"Total": 9, "Delivered": 9},
            ],
        )
    )

    site = await repository.get_site_by_market_id(_MARKET_ID)
    assert sorted(c.name for c in site.commodities) == ["Steel", "Titanium"]


def test_commodity_progress_never_exceeds_one_hundred_percent() -> None:
    over = Commodity(
        name="steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=1500,
        payment=0,
    )

    assert over.progress_percentage == _FULL


def test_site_and_aggregate_progress_never_exceed_one_hundred_percent() -> None:
    over = Commodity(
        name="steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=1500,
        payment=0,
    )
    site = ConstructionSite(
        market_id=1,
        station_name="S",
        station_type="T",
        system_name="Y",
        system_address=1,
        construction_progress=0.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[over],
    )
    aggregate = CommodityAggregate(
        commodity_name="steel",
        commodity_name_localised="Steel",
        total_required=1000,
        total_provided=1500,
        average_payment=0.0,
    )

    assert site.commodities_progress_percentage == _FULL
    assert aggregate.progress_percentage == _FULL
