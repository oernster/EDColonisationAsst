"""Parsers for the two colonisation journal events.

These are the only journal events this application reads that have changed
shape while it has been in service, so they are the only parsers carrying real
normalisation rather than a field map:

- `ColonisationConstructionDepot` moved its payload from `Commodities`
  (Total/Delivered) to `ResourcesRequired` (RequiredAmount/ProvidedAmount) and
  can omit the station and system fields entirely.
- `ColonisationContribution` moved from flat single-commodity fields to a
  `Contributions` array that carries no cumulative total.

Both normalise to the older, richer shape so nothing downstream has to know
which journal generation wrote the line.

`JournalParser` in src.services.journal_parser dispatches to these; the plain
field-map parsers live in the carrier and commander modules beside this one.
"""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from ..models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

_UNKNOWN_STATION = "Unknown Station"
_UNKNOWN_STATION_TYPE = "Unknown"
_UNKNOWN_SYSTEM = "Unknown System"


def parse_construction_depot(
    data: dict[str, Any],
    timestamp: datetime,
) -> ColonisationConstructionDepotEvent:
    """Parse ColonisationConstructionDepot event.

    Handles both legacy and current journal formats, including:
      - `Commodities` (old) vs `ResourcesRequired` (new) payloads
      - Optional StarSystem / SystemAddress keys
    """
    logger.info(
        "Raw ColonisationConstructionDepotEvent data: %s",
        json.dumps(data),
    )

    # Station name can be in StationName or Name (e.g. carriers)
    station_name = data.get("StationName", "") or data.get("Name", "")
    if not station_name:
        station_name = _UNKNOWN_STATION

    # System information is sometimes missing from the colonisation event.
    # Be defensive and fall back to placeholders instead of raising KeyError.
    system_name = (
        data.get("StarSystem")
        or data.get("SystemName")
        or data.get("System")
        or _UNKNOWN_SYSTEM
    )

    return ColonisationConstructionDepotEvent(
        timestamp=timestamp,
        event=data["event"],
        market_id=data["MarketID"],
        station_name=station_name,
        station_type=data.get("StationType", _UNKNOWN_STATION_TYPE),
        system_name=system_name,
        system_address=data.get("SystemAddress", 0),
        construction_progress=data.get("ConstructionProgress", 0.0),
        construction_complete=data.get("ConstructionComplete", False),
        construction_failed=data.get("ConstructionFailed", False),
        commodities=_normalise_commodities(data),
        raw_data=data,
    )


def _normalise_commodities(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the depot payload in the older Total/Delivered shape.

    Older journals used: "Commodities":
      [{Name, Name_Localised, Total, Delivered, Payment}]
    Newer journals use: "ResourcesRequired":
      [{Name, Name_Localised, RequiredAmount, ProvidedAmount, Payment}]
    """
    if isinstance(data.get("Commodities"), list):
        return data["Commodities"]

    resources = data.get("ResourcesRequired")
    if not isinstance(resources, list):
        return []

    return [
        {
            "Name": r.get("Name", ""),
            "Name_Localised": r.get("Name_Localised", r.get("Name", "")),
            # Map RequiredAmount/ProvidedAmount to the old Total/Delivered shape
            "Total": r.get("RequiredAmount", r.get("Total", 0)),
            "Delivered": r.get("ProvidedAmount", r.get("Delivered", 0)),
            "Payment": r.get("Payment", 0),
        }
        for r in resources
    ]


def parse_contribution(
    data: dict[str, Any],
    timestamp: datetime,
) -> ColonisationContributionEvent:
    """
    Parse ColonisationContribution / ColonisationContribution event.

    Supports both the legacy single-commodity schema:

        {
          "MarketID": 123456,
          "Commodity": "Steel",
          "Commodity_Localised": "Steel",
          "Quantity": 100,
          "TotalQuantity": 600,
          "CreditsReceived": 123400
        }

    and the newer schema that wraps one or more contributions in a
    "Contributions" array:

        {
          "MarketID": 3960951554,
          "Contributions": [
              {
                  "Name": "$Titanium_name;",
                  "Name_Localised": "Titanium",
                  "Amount": 23
              }
          ]
        }

    For the array form we currently materialise a single
    ColonisationContributionEvent for the first contribution item.
    The per-commodity cumulative total is not present in this shape,
    so we treat the provided amount as both quantity and
    total_quantity. Downstream repository logic stores the maximum
    observed provided_amount and will be corrected by subsequent
    depot snapshots if needed.
    """
    logger.info("Parsing ColonisationContributionEvent: %s", data)

    # Legacy schema: flat fields on the event itself.
    if "Commodity" in data:
        return ColonisationContributionEvent(
            timestamp=timestamp,
            event=data["event"],
            market_id=data["MarketID"],
            commodity=data["Commodity"],
            commodity_localised=data.get("Commodity_Localised"),
            quantity=data["Quantity"],
            total_quantity=data.get("TotalQuantity", data["Quantity"]),
            credits_received=data.get("CreditsReceived", 0),
            raw_data=data,
        )

    # Newer schema: list of contribution objects under "Contributions".
    contributions = data.get("Contributions")
    if isinstance(contributions, list) and contributions:
        first = contributions[0]
        name = first.get("Name") or first.get("Commodity") or ""
        # Fallback to raw name if no localised copy is present.
        name_localised = first.get("Name_Localised") or first.get(
            "Commodity_Localised", name
        )
        amount = int(first.get("Amount", 0))

        return ColonisationContributionEvent(
            timestamp=timestamp,
            event=data["event"],
            market_id=data["MarketID"],
            commodity=name,
            commodity_localised=name_localised,
            quantity=amount,
            # No explicit cumulative total is exposed in this schema.
            # Use the observed amount as a best-effort stand-in; the
            # repository layer will merge this with depot snapshots
            # using max() so any later, higher total will win.
            total_quantity=amount,
            credits_received=data.get("CreditsReceived", 0),
            raw_data=data,
        )

    # Fallback: schema we do not understand yet. Log and let the caller
    # treat it as a non-relevant event by raising a ValueError that
    # parse_line will catch and convert into a warning + None.
    logger.warning(
        "Unsupported ColonisationContribution schema, ignoring event: %s",
        data,
    )
    raise ValueError("Unsupported ColonisationContribution schema")


__all__ = ["parse_construction_depot", "parse_contribution"]
