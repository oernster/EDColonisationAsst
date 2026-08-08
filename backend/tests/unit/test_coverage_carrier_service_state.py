"""State reconstruction, market export and space usage.

Split out of test_coverage_carrier_service.py; the scaffolding lives in _test_coverage_carrier_service_support.py.
"""

from pathlib import Path
import pytest
import src.utils.journal as journal_utils
from src.services.carrier_service import (
    _normalise_carrier_commodity_key,
    _prettify_commodity_name,
    build_current_carrier_response,
    build_current_carrier_state_response,
    build_identity_from_journal,
    build_my_carriers_response,
    build_orders_for_carrier,
    find_latest_carrier_stats_for_callsign,
    find_latest_carrier_stats_for_id,
    find_latest_carrier_stats_for_market_id,
)

from tests.unit._test_coverage_carrier_service_support import (
    CARRIER_MARKET_ID,
    _docked,
    _location,
    _stats,
    _trade,
    _write_market,
)


def test_my_carriers_uses_real_docked_event_and_dedupes_stats() -> None:
    """A real FleetCarrier Docked event is preferred; stats are deduped."""
    docked_fc = _docked(minute=1)
    docked_station = _docked(minute=2, market_id=42, station_type="Coriolis")
    first_stats = _stats(minute=3, name="FIRST SEEN")
    duplicate_stats = _stats(minute=4, name="DUPLICATE")
    response = build_my_carriers_response(
        [docked_fc, docked_station, first_stats, duplicate_stats]
    )
    assert len(response.own_carriers) == 1
    assert response.own_carriers[0].name == "FIRST SEEN"
    assert response.own_carriers[0].market_id == CARRIER_MARKET_ID


def test_state_callsign_fallback_and_location_by_carrier_id(tmp_path: Path) -> None:
    """Stats found by callsign also drive the CarrierLocation lookup."""
    docked = _docked(minute=0, market_id=200, station_name="QQQ-111")
    stats = _stats(minute=1, carrier_id=300, callsign="QQQ-111", name="FALLBACK")
    location = _location(minute=2, carrier_id=300, system="Elsewhere")
    response = build_current_carrier_state_response(
        [docked, stats, location], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.identity.callsign == "QQQ-111"
    assert state.identity.carrier_id == 300
    assert state.identity.last_seen_system == "Elsewhere"
    assert state.snapshot_time == location.timestamp


def test_state_marks_old_trade_orders_stale(tmp_path: Path) -> None:
    """Trade orders far older than the newest journal activity are dropped."""
    docked = _docked(minute=0)
    trade = _trade(minute=1, commodity="gold", sale=5, stock=5)
    later_activity = _location(minute=45)
    response = build_current_carrier_state_response(
        [docked, trade, later_activity], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.trade_orders_scope == "stale"
    assert state.sell_orders == []
    assert state.cargo == []


def test_state_resolves_journal_dir_when_not_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A None journal_dir falls back to get_journal_directory."""
    monkeypatch.setattr(journal_utils, "get_journal_directory", lambda: tmp_path)
    response = build_current_carrier_state_response([_docked()], journal_dir=None)
    assert response is not None
    assert response.carrier.trade_orders_scope == "none"


def test_state_swallows_market_export_resolution_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Errors while resolving the journal directory are non-fatal."""

    def _boom() -> Path:
        raise RuntimeError("journal directory unavailable")

    monkeypatch.setattr(journal_utils, "get_journal_directory", _boom)
    response = build_current_carrier_state_response([_docked()], journal_dir=None)
    assert response is not None
    assert response.carrier.trade_orders_scope == "none"


def test_state_market_export_produces_sell_orders_and_cargo(tmp_path: Path) -> None:
    """Market.json stock entries become SELL orders plus cargo rows."""
    docked = _docked(minute=0)
    _write_market(
        tmp_path,
        CARRIER_MARKET_ID,
        "2025-12-15T10:05:00Z",
        [
            {
                "Name": "$gold_name;",
                "Name_Localised": "Gold",
                "Demand": 0,
                "Stock": 50,
                "BuyPrice": 100,
                "SellPrice": 0,
            },
            {
                "Name": "$silver_name;",
                "Name_Localised": "Silver",
                "Demand": 0,
                "Stock": 8,
                "BuyPrice": 0,
                "SellPrice": 20,
            },
            {
                "Name": "$steel_name;",
                "Name_Localised": "Steel",
                "Demand": 40,
                "Stock": 0,
                "BuyPrice": 30,
                "SellPrice": 0,
            },
        ],
    )
    response = build_current_carrier_state_response([docked], journal_dir=tmp_path)
    assert response is not None
    state = response.carrier
    assert state.trade_orders_scope == "market_export"

    sells = {o.commodity_name: o for o in state.sell_orders}
    assert sells["gold"].price == 100
    assert sells["gold"].stock == 50
    assert sells["silver"].price == 20

    buys = {o.commodity_name: o for o in state.buy_orders}
    assert buys["steel"].price == 30

    cargo = {c.commodity_name: c.stock for c in state.cargo}
    assert cargo == {"gold": 50, "silver": 8}


def test_state_market_export_fills_missing_orders_only(tmp_path: Path) -> None:
    """An older Market.json only fills commodities the journal lacks."""
    docked = _docked(minute=0)
    trade = _trade(minute=2, commodity="tritium", purchase=10, price=5)
    _write_market(
        tmp_path,
        CARRIER_MARKET_ID,
        "2025-12-15T10:01:00Z",
        [
            {
                "Name": "$tritium_name;",
                "Name_Localised": "Tritium",
                "Demand": 99,
                "Stock": 0,
                "BuyPrice": 0,
                "SellPrice": 7,
            },
            {
                "Name": "$steel_name;",
                "Name_Localised": "Steel",
                "Demand": 40,
                "Stock": 0,
                "BuyPrice": 0,
                "SellPrice": 9,
            },
            {
                "Name": "$gold_name;",
                "Name_Localised": "Gold",
                "Demand": 0,
                "Stock": 30,
                "BuyPrice": 11,
                "SellPrice": 0,
            },
        ],
    )
    response = build_current_carrier_state_response(
        [docked, trade], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.trade_orders_scope == "since_docked"

    buys = {o.commodity_name: o for o in state.buy_orders}
    # Journal-derived tritium wins over the Market.json entry.
    assert buys["tritium"].original_amount == 10
    assert buys["steel"].original_amount == 40

    sells = {o.commodity_name: o for o in state.sell_orders}
    assert sells["gold"].stock == 30

    cargo = {c.commodity_name: c.stock for c in state.cargo}
    assert cargo == {"gold": 30}

    # The older Market.json timestamp must not move the snapshot time.
    assert state.snapshot_time == trade.timestamp


def test_state_hold_follows_the_export_while_orders_keep_journal_values(
    tmp_path: Path,
) -> None:
    """What the carrier holds and what it is offering are separate questions.

    A sell order's Stock is the tonnage attached to that order, so the journal
    line stays authoritative for the order. The hold is the Market.json Stock
    column, which covers every commodity aboard whether or not it is on sale.
    Reading one as the other is what hid cargo that carried no sell order.
    """
    docked = _docked(minute=0)
    trade = _trade(minute=2, commodity="titanium", sale=5, stock=5)
    _write_market(
        tmp_path,
        CARRIER_MARKET_ID,
        "2025-12-15T10:01:00Z",
        [
            {
                "Name": "$titanium_name;",
                "Name_Localised": "Titanium",
                "Demand": 0,
                "Stock": 8,
                "BuyPrice": 4,
                "SellPrice": 0,
            },
            {
                "Name": "$silver_name;",
                "Name_Localised": "Silver",
                "Demand": 0,
                "Stock": 3,
                "BuyPrice": 2,
                "SellPrice": 0,
            },
        ],
    )
    response = build_current_carrier_state_response(
        [docked, trade], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.trade_orders_scope == "since_docked"

    sells = {o.commodity_name: o for o in state.sell_orders}
    # The journal titanium order (stock 5) beats the Market.json entry.
    assert sells["titanium"].stock == 5
    assert sells["silver"].stock == 3

    # The hold is the export: titanium at its held tonnage rather than the
    # tonnage on offer, with silver present despite carrying no journal order.
    cargo = {c.commodity_name: c.stock for c in state.cargo}
    assert cargo == {"titanium": 8, "silver": 3}
    assert state.cargo_snapshot_time is not None


def test_state_space_usage_rounds_floats_and_skips_bad_values(tmp_path: Path) -> None:
    """SpaceUsage floats round to ints while junk values become None."""
    stats = _stats(
        minute=1,
        raw={
            "SpaceUsage": {
                "Cargo": 10.6,
                "TotalCapacity": 25000,
                "FreeSpace": 99.4,
                "Crew": 3370.75,
                "ModulePacks": "not-a-number",
                "CargoSpaceReserved": 12,
            }
        },
    )
    response = build_current_carrier_state_response(
        [_docked(minute=0), stats], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.total_cargo_tonnage == 11
    assert state.total_capacity_tonnage == 25000
    assert state.free_space_tonnage == 99
    usage = state.space_usage
    assert usage is not None
    assert usage.crew == 3371
    assert usage.module_packs is None
    assert usage.cargo_space_reserved == 12


def test_state_space_usage_derivation_error_is_logged_not_raised(
    tmp_path: Path,
) -> None:
    """A malformed SpaceUsage payload degrades gracefully to None metrics."""
    stats = _stats(minute=1, raw={"SpaceUsage": ["completely", "wrong", "shape"]})
    response = build_current_carrier_state_response(
        [_docked(minute=0), stats], journal_dir=tmp_path
    )
    assert response is not None
    state = response.carrier
    assert state.total_cargo_tonnage is None
    assert state.total_capacity_tonnage is None
    assert state.free_space_tonnage is None
    assert state.space_usage is None
