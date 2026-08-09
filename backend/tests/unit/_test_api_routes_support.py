"""Shared scaffolding for the test_api_routes modules.

Split out of test_api_routes.py when that file passed the module cap. Not named
test_* on purpose: pytest collects only the modules that use it.
"""

import pytest_asyncio
from fastapi import FastAPI
from src.api.health import router as health_router
from src.api.routes import router as routes_router, set_dependencies
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
    # Health lives on its own router now, and the tests below cover both.
    app.include_router(health_router)
    app.include_router(routes_router)
    yield app

    # Repository fixture already clears in teardown; calling again is safe
    await repository.clear_all()


class _DummyEmptySystemData:
    total_sites = 0


class _DummyEmptyAggregator:
    async def aggregate_by_system(self, name: str):  # pragma: no cover - trivial
        return _DummyEmptySystemData()
