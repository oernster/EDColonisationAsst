"""Parsers for the three fleet carrier journal events.

`CarrierLocation`, `CarrierStats` and `CarrierTradeOrder` are what the carrier
services in this package reconcile into a single carrier identity, its market
and its orders. Each parser here is a field map onto the typed event; the
reconciliation itself belongs to carrier_identity and carrier_orders.

The one rule that is not obvious is the sentinel in the trade order, which is
recorded at that function rather than here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
)

_UNKNOWN_CARRIER = "Unknown Carrier"

# Sentinel meaning "not provided in this journal line", which downstream logic
# needs to tell apart from an explicit zero.
_NOT_PROVIDED = -1


def parse_carrier_location(
    data: dict[str, Any],
    timestamp: datetime,
) -> CarrierLocationEvent:
    """Parse CarrierLocation event.

    Example (from your journal):

        {
          "timestamp":"2025-12-15T10:50:30Z",
          "event":"CarrierLocation",
          "CarrierType":"FleetCarrier",
          "CarrierID":3700569600,
          "StarSystem":"Lupus Dark Region BQ-Y d66",
          "SystemAddress":2278253693331,
          "BodyID":0
        }
    """
    return CarrierLocationEvent(
        timestamp=timestamp,
        event=data["event"],
        carrier_id=data["CarrierID"],
        star_system=data["StarSystem"],
        system_address=data["SystemAddress"],
        raw_data=data,
    )


def parse_carrier_stats(
    data: dict[str, Any],
    timestamp: datetime,
) -> CarrierStatsEvent:
    """Parse CarrierStats event.

    Example (from your journal):

        {
          "timestamp":"2025-12-15T10:55:20Z",
          "event":"CarrierStats",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "Callsign":"X7J-BQG",
          "Name":"MIDNIGHT ELOQUENCE",
          "DockingAccess":"squadron",
          ...
        }
    """
    return CarrierStatsEvent(
        timestamp=timestamp,
        event=data["event"],
        carrier_id=data["CarrierID"],
        name=data.get("Name", _UNKNOWN_CARRIER),
        callsign=data.get("Callsign"),
        market_id=data.get("MarketID"),
        raw_data=data,
    )


def parse_carrier_trade_order(
    data: dict[str, Any],
    timestamp: datetime,
) -> CarrierTradeOrderEvent:
    """Parse CarrierTradeOrder event.

    Example (from your journal):

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

    Notes
    -----
    - Some clients also emit PurchaseOrder, Stock and Outstanding fields
      for buy orders and remaining quantities.
    - When Stock/Outstanding are omitted we keep sentinel values so that
      downstream logic can distinguish "unknown" from an explicit zero.

    IMPORTANT
    ---------
    Do NOT default Outstanding to the configured SaleOrder/PurchaseOrder.
    Those fields represent the *configured order size*, not current stock
    or remaining amount. Treating them as outstanding/stock causes the UI
    to show phantom cargo commodities that are not actually present.
    """
    return CarrierTradeOrderEvent(
        timestamp=timestamp,
        event=data["event"],
        carrier_id=data["CarrierID"],
        commodity=data.get("Commodity", ""),
        commodity_localised=data.get("Commodity_Localised"),
        purchase_order=data.get("PurchaseOrder", 0),
        sale_order=data.get("SaleOrder", 0),
        stock=data.get("Stock", _NOT_PROVIDED),
        outstanding=data.get("Outstanding", _NOT_PROVIDED),
        price=data.get("Price", 0),
        raw_data=data,
    )


__all__ = [
    "parse_carrier_location",
    "parse_carrier_stats",
    "parse_carrier_trade_order",
]
