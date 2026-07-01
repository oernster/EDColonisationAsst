"""Coverage tests for the Market.json export helpers.

Closes the remaining lines and branches in
src/services/market_export_service.py using real files under tmp_path
and direct calls to the parsing helpers (no mock libraries).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from src.services.market_export_service import (
    _as_int,
    _as_str,
    _parse_ts,
    load_market_export,
    normalise_market_item_name,
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def test_parse_ts_handles_empty_invalid_and_valid_values() -> None:
    """Timestamp parsing should tolerate empty and malformed input."""
    assert _parse_ts("") is None
    assert _parse_ts("not-a-timestamp") is None

    parsed = _parse_ts("2026-05-01T11:25:25Z")
    assert parsed == datetime(2026, 5, 1, 11, 25, 25, tzinfo=timezone.utc)


def test_as_int_rejects_bools_and_non_numbers() -> None:
    """Integer coercion should accept ints and floats but reject bools and strings."""
    assert _as_int(True) is None
    assert _as_int(False) is None
    assert _as_int(7) == 7
    assert _as_int(1.6) == 2
    assert _as_int("42") is None
    assert _as_int(None) is None


def test_as_str_only_accepts_strings() -> None:
    """String coercion should pass strings through and reject other types."""
    assert _as_str("hello") == "hello"
    assert _as_str(5) is None


def test_normalise_market_item_name_variants() -> None:
    """Name normalisation should handle tokens, fallbacks and empty input."""
    assert normalise_market_item_name("") == ""
    assert normalise_market_item_name("$titanium_name;") == "titanium"
    # Fallback path: not a well-formed token but ends with _name.
    assert normalise_market_item_name("steel_name") == "steel"
    # Fallback path: not a token and no _name suffix.
    assert normalise_market_item_name("gold") == "gold"


# ---------------------------------------------------------------------------
# load_market_export
# ---------------------------------------------------------------------------


def test_load_market_export_missing_file(tmp_path: Path) -> None:
    """A directory without Market.json should yield no snapshot."""
    assert load_market_export(tmp_path) is None


def test_load_market_export_invalid_json(tmp_path: Path) -> None:
    """Corrupt JSON should yield no snapshot."""
    (tmp_path / "Market.json").write_text("{not valid json", encoding="utf-8")
    assert load_market_export(tmp_path) is None


def test_load_market_export_non_dict_payload(tmp_path: Path) -> None:
    """A JSON payload that is not an object should yield no snapshot."""
    (tmp_path / "Market.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_market_export(tmp_path) is None


def test_load_market_export_wrong_event(tmp_path: Path) -> None:
    """A non-market export should yield no snapshot."""
    (tmp_path / "Market.json").write_text(
        json.dumps({"event": "Cargo"}), encoding="utf-8"
    )
    assert load_market_export(tmp_path) is None


def test_load_market_export_items_not_a_list(tmp_path: Path) -> None:
    """A market export whose Items field is malformed should have no items."""
    payload = {
        "event": "Market",
        "timestamp": "2026-05-01T11:25:25Z",
        "StationType": "FleetCarrier",
        "StationName": "K7Q-BQL",
        "StarSystem": "Test System",
        "MarketID": 123,
        "Items": {"unexpected": "shape"},
    }
    (tmp_path / "Market.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_market_export(tmp_path)
    assert snapshot is not None
    assert snapshot.items == ()
    assert snapshot.market_id == 123


def test_load_market_export_full_snapshot_with_bad_entries(tmp_path: Path) -> None:
    """Valid items should be parsed while malformed entries are skipped."""
    payload = {
        "event": "Market",
        "timestamp": "2026-05-01T11:25:25Z",
        "StationType": "FleetCarrier",
        "StationName": "K7Q-BQL",
        "StarSystem": "Test System",
        "MarketID": 456,
        "Items": [
            {
                "Name": "$titanium_name;",
                "Name_Localised": "Titanium",
                "Demand": 100,
                "Stock": 5,
                "BuyPrice": 1000,
                "SellPrice": 1200,
            },
            "not-a-dict",
            {"Demand": 10},
        ],
    }
    (tmp_path / "Market.json").write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_market_export(tmp_path)
    assert snapshot is not None
    assert snapshot.station_type == "FleetCarrier"
    assert snapshot.station_name == "K7Q-BQL"
    assert snapshot.star_system == "Test System"
    assert snapshot.market_id == 456
    assert snapshot.timestamp == datetime(2026, 5, 1, 11, 25, 25, tzinfo=timezone.utc)

    # Only the well-formed entry should survive.
    assert len(snapshot.items) == 1
    item = snapshot.items[0]
    assert item.commodity_key == "titanium"
    assert item.name_token == "$titanium_name;"
    assert item.name_localised == "Titanium"
    assert item.demand == 100
    assert item.stock == 5
    assert item.buy_price == 1000
    assert item.sell_price == 1200
