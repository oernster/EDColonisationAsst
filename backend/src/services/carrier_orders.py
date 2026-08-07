"""Cargo, buy and sell orders derived from CarrierTradeOrder events.

The most intricate rule set in the carrier code: trade orders arrive as
deltas as often as snapshots, so building a current view means deciding
which observations still hold rather than replaying them all.
"""

from __future__ import annotations

from ..models.carriers import (
    CarrierCargoItem,
    CarrierOrder,
    CarrierOrderType,
)
from ..models.journal_events import (
    CarrierTradeOrderEvent,
    JournalEvent,
)
from ..utils.logger import get_logger
from .carrier_naming import (
    _normalise_carrier_commodity_key,
    _prettify_commodity_name,
)

logger = get_logger(__name__)


def build_orders_for_carrier(
    events: list[JournalEvent],
    carrier_id: int,
) -> tuple[list[CarrierCargoItem], list[CarrierOrder], list[CarrierOrder]]:
    """Build cargo, buy and sell orders for one carrier.

    Built from that carrier's CarrierTradeOrder events.

    The journal events look like (examples from your logs):

        {
          "timestamp":"2025-12-15T11:17:37Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"titanium",
          "SaleOrder":23,
          "Price":4446
        }

        {
          "timestamp":"2025-12-15T11:20:15Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"tritium",
          "PurchaseOrder":1,
          "Price":51294
        }

        {
          "timestamp":"2025-12-15T11:20:20Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"tritium",
          "CancelTrade":true
        }

    We infer order_type via the presence of PurchaseOrder vs SaleOrder.

    Semantics
    ---------
    - Orders are modelled as the *latest known state per commodity*, not as
      a historical list. Subsequent CarrierTradeOrder events for the same
      commodity overwrite earlier ones.
    - CancelTrade events remove any existing buy/sell order and associated
      cargo entry for that commodity.
    - For SELL orders we only treat Stock/Outstanding as indicative of current
      *market stock* when present. The configured SaleOrder size is not a cargo
      snapshot and must not be used as a stock proxy.
    """
    # Latest buy/sell order per commodity.
    buy_orders_by_commodity: dict[str, CarrierOrder] = {}
    sell_orders_by_commodity: dict[str, CarrierOrder] = {}

    # Aggregate cargo stock per commodity based on SELL orders. This does not
    # represent the full physical cargo hold but it provides a useful view of
    # "stock assigned to the market" for each commodity.
    cargo_by_commodity: dict[str, dict[str, object]] = {}

    for event in events:
        if not isinstance(event, CarrierTradeOrderEvent):
            continue
        if event.carrier_id != carrier_id:
            continue

        commodity_key = _normalise_carrier_commodity_key(event.commodity or "")
        if not commodity_key:
            # Ignore events with no usable commodity identifier.
            continue

        raw = event.raw_data or {}

        # Explicit cancel: clear any existing orders and cargo entry.
        if raw.get("CancelTrade"):
            buy_orders_by_commodity.pop(commodity_key, None)
            sell_orders_by_commodity.pop(commodity_key, None)
            cargo_by_commodity.pop(commodity_key, None)
            continue

        # Some journal variants clear an order by emitting a new CarrierTradeOrder
        # line with SaleOrder/PurchaseOrder set to 0 (rather than CancelTrade).
        # Treat explicit zero values as a cancellation for that order type.
        sale_present = "SaleOrder" in raw
        purchase_present = "PurchaseOrder" in raw
        sale_value = raw.get("SaleOrder")
        purchase_value = raw.get("PurchaseOrder")

        def _as_int(val: object) -> int | None:
            if isinstance(val, bool):
                return None
            if isinstance(val, int):
                return val
            if isinstance(val, float):
                return round(val)
            return None

        sale_int = _as_int(sale_value)
        purchase_int = _as_int(purchase_value)

        cleared_any = False
        if sale_present and sale_int == 0:
            sell_orders_by_commodity.pop(commodity_key, None)
            cargo_by_commodity.pop(commodity_key, None)
            cleared_any = True
        if purchase_present and purchase_int == 0:
            buy_orders_by_commodity.pop(commodity_key, None)
            cleared_any = True

        # If this event only exists to clear orders, stop processing.
        if cleared_any and not ((sale_int or 0) > 0 or (purchase_int or 0) > 0):
            continue

        # Determine order type
        order_type: CarrierOrderType | None = None
        if event.sale_order > 0:
            order_type = CarrierOrderType.SELL
        elif event.purchase_order > 0:
            order_type = CarrierOrderType.BUY
        else:
            # Neither sale nor purchase order (and no CancelTrade): ignore.
            continue

        # Original amount is the configured order size.
        original_amount = (
            event.sale_order
            if order_type == CarrierOrderType.SELL
            else event.purchase_order
        )

        # Remaining amount (Outstanding) is optional in journal output.
        # When not provided we keep it as the configured size for display
        # purposes; we do NOT use it to infer cargo stock.
        remaining_amount = (
            event.outstanding if event.outstanding >= 0 else original_amount
        )

        # Derive a best-effort view of *current market stock* for SELL orders.
        # Priority:
        #   1. Explicit Stock when present.
        #   2. Outstanding when present.
        # We intentionally do NOT fall back to SaleOrder (configured size).
        derived_stock: int | None = None
        if order_type == CarrierOrderType.SELL:
            if event.stock >= 0:
                derived_stock = event.stock
            elif event.outstanding >= 0:
                derived_stock = event.outstanding

        # If we could not infer a sensible stock value, keep None so that the
        # API surface can distinguish "unknown" from an explicit zero.
        order_stock: int | None
        if order_type == CarrierOrderType.SELL and derived_stock is not None:
            order_stock = max(derived_stock, 0)
        elif event.stock >= 0:
            order_stock = max(event.stock, 0)
        else:
            order_stock = None

        # Choose a human‑friendly display name, preferring the journal's
        # localized label when available and falling back to a prettified
        # internal name (e.g. "fruitandvegetables" → "Fruit and Vegetables").
        display_name = _prettify_commodity_name(
            raw_name=event.commodity,
            localised=event.commodity_localised,
        )

        order = CarrierOrder(
            order_type=order_type,
            commodity_name=event.commodity,
            commodity_name_localised=display_name,
            price=event.price,
            original_amount=max(original_amount, 0),
            remaining_amount=max(remaining_amount, 0),
            stock=order_stock,
        )

        if order_type == CarrierOrderType.SELL:
            # Latest SELL order wins for this commodity.
            sell_orders_by_commodity[commodity_key] = order
            # A carrier cannot practically have both BUY and SELL orders for the
            # same commodity; discard any stale BUY for this key.
            buy_orders_by_commodity.pop(commodity_key, None)

            # Reflect SELL orders into a simple cargo/market-stock view.
            # Only include commodities when we have a stock value (Stock or
            # Outstanding) from the journal.
            if derived_stock is None:
                # Unknown stock: do not show a per-commodity row.
                cargo_by_commodity.pop(commodity_key, None)
            else:
                stock_qty = max(int(derived_stock), 0)
                if stock_qty == 0:
                    cargo_by_commodity.pop(commodity_key, None)
                else:
                    display_name = _prettify_commodity_name(
                        raw_name=event.commodity,
                        localised=event.commodity_localised,
                    )
                    cargo_by_commodity[commodity_key] = {
                        "commodity_name": event.commodity,
                        "commodity_name_localised": display_name,
                        "stock": stock_qty,
                        "reserved": 0,
                        "capacity": None,
                    }
        else:
            # Latest BUY order wins for this commodity.
            buy_orders_by_commodity[commodity_key] = order
            # Likewise, a BUY order replaces any previous SELL configuration for
            # the same commodity.
            sell_orders_by_commodity.pop(commodity_key, None)

    # Convert cargo map into CarrierCargoItem list
    cargo_items: list[CarrierCargoItem] = []
    for data in cargo_by_commodity.values():
        cargo_items.append(
            CarrierCargoItem(
                commodity_name=data["commodity_name"],  # type: ignore[arg-type]
                commodity_name_localised=data[
                    "commodity_name_localised"
                ],  # type: ignore[arg-type]
                stock=int(data["stock"]),  # type: ignore[arg-type]
                reserved=int(data["reserved"]),  # type: ignore[arg-type]
                capacity=data["capacity"],  # type: ignore[arg-type]
            )
        )

    buy_orders = list(buy_orders_by_commodity.values())
    sell_orders = list(sell_orders_by_commodity.values())

    return cargo_items, buy_orders, sell_orders
