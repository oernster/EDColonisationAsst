"""Dependency guards, 404 cases and journal reload.

Split out of test_api_routes.py; the scaffolding lives in _test_api_routes_support.py.
"""

from pathlib import Path
import pytest
import src.config as config_module
from fastapi import HTTPException
from src.api import routes as routes_api
from src.repositories.colonisation_repository import ColonisationRepository

from tests.unit._test_api_routes_support import (
    _DummyEmptyAggregator,
)


@pytest.mark.asyncio
async def test_get_systems_raises_500_when_repository_not_set():
    """get_systems should raise HTTP 500 if repository dependency is missing."""
    orig_repo = routes_api._repository
    try:
        routes_api._repository = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_systems()
    finally:
        routes_api._repository = orig_repo

    assert exc.value.status_code == 500
    assert "Repository not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_search_systems_raises_500_when_repository_not_set():
    """search_systems should raise HTTP 500 if repository dependency is missing."""
    orig_repo = routes_api._repository
    try:
        routes_api._repository = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.search_systems(q="Test")
    finally:
        routes_api._repository = orig_repo

    assert exc.value.status_code == 500
    assert "Repository not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_system_raises_500_when_tracker_not_set():
    """get_current_system should raise HTTP 500 if system tracker is missing."""
    orig_tracker = routes_api._system_tracker
    try:
        routes_api._system_tracker = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_current_system()
    finally:
        routes_api._system_tracker = orig_tracker

    assert exc.value.status_code == 500
    assert "System tracker not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_system_data_raises_500_when_aggregator_not_set():
    """get_system_data should raise HTTP 500 if aggregator dependency is missing."""
    orig_agg = routes_api._aggregator
    try:
        routes_api._aggregator = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_system_data(name="Test System")
    finally:
        routes_api._aggregator = orig_agg

    assert exc.value.status_code == 500
    assert "Aggregator not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_system_commodities_raises_500_when_aggregator_not_set():
    """get_system_commodities should raise HTTP 500 if aggregator is missing."""
    orig_agg = routes_api._aggregator
    try:
        routes_api._aggregator = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_system_commodities(name="Test System")
    finally:
        routes_api._aggregator = orig_agg

    assert exc.value.status_code == 500
    assert "Aggregator not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_site_raises_500_when_repository_not_set():
    """get_site should raise HTTP 500 if repository dependency is missing."""
    orig_repo = routes_api._repository
    try:
        routes_api._repository = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_site(market_id=123)
    finally:
        routes_api._repository = orig_repo

    assert exc.value.status_code == 500
    assert "Repository not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_all_sites_raises_500_when_dependencies_not_set():
    """get_all_sites should raise HTTP 500 if either repository or aggregator is
    missing.
    """
    orig_repo = routes_api._repository
    orig_agg = routes_api._aggregator
    try:
        routes_api._repository = None
        routes_api._aggregator = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_all_sites()
    finally:
        routes_api._repository = orig_repo
        routes_api._aggregator = orig_agg

    assert exc.value.status_code == 500
    assert "Dependencies not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_stats_raises_500_when_repository_not_set():
    """get_stats should raise HTTP 500 if repository dependency is missing."""
    orig_repo = routes_api._repository
    try:
        routes_api._repository = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_stats()
    finally:
        routes_api._repository = orig_repo

    assert exc.value.status_code == 500
    assert "Repository not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_get_system_data_404_when_no_sites():
    """get_system_data should return 404 when aggregator reports no sites."""
    orig_agg = routes_api._aggregator
    try:
        routes_api._aggregator = _DummyEmptyAggregator()
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_system_data(name="Nowhere System")
    finally:
        routes_api._aggregator = orig_agg

    assert exc.value.status_code == 404
    assert "No construction sites found in system" in exc.value.detail


@pytest.mark.asyncio
async def test_get_system_commodities_404_when_no_sites():
    """get_system_commodities should return 404 when aggregator reports no sites."""
    orig_agg = routes_api._aggregator
    try:
        routes_api._aggregator = _DummyEmptyAggregator()
        with pytest.raises(HTTPException) as exc:
            await routes_api.get_system_commodities(name="Nowhere System")
    finally:
        routes_api._aggregator = orig_agg

    assert exc.value.status_code == 404
    assert "No construction sites found in system" in exc.value.detail


@pytest.mark.asyncio
async def test_reload_journals_raises_500_when_repository_not_set():
    """reload_journals should raise HTTP 500 if repository dependency is missing."""
    orig_repo = routes_api._repository
    try:
        routes_api._repository = None
        with pytest.raises(HTTPException) as exc:
            await routes_api.reload_journals()
    finally:
        routes_api._repository = orig_repo

    assert exc.value.status_code == 500
    assert "Repository not initialized" in exc.value.detail


@pytest.mark.asyncio
async def test_reload_journals_missing_directory_returns_404(
    repository: ColonisationRepository, tmp_path: Path
):
    """reload_journals should raise 404 when configured journal directory does not
    exist.
    """
    missing_dir = tmp_path / "no_such_dir"

    class _Cfg:
        class _Journal:
            directory = str(missing_dir)

        journal = _Journal()

    orig_repo = routes_api._repository
    orig_get_config = config_module.get_config
    try:
        routes_api._repository = repository
        config_module.get_config = lambda: _Cfg()  # type: ignore[assignment]
        with pytest.raises(HTTPException) as exc:
            await routes_api.reload_journals()
    finally:
        routes_api._repository = orig_repo
        config_module.get_config = orig_get_config

    assert exc.value.status_code == 404
    assert "Journal directory not found" in exc.value.detail


@pytest.mark.asyncio
async def test_reload_journals_processes_journal_files(
    repository: ColonisationRepository, tmp_path: Path, sample_journal_line: str
):
    """
    reload_journals should parse all Journal.*.log files in the configured directory
    and return simple stats about processed depot events.
    """
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    journal_file = journal_dir / "Journal.2025-01-01T000000.01.log"
    journal_file.write_text(sample_journal_line + "\n", encoding="utf-8")

    class _Cfg:
        class _Journal:
            directory = str(journal_dir)

        journal = _Journal()

    orig_repo = routes_api._repository
    orig_get_config = config_module.get_config
    try:
        routes_api._repository = repository
        config_module.get_config = lambda: _Cfg()  # type: ignore[assignment]

        result = await routes_api.reload_journals()
    finally:
        routes_api._repository = orig_repo
        config_module.get_config = orig_get_config

    # We wrote exactly one file with a single ColonisationConstructionDepotEvent
    assert result["total_events"] == 1
    assert result["processed_files"] == [journal_file.name]
    assert result["journal_directory"] == str(journal_dir)
