"""Coverage tests for src.services.carrier_service.

These tests exercise the journal interpretation helpers directly with
hand-built pydantic event objects plus real Market.json files written to
temporary directories. No mocking libraries are used; only pytest
monkeypatch is used to redirect journal directory resolution.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

import src.utils.journal as journal_utils
from src.models.carriers import CarrierOrderType, CarrierRole
from src.models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
    DockedEvent,
)
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


# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------


def test_prettify_prefers_localised_label() -> None:
    """The explicit localized name wins over any heuristic cleanup."""
    assert (
        _prettify_commodity_name("fruitandvegetables", "Fancy Label") == "Fancy Label"
    )


def test_prettify_handles_blank_inputs() -> None:
    """Empty or whitespace-only names are returned unchanged."""
    assert _prettify_commodity_name("") == ""
    assert _prettify_commodity_name("   ") == "   "


def test_prettify_degenerate_wrapper_yields_no_words() -> None:
    """A bare journal wrapper collapses to an empty word list."""
    assert _prettify_commodity_name("$;") == ""


def test_prettify_applies_manual_override() -> None:
    """Known unspaced identifiers map through the override table."""
    assert _prettify_commodity_name("fruitandvegetables") == "Fruit and Vegetables"


def test_prettify_title_cases_with_connector_words() -> None:
    """Wrappers are stripped, underscores spaced and connectors lowered."""
    assert _prettify_commodity_name("$Food_And_Water;") == "Food and Water"
    assert _prettify_commodity_name("titanium") == "Titanium"


def test_normalise_commodity_key_variants() -> None:
    """Wrapper, suffix and separator variants converge on one key."""
    assert _normalise_carrier_commodity_key("") == ""
    assert _normalise_carrier_commodity_key("   ") == ""
    assert _normalise_carrier_commodity_key("$Titanium_Name;") == "titanium"
    assert _normalise_carrier_commodity_key("food_name") == "food"
    assert (
        _normalise_carrier_commodity_key("Fruit And Vegetables") == "fruitandvegetables"
    )


# ---------------------------------------------------------------------------
# Event selection helpers
# ---------------------------------------------------------------------------


def test_find_latest_carrier_stats_for_id_no_match_returns_none() -> None:
    """No CarrierStats with the requested id yields None."""
    events = [_stats(carrier_id=1)]
    assert find_latest_carrier_stats_for_id(events, 2) is None


def test_find_stats_for_market_id_matches_raw_market_id() -> None:
    """A raw_data MarketID matching the target is accepted."""
    stats = _stats(carrier_id=555, raw={"MarketID": CARRIER_MARKET_ID})
    assert find_latest_carrier_stats_for_market_id([stats], CARRIER_MARKET_ID) is stats


def test_find_stats_for_market_id_ignores_non_int_raw_market_id() -> None:
    """A non-integer raw MarketID does not count as a match."""
    stats = _stats(carrier_id=555, raw={"MarketID": "not-an-int"})
    assert find_latest_carrier_stats_for_market_id([stats], CARRIER_MARKET_ID) is None


def test_find_stats_for_callsign_blank_target() -> None:
    """Blank callsigns can never match anything."""
    assert find_latest_carrier_stats_for_callsign([_stats()], "") is None
    assert find_latest_carrier_stats_for_callsign([_stats()], "   ") is None


def test_find_stats_for_callsign_matches_case_insensitively() -> None:
    """Callsign matching trims whitespace and ignores case."""
    stats = _stats(callsign="X7J-BQG")
    assert find_latest_carrier_stats_for_callsign([stats], " x7j-bqg ") is stats


def test_find_stats_for_callsign_uses_raw_data_fallback() -> None:
    """When the model field is None the raw Callsign is consulted."""
    stats = _stats(callsign=None, raw={"Callsign": "ABC-123"})
    assert find_latest_carrier_stats_for_callsign([stats], "abc-123") is stats


def test_find_stats_for_callsign_no_match_returns_none() -> None:
    """Non-stats events are skipped; unmatched callsigns yield None."""
    events = [_docked(), _stats(callsign="X7J-BQG")]
    assert find_latest_carrier_stats_for_callsign(events, "ZZZ-999") is None


# ---------------------------------------------------------------------------
# Identity construction
# ---------------------------------------------------------------------------


def test_identity_filters_crew_entries() -> None:
    """Only activated string crew roles other than captain become services."""
    stats = _stats(
        raw={
            "Crew": [
                "not-a-dict",
                {"Activated": False, "CrewRole": "Exploration"},
                {"Activated": True, "CrewRole": 123},
                {"Activated": True, "CrewRole": "Captain"},
                {"Activated": True, "CrewRole": "Bartender"},
            ]
        }
    )
    identity = build_identity_from_journal(_docked(), stats, None)
    assert identity.role is CarrierRole.OWN
    assert identity.services == ["bartender"]


def test_identity_services_from_stats_services_list() -> None:
    """Services on CarrierStats accept strings plus dict entries."""
    stats = _stats(
        raw={
            "Crew": {"unexpected": "shape"},
            "Services": [
                "Refuel",
                {"Name": "Shipyard"},
                {"name": "outfitting"},
                {"neither": True},
                42,
            ],
        }
    )
    identity = build_identity_from_journal(_docked(), stats, None)
    assert identity.services == ["outfitting", "refuel", "shipyard"]


# ---------------------------------------------------------------------------
# Trade order aggregation
# ---------------------------------------------------------------------------


def test_orders_skip_irrelevant_events() -> None:
    """Non-trade events, foreign carriers and blank commodities are ignored."""
    events = [
        _docked(),
        _trade(carrier_id=999, sale=5, stock=5),
        _trade(commodity="", sale=5, stock=5),
    ]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert cargo == []
    assert buys == []
    assert sells == []


def test_orders_cancel_trade_clears_everything() -> None:
    """CancelTrade removes orders plus the cargo row for that commodity."""
    events = [
        _trade(minute=1, commodity="gold", sale=5, stock=5),
        _trade(minute=2, commodity="gold", raw={"CancelTrade": True}),
    ]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert cargo == []
    assert buys == []
    assert sells == []


def test_orders_zero_valued_updates_clear_orders() -> None:
    """Explicit zero SaleOrder or PurchaseOrder values act as cancellations."""
    events = [
        _trade(minute=1, commodity="gold", sale=10, stock=10),
        _trade(minute=2, commodity="gold", raw={"SaleOrder": 0.0}),
        _trade(minute=3, commodity="silver", purchase=4),
        _trade(minute=4, commodity="silver", raw={"PurchaseOrder": 0}),
    ]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert cargo == []
    assert buys == []
    assert sells == []


def test_orders_zero_sale_with_positive_purchase_creates_buy() -> None:
    """Clearing one side while configuring the other still yields an order."""
    events = [
        _trade(
            minute=1,
            commodity="tin",
            purchase=6,
            raw={"SaleOrder": 0, "PurchaseOrder": 6},
        ),
    ]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert sells == []
    assert len(buys) == 1
    assert buys[0].order_type is CarrierOrderType.BUY
    assert buys[0].original_amount == 6


def test_orders_boolean_sale_order_is_not_a_zero_clear() -> None:
    """A boolean SaleOrder in raw data is not treated as an integer zero."""
    events = [
        _trade(minute=1, commodity="copper", sale=3, stock=2, raw={"SaleOrder": True}),
    ]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert len(sells) == 1
    assert sells[0].stock == 2
    assert len(cargo) == 1
    assert cargo[0].stock == 2


def test_orders_event_without_any_order_is_ignored() -> None:
    """Events with neither sale nor purchase amounts produce nothing."""
    events = [_trade(minute=1, commodity="lead")]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert cargo == []
    assert buys == []
    assert sells == []


def test_orders_sell_uses_outstanding_when_stock_missing() -> None:
    """Outstanding acts as the stock proxy when Stock is absent."""
    events = [_trade(minute=1, commodity="iron", sale=9, stock=-1, outstanding=7)]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert len(sells) == 1
    assert sells[0].stock == 7
    assert sells[0].remaining_amount == 7
    assert len(cargo) == 1
    assert cargo[0].stock == 7


def test_orders_buy_order_carries_explicit_stock() -> None:
    """BUY orders surface an explicit non-negative Stock value."""
    events = [_trade(minute=1, commodity="coal", purchase=5, stock=3)]
    cargo, buys, sells = build_orders_for_carrier(events, CARRIER_MARKET_ID)
    assert len(buys) == 1
    assert buys[0].stock == 3
    assert cargo == []


# ---------------------------------------------------------------------------
# High-level composition helpers
# ---------------------------------------------------------------------------


def test_empty_event_lists_short_circuit() -> None:
    """All composition helpers handle an empty event stream."""
    assert build_current_carrier_response([]).docked_at_carrier is False
    assert build_current_carrier_state_response([]) is None
    mine = build_my_carriers_response([])
    assert mine.own_carriers == []
    assert mine.squadron_carriers == []


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


def test_state_market_export_does_not_overwrite_journal_cargo(tmp_path: Path) -> None:
    """Existing journal cargo rows survive the Market.json merge."""
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

    cargo = {c.commodity_name: c.stock for c in state.cargo}
    assert cargo == {"titanium": 5}


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
