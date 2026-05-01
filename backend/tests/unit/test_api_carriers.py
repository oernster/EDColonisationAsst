"""Tests for Fleet carrier REST API routes using real components (no mocking framework).

These tests exercise the new /api/carriers endpoints against realistic in-memory
journal data written to a temporary directory. They use the real JournalParser
and FastAPI router wiring; only simple monkeypatching of helper functions is used
to point the API at the test journal directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import httpx
import pytest
from fastapi import FastAPI

import src.api.carriers as carriers_api
from src.api.carriers import router as carriers_router


def _write_journal_file(journal_dir: Path, events: list[dict]) -> Path:
    """Helper to write a Journal.*.log file with the given JSON events."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    file_path = journal_dir / "Journal.2025-12-15T104644.01.log"
    lines = [json.dumps(e) for e in events]
    file_path.write_text("\n".join(lines), encoding="utf-8")
    return file_path


def _write_market_export(
    journal_dir: Path,
    *,
    market_id: int,
    station_name: str = "X7J-BQG",
    star_system: str = "Test System",
    timestamp: str = "2025-12-15T11:25:25Z",
    items: list[dict] | None = None,
) -> Path:
    """Helper to write a Market.json export in the journal directory."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    path = journal_dir / "Market.json"
    payload = {
        "timestamp": timestamp,
        "event": "Market",
        "StationName": station_name,
        "StationType": "FleetCarrier",
        "StarSystem": star_system,
        "MarketID": market_id,
        "Items": items or [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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


@pytest.mark.asyncio
async def test_carrier_sell_order_without_stock_or_outstanding_does_not_create_cargo_row(
    tmp_path: Path, monkeypatch: Callable
):
    """Regression: do not treat SaleOrder (configured size) as cargo stock.

    Some journals emit CarrierTradeOrder lines with only SaleOrder + Price and
    omit Stock/Outstanding. Those lines should still create a SELL order, but
    must NOT create a cargo commodity row, otherwise the UI shows phantom cargo.
    """
    journal_dir = tmp_path / "journals"

    events = [
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
            "StationEconomies": [{"Name": "$economy_Carrier;", "Proportion": 1.0}],
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
            "Price": 4446,
            # Intentionally omit Stock and Outstanding
        },
    ]

    journal_file = _write_journal_file(journal_dir, events)

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(carriers_api, "get_journal_files", lambda _dir: [journal_file])

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 200
        state_data = resp_state.json()
        carrier_state = state_data["carrier"]
        assert carrier_state is not None

        # Order should exist
        sell_orders = carrier_state["sell_orders"]
        assert any(
            order["commodity_name"] == "titanium" and order["order_type"] == "sell"
            for order in sell_orders
        )

        # Cargo should NOT include titanium because stock is unknown
        cargo = carrier_state["cargo"]
        assert isinstance(cargo, list)
        assert not any(item["commodity_name"] == "titanium" for item in cargo)


@pytest.mark.asyncio
async def test_carriers_scan_recent_files_for_most_recent_trade_orders(
    tmp_path: Path, monkeypatch: Callable
):
    """Carrier data should be recovered even when it is not in the latest journal.

    Scenario:
      - An older journal contains Docked + CarrierStats + trade order events.
      - The newest journal contains unrelated events only.
    The /api/carriers endpoints should still pick up the carrier context from the
    older file by scanning recent files.
    """
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir(parents=True, exist_ok=True)

    older_file = journal_dir / "Journal.2025-12-15T104644.01.log"
    newer_file = journal_dir / "Journal.2025-12-16T010101.01.log"

    older_events = [
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
            "StationEconomies": [{"Name": "$economy_Carrier;", "Proportion": 1.0}],
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
    newer_events = [
        {
            "timestamp": "2025-12-16T01:02:03Z",
            "event": "FSDJump",
            "StarSystem": "Other System",
            "SystemAddress": 999,
        }
    ]

    older_file.write_text("\n".join(json.dumps(e) for e in older_events), encoding="utf-8")
    newer_file.write_text("\n".join(json.dumps(e) for e in newer_events), encoding="utf-8")

    # Simulate newest file being "newer" by mtime to match production ordering.
    older_file.touch()
    newer_file.touch()

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    # Let get_journal_files return both.
    monkeypatch.setattr(carriers_api, "get_journal_files", lambda _dir: [older_file, newer_file])

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_current = await client.get("/api/carriers/current")
        assert resp_current.status_code == 200
        current_data = resp_current.json()
        assert current_data["docked_at_carrier"] is True
        assert current_data["carrier"]["name"] == "MIDNIGHT ELOQUENCE"


@pytest.mark.asyncio
async def test_carriers_current_state_ignores_trade_orders_before_latest_docked_context(
    tmp_path: Path, monkeypatch: Callable
):
    """Regression: old trade orders from previous sessions should not linger.

    The API scans multiple recent journal files. If old CarrierTradeOrder events
    are included without a newer cancel, they must not be treated as active for
    the current docking context.
    """
    journal_dir = tmp_path / "journals"

    # Old session (older timestamp) contains a SELL order.
    old_events = [
        {
            "timestamp": "2025-12-14T10:54:47Z",
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
        {
            "timestamp": "2025-12-14T11:17:37Z",
            "event": "CarrierTradeOrder",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "BlackMarket": False,
            "Commodity": "aluminium",
            "Commodity_Localised": "Aluminium",
            "SaleOrder": 99,
            "Stock": 99,
            "Outstanding": 99,
            "Price": 127,
        },
    ]

    # New session: commander docks again, but no trade orders at all.
    new_events = [
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
            "StationEconomies": [{"Name": "$economy_Carrier;", "Proportion": 1.0}],
        }
    ]

    old_file = _write_journal_file(journal_dir, old_events)
    new_file = journal_dir / "Journal.2025-12-15T104644.01.log"
    new_file.write_text("\n".join(json.dumps(e) for e in new_events), encoding="utf-8")

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    monkeypatch.setattr(carriers_api, "get_journal_files", lambda _dir: [old_file, new_file])

    app = FastAPI()
    app.include_router(carriers_router)

    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp_state = await client.get("/api/carriers/current/state")
        assert resp_state.status_code == 200
        carrier_state = resp_state.json()["carrier"]
        assert carrier_state is not None

        # Old aluminium sell order should NOT be used as current state.
        # We expect the API to return no orders/cargo for this session.
        assert carrier_state["sell_orders"] == []
        assert carrier_state["cargo"] == []
        assert carrier_state.get("trade_orders_scope") in {"stale", "none"}


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
            o["commodity_name"] == "steel" and o["remaining_amount"] == 7705 for o in buy_orders
        )
        assert any(
            o["commodity_name"] == "titanium" and o["remaining_amount"] == 4606 for o in buy_orders
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
            item["commodity_name"] == "titanium" and item["stock"] > 0
            for item in cargo
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
        # DockingAccess 'squadron' is now surfaced on the identity, but we no longer
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
