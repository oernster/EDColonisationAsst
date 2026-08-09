"""Tests for colonisation repository"""

import pytest


@pytest.mark.asyncio
async def test_add_construction_site(repository, sample_construction_site):
    """Test adding a construction site"""
    await repository.add_construction_site(sample_construction_site)

    site = await repository.get_site_by_market_id(sample_construction_site.market_id)

    assert site is not None
    assert site.market_id == sample_construction_site.market_id
    assert site.station_name == sample_construction_site.station_name


@pytest.mark.asyncio
async def test_get_sites_by_system(repository, sample_construction_site):
    """Test getting sites by system"""
    await repository.add_construction_site(sample_construction_site)

    sites = await repository.get_sites_by_system("Test System")

    assert len(sites) == 1
    assert sites[0].system_name == "Test System"


@pytest.mark.asyncio
async def test_get_all_systems(repository, sample_construction_site):
    """Test getting all systems"""
    await repository.add_construction_site(sample_construction_site)

    systems = await repository.get_all_systems()

    assert len(systems) == 1
    assert "Test System" in systems


@pytest.mark.asyncio
async def test_update_commodity(repository, sample_construction_site):
    """Test updating commodity amount"""
    await repository.add_construction_site(sample_construction_site)

    await repository.update_commodity(
        market_id=sample_construction_site.market_id,
        commodity_name="Steel",
        provided_amount=750,
    )

    site = await repository.get_site_by_market_id(sample_construction_site.market_id)
    steel = next(c for c in site.commodities if c.name == "Steel")

    assert steel.provided_amount == 750


@pytest.mark.asyncio
async def test_get_stats(repository, sample_construction_site):
    """Test getting repository statistics"""
    await repository.add_construction_site(sample_construction_site)

    stats = await repository.get_stats()

    assert stats["total_systems"] == 1
    assert stats["total_sites"] == 1
    assert stats["in_progress_sites"] == 1
    assert stats["completed_sites"] == 0


@pytest.mark.asyncio
async def test_update_commodity_missing_site_does_not_raise(repository):
    """update_commodity should safely no-op when the site does not exist."""
    # No sites have been added yet; use a bogus market_id.
    await repository.update_commodity(
        market_id=999999,
        commodity_name="Steel",
        provided_amount=123,
    )
    # Should not raise and repository should still be empty
    stats = await repository.get_stats()
    assert stats["total_sites"] == 0


@pytest.mark.asyncio
async def test_update_commodity_missing_commodity_does_not_modify_site(
    repository, sample_construction_site
):
    """update_commodity should log a warning but leave data unchanged when commodity is
    missing."""
    await repository.add_construction_site(sample_construction_site)

    # Attempt to update a non-existent commodity name
    await repository.update_commodity(
        market_id=sample_construction_site.market_id,
        commodity_name="NonExistentCommodity",
        provided_amount=999,
    )

    # Original commodity values should be unchanged
    site = await repository.get_site_by_market_id(sample_construction_site.market_id)
    steel = next(c for c in site.commodities if c.name == "Steel")
    assert (
        steel.provided_amount == sample_construction_site.commodities[0].provided_amount
    )
