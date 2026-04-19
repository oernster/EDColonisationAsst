"""End-to-end tests for REST API routes using real components (no mocking)."""

from datetime import datetime, UTC
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import src.config as config_module
from fastapi import FastAPI, HTTPException

from src.api import routes as routes_api
from src.api.routes import router as routes_router, set_dependencies
from src.models.colonisation import Commodity, ConstructionSite
from src.models.journal_events import DockedEvent
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.data_aggregator import DataAggregator
from src.services.system_tracker import SystemTracker


class _DummyInaraService:
    """Simple in-memory replacement for InaraService for tests.

    It exposes the same coroutine used by DataAggregator but never
    touches the network.
    """

    def __init__(self, sites_by_system: dict[str, list[dict]] | None = None) -> None:
        self._sites_by_system = sites_by_system or {}

    async def get_system_colonisation_data(self, system_name: str):
        return self._sites_by_system.get(system_name, [])


@pytest_asyncio.fixture
async def api_app(
    repository: ColonisationRepository,
    aggregator: DataAggregator,
    system_tracker: SystemTracker,
) -> FastAPI:
    """Create a FastAPI app wired with real dependencies for the colonisation API."""
    # Ensure Inara is offline-safe for tests
    aggregator._inara_service = _DummyInaraService()

    # Wire dependencies into the router globals
    set_dependencies(repository, aggregator, system_tracker)

    app = FastAPI()
    app.include_router(routes_router)
    yield app

    # Repository fixture already clears in teardown, but calling again is safe
    await repository.clear_all()


@pytest.mark.asyncio
async def test_health_endpoint(api_app: FastAPI):
    """Health endpoint should always respond with basic app/journal info."""
    async with httpx.AsyncClient(app=api_app, base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    # Basic shape checks; do not assert on actual journal path existence
    assert data["status"] == "healthy"
    assert "version" in data
    assert "build_id" in data
    assert "journal_directory" in data
    assert "journal_accessible" in data


@pytest.mark.asyncio
async def test_get_systems_empty(api_app: FastAPI):
    """When no sites exist, /systems should return an empty list."""
    async with httpx.AsyncClient(app=api_app, base_url="http://test") as client:
        resp = await client.get("/api/systems")
    assert resp.status_code == 200
    assert resp.json() == {"systems": []}


@pytest.mark.asyncio
async def test_system_lifecycle_and_stats(
    api_app: FastAPI,
    repository: ColonisationRepository,
    system_tracker: SystemTracker,
):
    """Exercise system-level endpoints with a couple of real construction sites."""
    # Seed repository with two sites in different systems
    site1 = ConstructionSite(
        market_id=1,
        station_name="Alpha Depot",
        station_type="Depot",
        system_name="Alpha System",
        system_address=111,
        construction_progress=25.0,
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
    site2 = ConstructionSite(
        market_id=2,
        station_name="Beta Depot",
        station_type="Depot",
        system_name="Beta System",
        system_address=222,
        construction_progress=100.0,
        construction_complete=True,
        construction_failed=False,
        commodities=[],
        last_updated=datetime.now(UTC),
    )
    await repository.add_construction_site(site1)
    await repository.add_construction_site(site2)

    async with httpx.AsyncClient(app=api_app, base_url="http://test") as client:
        # /systems should list both systems
        resp = await client.get("/api/systems")
        assert resp.status_code == 200
        systems = set(resp.json()["systems"])
        assert {"Alpha System", "Beta System"}.issubset(systems)

        # /systems/search should filter
        resp = await client.get("/api/systems/search", params={"q": "Alpha"})
        assert resp.status_code == 200
        assert resp.json()["systems"] == ["Alpha System"]

        # /system returns aggregated data for Alpha System
        resp = await client.get("/api/system", params={"name": "Alpha System"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_name"] == "Alpha System"
        assert data["total_sites"] == 1
        assert data["in_progress_sites"] == 1
        assert data["completed_sites"] == 0

        # /system/commodities returns aggregates for that system
        resp = await client.get(
            "/api/system/commodities", params={"name": "Alpha System"}
        )
        assert resp.status_code == 200
        commodities = resp.json()["commodities"]
        assert len(commodities) == 1
        steel = commodities[0]
        assert steel["commodity_name"] == "Steel"

        # /sites lists sites split by completion status
        resp = await client.get("/api/sites")
        assert resp.status_code == 200
        sites_payload = resp.json()
        in_progress_ids = {s["market_id"] for s in sites_payload["in_progress_sites"]}
        completed_ids = {s["market_id"] for s in sites_payload["completed_sites"]}
        assert in_progress_ids == {1}
        assert completed_ids == {2}

        # /sites/{market_id} returns detail
        resp = await client.get("/api/sites/1")
        assert resp.status_code == 200
        assert resp.json()["site"]["station_name"] == "Alpha Depot"

        # Non-existent site returns 404
        resp = await client.get("/api/sites/9999")
        assert resp.status_code == 404

        # /stats wraps repository.get_stats
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total_systems"] >= 2
        assert stats["total_sites"] >= 2
        assert stats["completed_sites"] >= 1


@pytest.mark.asyncio
async def test_get_current_system_endpoint(
    api_app: FastAPI, system_tracker: SystemTracker
):
    """Verify /systems/current reflects SystemTracker state."""
    # Simulate a DockedEvent updating the tracker
    event = DockedEvent(
        timestamp=datetime.now(UTC),
        event="Docked",
        station_name="Gamma Station",
        station_type="Outpost",
        star_system="Gamma System",
        system_address=333,
        market_id=123,
        station_faction={"Name": "Gamma Faction"},
        station_government="Democracy",
        station_economy="Industrial",
        station_economies=[],
        raw_data={},
    )
    system_tracker.update_from_docked(event)

    async with httpx.AsyncClient(app=api_app, base_url="http://test") as client:
        resp = await client.get("/api/systems/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["system_name"] == "Gamma System"
    assert data["station_name"] == "Gamma Station"
    assert data["is_docked"] is True


# ---------------------------------------------------------------------------
# Guard-rail tests for uninitialised dependencies
# ---------------------------------------------------------------------------


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
    """get_all_sites should raise HTTP 500 if either repository or aggregator is missing."""
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


# ---------------------------------------------------------------------------
# 404 branches for empty systems
# ---------------------------------------------------------------------------


class _DummyEmptySystemData:
    total_sites = 0


class _DummyEmptyAggregator:
    async def aggregate_by_system(self, name: str):  # pragma: no cover - trivial
        return _DummyEmptySystemData()


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


# ---------------------------------------------------------------------------
# /debug/reload-journals endpoint
# ---------------------------------------------------------------------------


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
    """reload_journals should raise 404 when configured journal directory does not exist."""
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
