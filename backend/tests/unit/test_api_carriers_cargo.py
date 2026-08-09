"""Cargo rows, recent-file scans and docked-context scoping.

Split out of test_api_carriers.py; the scaffolding lives in
_test_api_carriers_support.py.
"""

import json
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
async def test_carrier_sell_order_without_stock_or_outstanding_creates_no_cargo_row(
    tmp_path: Path, monkeypatch: Callable
):
    """Regression: do not treat SaleOrder (configured size) as cargo stock.

    Some journals emit CarrierTradeOrder lines with only SaleOrder + Price and
    omit Stock/Outstanding. Those lines should still create a SELL order but
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
    # Deliberately an event that says nothing about where the COMMANDER is.
    # This test is about scanning back through files for trade orders, so the
    # newer file only needs to exist and carry something. An FSDJump would no
    # longer be neutral: jumping to another system means the commander is not
    # on the carrier any more, which is now reported as such. See
    # test_carrier_docking for that behaviour on its own.
    newer_events = [
        {
            "timestamp": "2025-12-16T01:02:03Z",
            "event": "CarrierStats",
            "CarrierID": 3700569600,
            "CarrierType": "FleetCarrier",
            "Callsign": "X7J-BQG",
            "Name": "MIDNIGHT ELOQUENCE",
        }
    ]

    older_file.write_text(
        "\n".join(json.dumps(e) for e in older_events), encoding="utf-8"
    )
    newer_file.write_text(
        "\n".join(json.dumps(e) for e in newer_events), encoding="utf-8"
    )

    # Simulate newest file being "newer" by mtime to match production ordering.
    older_file.touch()
    newer_file.touch()

    monkeypatch.setattr(carriers_api, "get_journal_directory", lambda: journal_dir)
    # Let get_journal_files return both.
    monkeypatch.setattr(
        carriers_api, "get_journal_files", lambda _dir: [older_file, newer_file]
    )

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

    # New session: commander docks again but no trade orders at all.
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
    monkeypatch.setattr(
        carriers_api, "get_journal_files", lambda _dir: [old_file, new_file]
    )

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
