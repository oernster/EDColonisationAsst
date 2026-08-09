"""Shared scaffolding for the test_coverage_carrier_service modules.

Split out of test_coverage_carrier_service.py when that file passed the module cap. Not
named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from src.models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
    DockedEvent,
)


CARRIER_MARKET_ID = 100


_BASE_TIME = datetime(2025, 12, 15, 10, 0, 0, tzinfo=timezone.utc)


def _ts(minute: int = 0) -> datetime:
    """Build a deterministic timezone-aware timestamp offset by minutes."""
    return _BASE_TIME + timedelta(minutes=minute)


def _docked(
    minute: int = 0,
    market_id: int = CARRIER_MARKET_ID,
    station_name: str = "X7J-BQG",
    station_type: str = "FleetCarrier",
    raw: Optional[dict[str, Any]] = None,
) -> DockedEvent:
    """Build a DockedEvent suitable for carrier state reconstruction."""
    return DockedEvent(
        timestamp=_ts(minute),
        event="Docked",
        station_name=station_name,
        station_type=station_type,
        star_system="Test System",
        system_address=1,
        market_id=market_id,
        station_faction={},
        station_government="",
        station_economy="",
        station_economies=[],
        raw_data=raw or {},
    )


def _stats(
    minute: int = 0,
    carrier_id: int = CARRIER_MARKET_ID,
    name: str = "MIDNIGHT ELOQUENCE",
    callsign: Optional[str] = None,
    market_id: Optional[int] = None,
    raw: Optional[dict[str, Any]] = None,
) -> CarrierStatsEvent:
    """Build a CarrierStatsEvent with optional raw payload."""
    return CarrierStatsEvent(
        timestamp=_ts(minute),
        event="CarrierStats",
        carrier_id=carrier_id,
        name=name,
        callsign=callsign,
        market_id=market_id,
        raw_data=raw or {},
    )


def _location(
    minute: int = 0,
    carrier_id: int = CARRIER_MARKET_ID,
    system: str = "Test System",
) -> CarrierLocationEvent:
    """Build a CarrierLocationEvent."""
    return CarrierLocationEvent(
        timestamp=_ts(minute),
        event="CarrierLocation",
        carrier_id=carrier_id,
        star_system=system,
        system_address=1,
        raw_data={},
    )


def _trade(
    minute: int = 0,
    carrier_id: int = CARRIER_MARKET_ID,
    commodity: str = "titanium",
    localised: Optional[str] = None,
    purchase: int = 0,
    sale: int = 0,
    stock: int = -1,
    outstanding: int = -1,
    price: int = 0,
    raw: Optional[dict[str, Any]] = None,
) -> CarrierTradeOrderEvent:
    """Build a CarrierTradeOrderEvent with sentinel defaults."""
    return CarrierTradeOrderEvent(
        timestamp=_ts(minute),
        event="CarrierTradeOrder",
        carrier_id=carrier_id,
        commodity=commodity,
        commodity_localised=localised,
        purchase_order=purchase,
        sale_order=sale,
        stock=stock,
        outstanding=outstanding,
        price=price,
        raw_data=raw or {},
    )


def _write_market(
    journal_dir: Path,
    market_id: int,
    timestamp: str,
    items: list[dict[str, Any]],
) -> None:
    """Write a FleetCarrier Market.json export into journal_dir."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": timestamp,
        "event": "Market",
        "StationName": "X7J-BQG",
        "StationType": "FleetCarrier",
        "StarSystem": "Test System",
        "MarketID": market_id,
        "Items": items,
    }
    (journal_dir / "Market.json").write_text(json.dumps(payload), encoding="utf-8")
