"""Fleet listing and the not-docked case.

Split out of test_api_carriers.py; the scaffolding lives in _test_api_carriers_support.py.
"""

from pathlib import Path
from typing import Callable
import httpx
import pytest
from fastapi import FastAPI
import src.api.carriers as carriers_api
from src.api.carriers import router as carriers_router

from tests.unit._test_api_carriers_support import (
    _write_journal_file,
)


@pytest.mark.asyncio
async def test_carriers_mine_lists_own_and_squadron(
    tmp_path: Path, monkeypatch: Callable
):
    """Test /api/carriers/mine discovers own and squadron carriers from CarrierStats/CarrierLocation."""
    journal_dir = tmp_path / "journals"

    events = [
        {
            "timestamp": "2025-12-15T10:50:30Z",
            "event": "CarrierLocation",
            "CarrierType": "FleetCarrier",
            "CarrierID": 3700569600,
            "StarSystem": "Test System",
            "SystemAddress": 2278253693331,
            "BodyID": 0,
        },
        {
            "timestamp": "2025-12-15T10:55:20Z",
            "event": "CarrierStats",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "Callsign": "X7J-BQG",
            "Name": "MIDNIGHT ELOQUENCE",
            "DockingAccess": "squadron",
        },
    ]

    journal_file = _write_journal_file(journal_dir, events)

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(
        carriers_api,
        "get_journal_files",
        lambda _dir: [journal_file],
    )

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/carriers/mine")
        assert resp.status_code == 200
        data = resp.json()

        own_carriers = data["own_carriers"]
        squadron_carriers = data["squadron_carriers"]

        assert len(own_carriers) == 1
        assert own_carriers[0]["name"] == "MIDNIGHT ELOQUENCE"
        # DockingAccess 'squadron' is now surfaced on the identity but we no longer
        # infer an official squadron carrier list from it.
        assert own_carriers[0]["docking_access"] == "squadron"
        assert len(squadron_carriers) == 0


@pytest.mark.asyncio
async def test_carriers_current_state_404_when_not_docked_at_carrier(
    tmp_path: Path, monkeypatch: Callable
):
    """When the latest Docked event is not at a FleetCarrier, /current/state should return 404."""
    journal_dir = tmp_path / "journals"

    events = [
        {
            "timestamp": "2025-12-15T10:55:20Z",
            "event": "CarrierStats",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "Callsign": "X7J-BQG",
            "Name": "MIDNIGHT ELOQUENCE",
            "DockingAccess": "squadron",
        },
        {
            "timestamp": "2025-12-15T10:56:00Z",
            "event": "Docked",
            "StationName": "Some Station",
            "StationType": "Coriolis",
            "StarSystem": "Some System",
            "SystemAddress": 123,
            "MarketID": 111,
            "StationFaction": {"Name": "Faction"},
            "StationGovernment": "Democracy",
            "StationEconomy": "Industrial",
            "StationEconomies": [],
        },
    ]

    journal_file = _write_journal_file(journal_dir, events)

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(
        carriers_api,
        "get_journal_files",
        lambda _dir: [journal_file],
    )

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_current = await client.get("/api/carriers/current")
        assert resp_current.status_code == 200
        assert resp_current.json()["docked_at_carrier"] is False

        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 404
        assert "not currently docked" in resp_state.json()["detail"]
