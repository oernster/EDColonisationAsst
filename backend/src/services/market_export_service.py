"""Helpers for Elite Dangerous market export files (Market.json).

Elite writes several "companion" JSON exports into the journal directory,
including Market.json, Cargo.json, and Status.json.

For Fleet Carriers, Market.json is often the *only* authoritative source for
the currently configured market orders (especially buy orders) during a docked
session, because CarrierTradeOrder journal events are not always emitted when
the market is configured/changed.

This module intentionally uses only the Python standard library.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional


def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse ED timestamps like '2026-05-01T11:25:25Z' into an aware datetime."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _as_int(val: object) -> Optional[int]:
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(round(val))
    return None


def _as_str(val: object) -> Optional[str]:
    return val if isinstance(val, str) else None


_NAME_TOKEN_RE = re.compile(r"^\$(?P<name>[a-z0-9_]+)_name;$", re.IGNORECASE)


def normalise_market_item_name(raw_name: str) -> str:
    """Convert Market.json 'Name' tokens into a stable commodity key.

    Observed form:
      - '$titanium_name;' -> 'titanium'

    Fallback is best-effort: strip '$' and ';', remove a trailing '_name'.
    """
    name = (raw_name or "").strip()
    if not name:
        return ""

    m = _NAME_TOKEN_RE.match(name)
    if m:
        return m.group("name").lower()

    # Defensive fallback.
    lowered = name.lower().strip("$;")
    if lowered.endswith("_name"):
        lowered = lowered[: -len("_name")]
    return lowered


@dataclass(frozen=True)
class MarketExportItem:
    commodity_key: str
    name_token: str | None
    name_localised: str | None
    demand: int
    stock: int
    buy_price: int
    sell_price: int


@dataclass(frozen=True)
class MarketExportSnapshot:
    timestamp: datetime | None
    station_type: str | None
    station_name: str | None
    star_system: str | None
    market_id: int | None
    items: tuple[MarketExportItem, ...]


def load_market_export(journal_dir: Path) -> Optional[MarketExportSnapshot]:
    """Load Market.json from the journal directory, if present and valid."""
    path = journal_dir / "Market.json"
    if not path.exists() or not path.is_file():
        return None

    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    if data.get("event") not in ("Market", "market"):
        # Non-market export or corrupt file.
        return None

    ts = _parse_ts(_as_str(data.get("timestamp")) or "")
    station_type = _as_str(data.get("StationType"))
    station_name = _as_str(data.get("StationName"))
    star_system = _as_str(data.get("StarSystem"))
    market_id = _as_int(data.get("MarketID"))

    items_raw = data.get("Items")
    items: list[MarketExportItem] = []
    if isinstance(items_raw, list):
        for it in items_raw:
            if not isinstance(it, dict):
                continue
            name_token = _as_str(it.get("Name"))
            commodity_key = normalise_market_item_name(name_token or "")
            if not commodity_key:
                # Without a stable key, we cannot merge/identify reliably.
                continue

            items.append(
                MarketExportItem(
                    commodity_key=commodity_key,
                    name_token=name_token,
                    name_localised=_as_str(it.get("Name_Localised")),
                    demand=max(_as_int(it.get("Demand")) or 0, 0),
                    stock=max(_as_int(it.get("Stock")) or 0, 0),
                    buy_price=max(_as_int(it.get("BuyPrice")) or 0, 0),
                    sell_price=max(_as_int(it.get("SellPrice")) or 0, 0),
                )
            )

    return MarketExportSnapshot(
        timestamp=ts,
        station_type=station_type,
        station_name=station_name,
        star_system=star_system,
        market_id=market_id,
        items=tuple(items),
    )

