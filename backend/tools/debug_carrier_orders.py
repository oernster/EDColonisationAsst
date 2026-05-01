"""Debug helper: inspect Fleet Carrier trade-order data from local journal files.

This script is intentionally standalone and uses only the standard library so
that it can be run directly from the repo.

Usage (from repo root):

    c:/Users/Oliver/Development/EDColonisationAsst/venv/Scripts/python backend/tools/debug_carrier_orders.py

It will:
  - Find the latest Journal.*.log in the default Saved Games folder.
  - Locate the most recent Docked event at a FleetCarrier.
  - Summarise CarrierTradeOrder events for that carrier id, especially those
    after the last Docked timestamp.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def _parse_ts(ts: str) -> datetime:
    # Journal timestamps are ISO 8601, typically with a trailing 'Z'.
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _iter_json_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


@dataclass(frozen=True)
class CarrierContext:
    docked_ts: datetime
    station_name: str
    market_id: int
    star_system: str | None


def _find_latest_fc_docked(entries: list[dict[str, Any]]) -> CarrierContext | None:
    for obj in reversed(entries):
        if obj.get("event") != "Docked":
            continue
        if obj.get("StationType") != "FleetCarrier":
            continue
        ts = obj.get("timestamp")
        if not isinstance(ts, str):
            continue
        market_id = obj.get("MarketID")
        if not isinstance(market_id, int):
            continue
        station_name = obj.get("StationName")
        if not isinstance(station_name, str):
            station_name = ""
        star_system = obj.get("StarSystem")
        if not isinstance(star_system, str):
            star_system = None
        return CarrierContext(
            docked_ts=_parse_ts(ts),
            station_name=station_name,
            market_id=market_id,
            star_system=star_system,
        )
    return None


def main() -> int:
    journal_dir = Path(r"C:\Users\Oliver\Saved Games\Frontier Developments\Elite Dangerous")
    if not journal_dir.exists():
        print(f"Journal directory not found: {journal_dir}")
        return 2

    journals = sorted(journal_dir.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime)
    if not journals:
        print(f"No Journal.*.log files found under: {journal_dir}")
        return 2

    latest = journals[-1]
    print(f"Latest journal: {latest}")
    print(f"Last write: {datetime.fromtimestamp(latest.stat().st_mtime).isoformat()}")

    entries = list(_iter_json_lines(latest))
    print(f"Total JSON lines: {len(entries)}")

    ctx = _find_latest_fc_docked(entries)
    if ctx is None:
        print("No Docked event at a FleetCarrier found in latest journal.")
        return 0

    print("\n--- Current docking context (latest FleetCarrier Docked) ---")
    print(f"Docked timestamp: {ctx.docked_ts.isoformat()}")
    print(f"StationName/callsign: {ctx.station_name}")
    print(f"MarketID: {ctx.market_id}")
    if ctx.star_system:
        print(f"StarSystem: {ctx.star_system}")

    # CarrierStats (last 3)
    carrier_stats = [
        o
        for o in entries
        if o.get("event") == "CarrierStats" and o.get("CarrierID") == ctx.market_id
    ]
    print("\n--- CarrierStats (matching MarketID) ---")
    print(f"Count: {len(carrier_stats)}")
    for o in carrier_stats[-3:]:
        print(
            f"{o.get('timestamp')} CarrierID={o.get('CarrierID')} Callsign={o.get('Callsign')} Name={o.get('Name')} DockingAccess={o.get('DockingAccess')}"
        )

    # Trade orders
    trades = [
        o
        for o in entries
        if o.get("event") == "CarrierTradeOrder" and o.get("CarrierID") == ctx.market_id
    ]
    trades_sorted = sorted(
        (o for o in trades if isinstance(o.get("timestamp"), str)),
        key=lambda o: _parse_ts(o["timestamp"]),
    )

    print("\n--- CarrierTradeOrder summary (matching CarrierID==MarketID) ---")
    print(f"Total CarrierTradeOrder lines: {len(trades_sorted)}")
    if trades_sorted:
        print(
            "First/last ts:",
            trades_sorted[0]["timestamp"],
            "→",
            trades_sorted[-1]["timestamp"],
        )

    trades_after_dock = [
        o
        for o in trades_sorted
        if _parse_ts(o["timestamp"]) >= ctx.docked_ts
    ]
    print(f"CarrierTradeOrder AFTER dock: {len(trades_after_dock)}")

    # Last-known per commodity after docking
    per_commodity: dict[str, dict[str, Any]] = {}
    for o in trades_after_dock:
        commodity = o.get("Commodity")
        if not isinstance(commodity, str) or not commodity:
            continue
        per_commodity[commodity] = o

    print("\n--- Last known trade-order event per commodity AFTER dock ---")
    for commodity in sorted(per_commodity.keys()):
        o = per_commodity[commodity]
        ts = o.get("timestamp")
        sale = o.get("SaleOrder")
        purchase = o.get("PurchaseOrder")
        cancel = o.get("CancelTrade")
        stock = o.get("Stock")
        out = o.get("Outstanding")
        price = o.get("Price")
        print(
            f"{commodity:24} ts={ts} SaleOrder={sale} PurchaseOrder={purchase} CancelTrade={cancel} Stock={stock} Outstanding={out} Price={price}"
        )

    print("\n--- Last 50 CarrierTradeOrder lines AFTER dock (raw JSON) ---")
    for o in trades_after_dock[-50:]:
        print(json.dumps(o, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

