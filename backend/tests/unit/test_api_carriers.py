"""Current carrier and state for a docked fleet carrier.

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
async def test_carriers_current_and_state_with_fleet_carrier(
    tmp_path: Path, monkeypatch: Callable
):
    """End-to-end test for /api/carriers/current and /api/carriers/current/state.

    Verifies that:
      - The API recognises a FleetCarrier docking context.
      - Carrier identity is built from CarrierStats/Docked/CarrierLocation.
      - Cargo, buy_orders, sell_orders and total_cargo_tonnage are populated
        from CarrierTradeOrder and CarrierStats events.
    """
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
            "SpaceUsage": {
                "TotalCapacity": 25000,
                "Crew": 3370,
                "Cargo": 2316,
                "CargoSpaceReserved": 0,
                "ShipPacks": 0,
                "ModulePacks": 0,
                "FreeSpace": 19314,
            },
            "Crew": [
                {
                    "CrewRole": "Captain",
                    "Activated": True,
                    "Enabled": True,
                    "CrewName": "Swara Phillips",
                },
                {
                    "CrewRole": "Exploration",
                    "Activated": True,
                    "Enabled": True,
                    "CrewName": "Roland Lechner",
                },
                {
                    "CrewRole": "Outfitting",
                    "Activated": True,
                    "Enabled": True,
                    "CrewName": "Alvaro Stokes",
                },
            ],
        },
        {
            "timestamp": "2025-12-15T10:54:47Z",
            "event": "Docked",
            "StationName": "X7J-BQG",
            "StationType": "FleetCarrier",
            "StarSystem": "Test System",
            "SystemAddress": 2278253693331,
            "MarketID": 3700569600,
            "StationFaction": {"Name": "FleetCarrier"},
            "StationGovernment": "$government_Carrier;",
            "StationEconomy": "$economy_Carrier;",
            "StationEconomies": [
                {"Name": "$economy_Carrier;", "Proportion": 1.0},
            ],
        },
        {
            "timestamp": "2025-12-15T11:17:37Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "titanium",
            "Commodity_Localised": "Titanium",
            "SaleOrder": 23,
            # Provide Stock/Outstanding so the API can derive a per-commodity
            # market-stock row for the cargo snapshot.
            "Stock": 23,
            "Outstanding": 23,
            "Price": 4446,
        },
        {
            "timestamp": "2025-12-15T11:20:15Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "tritium",
            "Commodity_Localised": "Tritium",
            "PurchaseOrder": 5,
            "Price": 51294,
        },
    ]

    journal_file = _write_journal_file(journal_dir, events)

    # Point the carriers API at our test journal directory/file
    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(
        carriers_api,
        "get_journal_files",
        lambda _dir: [journal_file],
    )

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        # /api/carriers/current
        resp_current = await client.get("/api/carriers/current")
        assert resp_current.status_code == 200
        current_data = resp_current.json()
        assert current_data["docked_at_carrier"] is True
        carrier = current_data["carrier"]
        assert carrier is not None
        assert carrier["name"] == "MIDNIGHT ELOQUENCE"
        assert carrier["callsign"] == "X7J-BQG"
        assert carrier["last_seen_system"] == "Test System"

        # /api/carriers/current/state
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 200
        state_data = resp_state.json()
        carrier_state = state_data["carrier"]
        assert carrier_state is not None

        identity = carrier_state["identity"]
        assert identity["name"] == "MIDNIGHT ELOQUENCE"
        assert identity["callsign"] == "X7J-BQG"

        # total_cargo_tonnage from CarrierStats.SpaceUsage.Cargo
        assert carrier_state["total_cargo_tonnage"] == 2316
        # total_capacity_tonnage and free_space_tonnage from CarrierStats.SpaceUsage
        assert carrier_state["total_capacity_tonnage"] == 25000
        assert carrier_state["free_space_tonnage"] == 19314

        # Services should include at least exploration and outfitting based on CarrierStats.Crew
        services = identity.get("services") or []
        assert isinstance(services, list)
        assert "exploration" in services
        assert "outfitting" in services

        # Cargo derived from SELL orders (titanium)
        cargo = carrier_state["cargo"]
        assert isinstance(cargo, list)
        assert any(
            item["commodity_name"] == "titanium" and item["stock"] == 23
            for item in cargo
        )

        # Buy and sell orders from CarrierTradeOrder
        buy_orders = carrier_state["buy_orders"]
        sell_orders = carrier_state["sell_orders"]

        assert any(
            order["commodity_name"] == "tritium"
            and order["original_amount"] == 5
            and order["order_type"] == "buy"
            for order in buy_orders
        )
        assert any(
            order["commodity_name"] == "titanium"
            and order["original_amount"] == 23
            and order["order_type"] == "sell"
            for order in sell_orders
        )
