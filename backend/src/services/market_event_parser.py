"""Parser for the two market transaction events.

`MarketBuy` and `MarketSell` are flat field maps onto one event type, which is
why they share a parser rather than having one each. They are parsed at all for
a single reason: against the commander's own fleet carrier they are the only
journal lines that move its hold, so they are what carries a Market.json
snapshot forward between refreshes.

Direction is recorded as a flag here rather than left to the event name, so the
hold derivation downstream never has to know journal spellings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models.journal_events import MarketTransactionEvent

# The journal name for the direction that REMOVES stock from a carrier: the
# commander buying means the carrier sold.
_PURCHASE_EVENT = "MarketBuy"


def _tonnes(value: Any) -> int:
    """Tonnage from a journal field, reading anything unusable as nothing moved.

    A boolean is rejected explicitly because bool is a subclass of int, so
    `True` would otherwise arrive as one tonne.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(int(value), 0)


def parse_market_transaction(
    data: dict[str, Any],
    timestamp: datetime,
) -> MarketTransactionEvent:
    """Parse a MarketBuy or MarketSell event.

    Example (from a real journal):

        {
          "timestamp":"2025-12-15T20:33:59Z",
          "event":"MarketBuy",
          "MarketID":3700569600,
          "Type":"titanium",
          "Count":23,
          "BuyPrice":223,
          "TotalCost":5129
        }

    Prices are deliberately not carried. The hold derivation cares only about
    which market moved how much of what, plus the direction.
    """
    event = data["event"]
    return MarketTransactionEvent(
        timestamp=timestamp,
        event=event,
        market_id=data.get("MarketID"),
        commodity=data.get("Type", ""),
        commodity_localised=data.get("Type_Localised"),
        count=_tonnes(data.get("Count")),
        is_purchase=event == _PURCHASE_EVENT,
        raw_data=data,
    )


__all__ = ["parse_market_transaction"]
