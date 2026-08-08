"""Tests for the per-commodity carrier hold derivation.

The rules being pinned here come from measurement against a real carrier's
journals rather than from the schema: the export is the hold and not merely
what is on sale, transactions only extend it forward from the anchor and a
tonnage can never go negative however the arithmetic lands.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.src.models.carriers import CarrierCargoItem
from backend.src.models.journal_events import MarketTransactionEvent
from backend.src.services.carrier_hold import derive_carrier_hold
from backend.src.services.market_export_service import (
    MarketExportItem,
    MarketExportSnapshot,
)

CARRIER_MARKET_ID = 3700569600
ANCHOR = datetime(2026, 6, 21, 17, 51, 30, tzinfo=UTC)


def _item(key: str, stock: int, localised: str | None = None) -> MarketExportItem:
    return MarketExportItem(
        commodity_key=key,
        name_token=f"${key}_name;",
        name_localised=localised,
        demand=0,
        stock=stock,
        buy_price=0,
        sell_price=0,
    )


def _snapshot(
    *items: MarketExportItem,
    market_id: int | None = CARRIER_MARKET_ID,
    station_type: str | None = "FleetCarrier",
    timestamp: datetime | None = ANCHOR,
) -> MarketExportSnapshot:
    return MarketExportSnapshot(
        timestamp=timestamp,
        station_type=station_type,
        station_name="X7J-BQG",
        star_system="Sol",
        market_id=market_id,
        items=tuple(items),
    )


def _txn(
    commodity: str,
    count: int,
    *,
    purchase: bool,
    minutes: int = 5,
    market_id: int | None = CARRIER_MARKET_ID,
) -> MarketTransactionEvent:
    return MarketTransactionEvent(
        timestamp=ANCHOR + timedelta(minutes=minutes),
        event="MarketBuy" if purchase else "MarketSell",
        market_id=market_id,
        commodity=commodity,
        count=count,
        is_purchase=purchase,
    )


def _derive(snapshot, transactions=(), reported=None, fallback=()):
    return derive_carrier_hold(
        snapshot=snapshot,
        transactions=list(transactions),
        carrier_market_id=CARRIER_MARKET_ID,
        reported_tonnage=reported,
        fallback_items=list(fallback),
    )


def _tonnages(hold) -> dict[str, int]:
    return {item.commodity_name: item.stock for item in hold.items}


def test_the_export_is_the_hold() -> None:
    """Every commodity aboard shows, whether or not it carries a sell order."""
    hold = _derive(_snapshot(_item("tritium", 6354), _item("water", 120)))

    assert _tonnages(hold) == {"tritium": 6354, "water": 120}
    assert hold.snapshot_time == ANCHOR


def test_commodities_with_no_stock_are_left_out() -> None:
    """A carrier market lists dozens of commodities it holds none of."""
    hold = _derive(_snapshot(_item("tritium", 6354), _item("gold", 0)))

    assert _tonnages(hold) == {"tritium": 6354}


def test_the_heaviest_holding_comes_first() -> None:
    """Ordering is the diagnostic: what fills the hold should lead."""
    hold = _derive(
        _snapshot(_item("water", 120), _item("tritium", 6354), _item("gold", 900))
    )

    assert [item.commodity_name for item in hold.items] == [
        "tritium",
        "gold",
        "water",
    ]


def test_equal_tonnages_are_ordered_by_name() -> None:
    """Ties must not depend on export ordering; otherwise the list reshuffles."""
    hold = _derive(_snapshot(_item("water", 50), _item("gold", 50)))

    assert [item.commodity_name for item in hold.items] == ["gold", "water"]


def test_a_purchase_after_the_anchor_removes_tonnage() -> None:
    """Buying from the carrier is stock leaving it.

    This is the case measured against the real journals: 6354 in the export,
    one 80t purchase, with CarrierStats independently reporting 6274.
    """
    hold = _derive(
        _snapshot(_item("tritium", 6354)),
        [_txn("tritium", 80, purchase=True)],
        reported=6274,
    )

    assert _tonnages(hold) == {"tritium": 6274}
    assert hold.unaccounted_tonnage == 0


def test_a_sale_after_the_anchor_adds_tonnage() -> None:
    """Selling to the carrier is stock arriving, including a new commodity."""
    hold = _derive(
        _snapshot(_item("tritium", 100)),
        [_txn("tritium", 40, purchase=False), _txn("silver", 25, purchase=False)],
    )

    assert _tonnages(hold) == {"tritium": 140, "silver": 25}


def test_transactions_at_or_before_the_anchor_are_already_in_it() -> None:
    """Applying them again would double-count what the export already shows."""
    hold = _derive(
        _snapshot(_item("tritium", 100)),
        [
            _txn("tritium", 30, purchase=False, minutes=-5),
            _txn("tritium", 7, purchase=False, minutes=0),
        ],
    )

    assert _tonnages(hold) == {"tritium": 100}


def test_transactions_at_other_markets_are_ignored() -> None:
    """Trading at a station says nothing about what the carrier holds."""
    hold = _derive(
        _snapshot(_item("tritium", 100)),
        [_txn("tritium", 60, purchase=True, market_id=999)],
    )

    assert _tonnages(hold) == {"tritium": 100}


def test_a_transaction_with_no_commodity_is_skipped() -> None:
    """A blank name cannot be attributed to a row."""
    hold = _derive(
        _snapshot(_item("tritium", 100)),
        [_txn("   ", 60, purchase=False)],
    )

    assert _tonnages(hold) == {"tritium": 100}


def test_tonnage_never_goes_negative() -> None:
    """Cargo also moves by routes the journal never records.

    Reconstructing from transactions alone produced impossible negatives on
    real data, which is why a row that lands below zero is dropped rather than
    shown.
    """
    hold = _derive(
        _snapshot(_item("copper", 10)),
        [_txn("copper", 1242, purchase=True)],
    )

    assert _tonnages(hold) == {}


def test_an_export_with_no_timestamp_applies_no_transactions() -> None:
    """Without an anchor time nothing can be placed before or after it."""
    hold = _derive(
        _snapshot(_item("tritium", 100), timestamp=None),
        [_txn("tritium", 40, purchase=False)],
    )

    assert _tonnages(hold) == {"tritium": 100}
    assert hold.snapshot_time is None


def test_the_gap_against_the_carrier_total_is_reported() -> None:
    """A hold that has moved since the export must say so rather than read current."""
    hold = _derive(_snapshot(_item("tritium", 6354)), reported=6800)

    assert hold.unaccounted_tonnage == 446


def test_no_carrier_total_means_no_gap_to_report() -> None:
    """Without CarrierStats there is nothing to check the export against."""
    assert _derive(_snapshot(_item("tritium", 10))).unaccounted_tonnage is None


def test_another_station_export_falls_back_to_the_trade_orders() -> None:
    """Market.json is whatever market was opened last, often not the carrier."""
    fallback = [
        CarrierCargoItem(
            commodity_name="gold",
            commodity_name_localised="Gold",
            stock=30,
            reserved=0,
            capacity=None,
        )
    ]
    hold = _derive(
        _snapshot(_item("tritium", 6354), market_id=12345), fallback=fallback
    )

    assert _tonnages(hold) == {"gold": 30}
    assert hold.snapshot_time is None


def test_a_non_carrier_export_falls_back() -> None:
    """A starport market says nothing about a carrier hold."""
    hold = _derive(_snapshot(_item("tritium", 1), station_type="Coriolis"))

    assert hold.items == []


def test_an_export_with_no_market_id_falls_back() -> None:
    """Without an id it cannot be attributed to this carrier."""
    hold = _derive(_snapshot(_item("tritium", 1), market_id=None))

    assert hold.items == []


def test_no_export_at_all_falls_back() -> None:
    """The commander may never have opened the carrier's market."""
    assert _derive(None).items == []


def test_the_localised_name_is_preferred_for_display() -> None:
    """The raw key is a fallback, not the label."""
    hold = _derive(_snapshot(_item("fruitandvegetables", 9, "Fruit and Vegetables")))

    assert hold.items[0].commodity_name_localised == "Fruit and Vegetables"


def test_a_commodity_known_only_from_a_sale_uses_its_key() -> None:
    """Nothing in the export names it, so the key is all there is."""
    hold = _derive(_snapshot(), [_txn("silver", 25, purchase=False)])

    assert hold.items[0].commodity_name_localised == "silver"
