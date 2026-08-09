"""Tests for data models"""

from src.models.colonisation import (
    Commodity,
    CommodityStatus,
    ConstructionSite,
    SystemColonisationData,
)


def test_commodity_remaining_amount():
    """Test commodity remaining amount calculation"""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=600,
        payment=1234,
    )

    assert commodity.remaining_amount == 400


def test_commodity_progress_percentage():
    """Test commodity progress percentage calculation"""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=750,
        payment=1234,
    )

    assert commodity.progress_percentage == 75.0


def test_commodity_status_completed():
    """Test commodity status when completed"""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=1000,
        payment=1234,
    )

    assert commodity.status == CommodityStatus.COMPLETED


def test_commodity_status_in_progress():
    """Test commodity status when in progress"""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=500,
        payment=1234,
    )

    assert commodity.status == CommodityStatus.IN_PROGRESS


def test_commodity_status_not_started():
    """Test commodity status when not started"""
    commodity = Commodity(
        name="Steel",
        name_localised="Steel",
        required_amount=1000,
        provided_amount=0,
        payment=1234,
    )

    assert commodity.status == CommodityStatus.NOT_STARTED


def test_construction_site_is_complete(sample_construction_site):
    """Test construction site completion check"""
    assert not sample_construction_site.is_complete

    sample_construction_site.construction_complete = True
    assert sample_construction_site.is_complete


def test_construction_site_total_commodities_needed(sample_construction_site):
    """Test total commodities needed calculation"""
    # Steel: 500 remaining, CMM Composite: 0 remaining
    assert sample_construction_site.total_commodities_needed == 500


def test_construction_site_commodities_progress(sample_construction_site):
    """Test overall commodity progress calculation"""
    # Total required: 3000, Total provided: 2500
    progress = sample_construction_site.commodities_progress_percentage
    assert abs(progress - 83.33) < 0.1  # Allow small floating point difference


def test_system_colonisation_data_totals():
    """Test system colonisation data calculations"""
    sites = [
        ConstructionSite(
            market_id=1,
            station_name="Site 1",
            station_type="Depot",
            system_name="Test System",
            system_address=123,
            construction_progress=100.0,
            construction_complete=True,
            construction_failed=False,
            commodities=[],
        ),
        ConstructionSite(
            market_id=2,
            station_name="Site 2",
            station_type="Depot",
            system_name="Test System",
            system_address=123,
            construction_progress=50.0,
            construction_complete=False,
            construction_failed=False,
            commodities=[],
        ),
    ]

    system_data = SystemColonisationData(
        system_name="Test System", construction_sites=sites
    )

    assert system_data.total_sites == 2
    assert system_data.completed_sites == 1
    assert system_data.in_progress_sites == 1
    assert system_data.completion_percentage == 50.0
