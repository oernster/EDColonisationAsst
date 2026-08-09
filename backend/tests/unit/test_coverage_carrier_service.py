"""Naming, lookups, identity and order building.

Split out of test_coverage_carrier_service.py; the scaffolding lives in
_test_coverage_carrier_service_support.py.
"""

from src.models.carriers import CarrierOrderType, CarrierRole
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
    _stats,
    _trade,
)


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


def test_empty_event_lists_short_circuit() -> None:
    """All composition helpers handle an empty event stream."""
    assert build_current_carrier_response([]).docked_at_carrier is False
    assert build_current_carrier_state_response([]) is None
    mine = build_my_carriers_response([])
    assert mine.own_carriers == []
    assert mine.squadron_carriers == []
