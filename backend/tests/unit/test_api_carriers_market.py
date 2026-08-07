"""Market.json fallback and sold-out cargo.

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
    _write_market_export,
)


@pytest.mark.asyncio
async def test_carriers_state_falls_back_to_market_json_when_no_trade_orders_since_docked(
    tmp_path: Path, monkeypatch: Callable
):
    """Use Market.json as authoritative market snapshot when journal trade orders are absent."""
    journal_dir = tmp_path / "journals"

    events = [
        {
            "timestamp": "2025-12-15T11:24:47Z",
            "event": "Docked",
            "StationName": "X7J-BQG",
            "StationType": "FleetCarrier",
            "StarSystem": "Test System",
            "SystemAddress": 2278253693331,
            "MarketID": 3700569600,
            "StationFaction": {"Name": "FleetCarrier"},
            "StationGovernment": "$government_Carrier;",
            "StationEconomy": "$economy_Carrier;",
            "StationEconomies": [{"Name": "$economy_Carrier;", "Proportion": 1.0}],
        },
        # No CarrierTradeOrder events at all.
    ]

    journal_file = _write_journal_file(journal_dir, events)
    _write_market_export(
        journal_dir,
        market_id=3700569600,
        timestamp="2025-12-15T11:25:25Z",
        items=[
            {
                "id": 111,
                "Name": "$steel_name;",
                "Name_Localised": "Steel",
                "BuyPrice": 0,
                "SellPrice": 209,
                "Demand": 7705,
                "Stock": 0,
                "Category": "$MARKET_category_metals;",
                "Category_Localised": "Metals",
            },
            {
                "id": 112,
                "Name": "$titanium_name;",
                "Name_Localised": "Titanium",
                "BuyPrice": 0,
                "SellPrice": 223,
                "Demand": 4606,
                "Stock": 0,
                "Category": "$MARKET_category_metals;",
                "Category_Localised": "Metals",
            },
        ],
    )

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(carriers_api, "get_journal_files", lambda _dir: [journal_file])

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 200
        payload = resp_state.json()
        carrier_state = payload["carrier"]
        assert carrier_state is not None

        buy_orders = carrier_state["buy_orders"]
        assert any(
            o["commodity_name"] == "steel" and o["remaining_amount"] == 7705
            for o in buy_orders
        )
        assert any(
            o["commodity_name"] == "titanium" and o["remaining_amount"] == 4606
            for o in buy_orders
        )

        assert carrier_state["sell_orders"] == []
        assert carrier_state["cargo"] == []
        assert carrier_state["trade_orders_scope"] == "market_export"


@pytest.mark.asyncio
async def test_carriers_current_state_clears_sold_out_cargo(
    tmp_path: Path, monkeypatch: Callable
):
    """
    When a SELL order is later reported with zero Stock/Outstanding, the
    cargo view should no longer show positive stock for that commodity.
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
        # Another commodity that remains on the carrier (e.g. fruit and vegetables)
        {
            "timestamp": "2025-12-15T11:16:00Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "fruitandvegetables",
            "Commodity_Localised": "Fruit and Vegetables",
            "SaleOrder": 9,
            "Stock": 9,
            "Outstanding": 9,
            "Price": 1000,
        },
        # Initial SELL order for titanium with 23t for sale.
        {
            "timestamp": "2025-12-15T11:17:37Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "titanium",
            "Commodity_Localised": "Titanium",
            "SaleOrder": 23,
            "Stock": 23,
            "Outstanding": 23,
            "Price": 4446,
        },
        # Later update after the commander has bought all titanium. The journal
        # reports zero stock/outstanding; our aggregation should no longer show
        # positive stock for titanium in the cargo view.
        {
            "timestamp": "2025-12-15T11:25:00Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "titanium",
            "Commodity_Localised": "Titanium",
            "SaleOrder": 23,
            "Stock": 0,
            "Outstanding": 0,
            "Price": 4446,
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
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 200
        state_data = resp_state.json()
        carrier_state = state_data["carrier"]
        assert carrier_state is not None

        cargo = carrier_state["cargo"]
        assert isinstance(cargo, list)

        # Fruit and vegetables should still be present with 9t stock.
        assert any(
            item["commodity_name"] == "fruitandvegetables" and item["stock"] == 9
            for item in cargo
        )

        # Titanium should not report any positive stock after the zero-stock
        # CarrierTradeOrder update.
        assert not any(
            item["commodity_name"] == "titanium" and item["stock"] > 0 for item in cargo
        )
