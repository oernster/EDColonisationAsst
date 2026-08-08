"""Per-commodity carrier hold, from the market snapshot plus the commander's trades.

Elite Dangerous emits no carrier inventory event. Across 131 distinct event
types there is nothing that lists what a carrier is holding, so the hold has to
be derived. Two sources make that possible and a third checks the result:

- `Market.json` carries a `Stock` column per commodity. It is absolute and it is
  the carrier's real hold rather than only what is listed for sale, which was
  confirmed by its total matching `CarrierStats.SpaceUsage.Cargo` exactly.
  The game rewrites it when the commander docks and opens the carrier's
  commodity market, so it is a snapshot rather than a live reading.
- `MarketBuy` and `MarketSell` against the carrier's own market move that stock
  afterwards: buying takes tonnage out, selling puts tonnage in.
- `CarrierStats.SpaceUsage.Cargo` is an independent total, so the difference
  against the derived sum measures how far the snapshot has drifted.

**The snapshot is the anchor, never a starting guess.** Reconstructing a hold
from transactions alone was measured against 629 `CarrierStats` samples from a
real carrier and matched none of them, drifting by up to 4,880 tonnes and
producing impossible negatives, because cargo also moves by routes the
commander's own journal never records. That is why every derived tonnage is
clamped at zero and why the unaccounted difference is reported rather than
hidden: a hold that has moved since the snapshot says so instead of quietly
reading as current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..models.carriers import CarrierCargoItem
from ..models.journal_events import MarketTransactionEvent
from .market_export_service import MarketExportSnapshot

_FLEET_CARRIER = "FleetCarrier"


@dataclass(frozen=True, slots=True)
class CarrierHold:
    """The hold as far as local data can establish it."""

    items: list[CarrierCargoItem]
    snapshot_time: datetime | None = None
    unaccounted_tonnage: int | None = None


def _usable_snapshot(
    snapshot: MarketExportSnapshot | None,
    carrier_market_id: int | None,
) -> MarketExportSnapshot | None:
    """The export on disk when it is this carrier's own market, otherwise None.

    Returns the snapshot rather than a flag so the caller is narrowed by the
    check itself and needs no second assertion that it is set.
    """
    if (
        snapshot is not None
        and snapshot.station_type == _FLEET_CARRIER
        and snapshot.market_id is not None
        and carrier_market_id is not None
        and snapshot.market_id == carrier_market_id
    ):
        return snapshot
    return None


def _movements(
    transactions: list[MarketTransactionEvent],
    carrier_market_id: int | None,
    since: datetime | None,
) -> dict[str, int]:
    """Net tonnage per commodity from the commander's own trades at the carrier.

    Transactions at or before the snapshot are already reflected in it, so only
    later ones are applied. Without a snapshot time nothing can be positioned
    relative to the anchor, so nothing is applied.
    """
    net: dict[str, int] = {}
    if since is None:
        return net

    for txn in transactions:
        if txn.market_id != carrier_market_id or txn.timestamp <= since:
            continue
        key = (txn.commodity or "").strip().lower()
        if not key:
            continue
        net[key] = net.get(key, 0) + (-txn.count if txn.is_purchase else txn.count)
    return net


def derive_carrier_hold(
    *,
    snapshot: MarketExportSnapshot | None,
    transactions: list[MarketTransactionEvent],
    carrier_market_id: int | None,
    reported_tonnage: int | None,
    fallback_items: list[CarrierCargoItem],
) -> CarrierHold:
    """Build the per-commodity hold, anchored on the market export.

    Falls back to whatever the trade orders yielded when there is no usable
    export, which is the behaviour that predates this derivation: without an
    anchor the transactions cannot be positioned and are worth nothing.
    """
    usable = _usable_snapshot(snapshot, carrier_market_id)
    if usable is None:
        return CarrierHold(items=list(fallback_items))

    tonnages: dict[str, int] = {}
    display: dict[str, str] = {}

    for item in usable.items:
        key = item.commodity_key
        tonnages[key] = item.stock
        display[key] = item.name_localised or item.commodity_key

    for key, delta in _movements(
        transactions, carrier_market_id, usable.timestamp
    ).items():
        tonnages[key] = tonnages.get(key, 0) + delta
        display.setdefault(key, key)

    items = [
        CarrierCargoItem(
            commodity_name=key,
            commodity_name_localised=display[key],
            stock=tonnage,
            reserved=0,
            capacity=None,
        )
        # Clamped at zero: a negative tonnage means movement the journal did not
        # record, not a carrier holding less than nothing.
        for key, tonnage in sorted(
            tonnages.items(), key=lambda pair: (-pair[1], pair[0])
        )
        if tonnage > 0
    ]

    unaccounted = None
    if reported_tonnage is not None:
        unaccounted = reported_tonnage - sum(item.stock for item in items)

    return CarrierHold(
        items=items,
        snapshot_time=usable.timestamp,
        unaccounted_tonnage=unaccounted,
    )


__all__ = ["CarrierHold", "derive_carrier_hold"]
