"""Journal file parser service"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from ..models.journal_events import (
    JournalEvent,
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    LocationEvent,
    FSDJumpEvent,
    DockedEvent,
    CommanderEvent,
    CarrierLocationEvent,
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class IJournalParser(ABC):
    """Interface for journal file parser"""

    @abstractmethod
    def parse_file(self, file_path: Path) -> List[JournalEvent]:
        """Parse a journal file and return list of events"""
        pass

    @abstractmethod
    def parse_line(self, line: str) -> Optional[JournalEvent]:
        """Parse a single line from journal file"""
        pass


class JournalParser(IJournalParser):
    """
    Parses Elite: Dangerous journal files.
    Follows Single Responsibility Principle - only responsible for parsing.
    """

    # Event types we care about
    RELEVANT_EVENTS = {
        # Colonisation-related events (accept both US and UK spellings)
        "ColonisationConstructionDepot",
        "ColonisationConstructionDepot",
        "ColonisationContribution",
        "ColonisationContribution",
        # Location / movement / docking
        "Location",
        "FSDJump",
        "Docked",
        "Commander",
        # Fleet carrier events (location + basic stats + trade orders)
        "CarrierLocation",
        "CarrierStats",
        "CarrierTradeOrder",
    }

    def parse_file(self, file_path: Path) -> List[JournalEvent]:
        """
        Parse a journal file and return list of relevant events

        Args:
            file_path: Path to journal file

        Returns:
            List of parsed journal events
        """
        events: List[JournalEvent] = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        event = self.parse_line(line)
                        if event:
                            events.append(event)
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse line {line_num} in {file_path.name}: {e}"
                        )
                        continue

            logger.info(f"Parsed {len(events)} relevant events from {file_path.name}")
            return events

        except Exception as e:
            logger.error(f"Failed to parse file {file_path}: {e}")
            return []

    def parse_line(self, line: str) -> Optional[JournalEvent]:
        """
        Parse a single line from journal file

        Args:
            line: JSON line from journal file

        Returns:
            Parsed event or None if not relevant
        """
        try:
            data = json.loads(line)
            event_type = data.get("event")

            if event_type not in self.RELEVANT_EVENTS:
                return None

            # Parse timestamp
            timestamp_str = data.get("timestamp", "")
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            # Route to appropriate parser
            if event_type in {
                "ColonisationConstructionDepot",
                "ColonisationConstructionDepot",
            }:
                return self._parse_construction_depot(data, timestamp)
            elif event_type in {"ColonisationContribution", "ColonisationContribution"}:
                return self._parse_contribution(data, timestamp)
            elif event_type == "Location":
                return self._parse_location(data, timestamp)
            elif event_type == "FSDJump":
                return self._parse_fsd_jump(data, timestamp)
            elif event_type == "Docked":
                return self._parse_docked(data, timestamp)
            elif event_type == "Commander":
                return self._parse_commander(data, timestamp)
            elif event_type == "CarrierLocation":
                return self._parse_carrier_location(data, timestamp)
            elif event_type == "CarrierStats":
                return self._parse_carrier_stats(data, timestamp)
            elif event_type == "CarrierTradeOrder":
                return self._parse_carrier_trade_order(data, timestamp)

            return None

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error parsing line: {e}")
            return None

    def _parse_construction_depot(
        self,
        data: Dict[str, Any],
        timestamp: datetime,
    ) -> ColonisationConstructionDepotEvent:
        """Parse ColonisationConstructionDepot event.

        Handles both legacy and current journal formats, including:
          - US/UK spellings (handled by RELEVANT_EVENTS / dispatch)
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
            station_name = "Unknown Station"

        # System information is sometimes missing from the colonisation event.
        # Be defensive and fall back to placeholders instead of raising KeyError.
        system_name = (
            data.get("StarSystem")
            or data.get("SystemName")
            or data.get("System")
            or "Unknown System"
        )
        system_address = data.get("SystemAddress", 0)

        # Normalise commodities/resources payload.
        # Older journals used: "Commodities": [{Name, Name_Localised, Total, Delivered, Payment}]
        # Newer journals use:  "ResourcesRequired": [{Name, Name_Localised, RequiredAmount, ProvidedAmount, Payment}]
        commodities: list[dict[str, Any]] = []

        if "Commodities" in data and isinstance(data["Commodities"], list):
            commodities = data["Commodities"]
        elif "ResourcesRequired" in data and isinstance(
            data["ResourcesRequired"], list
        ):
            commodities = [
                {
                    "Name": r.get("Name", ""),
                    "Name_Localised": r.get("Name_Localised", r.get("Name", "")),
                    # Map RequiredAmount/ProvidedAmount to the old Total/Delivered shape
                    "Total": r.get("RequiredAmount", r.get("Total", 0)),
                    "Delivered": r.get("ProvidedAmount", r.get("Delivered", 0)),
                    "Payment": r.get("Payment", 0),
                }
                for r in data["ResourcesRequired"]
            ]
        else:
            commodities = []

        return ColonisationConstructionDepotEvent(
            timestamp=timestamp,
            event=data["event"],
            market_id=data["MarketID"],
            station_name=station_name,
            station_type=data.get("StationType", "Unknown"),
            system_name=system_name,
            system_address=system_address,
            construction_progress=data.get("ConstructionProgress", 0.0),
            construction_complete=data.get("ConstructionComplete", False),
            construction_failed=data.get("ConstructionFailed", False),
            commodities=commodities,
            raw_data=data,
        )

    def _parse_contribution(
        self, data: Dict[str, Any], timestamp: datetime
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
                # Use the observed amount as a best-effort stand‑in; the
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

    def _parse_location(
        self, data: Dict[str, Any], timestamp: datetime
    ) -> LocationEvent:
        """Parse Location event"""
        return LocationEvent(
            timestamp=timestamp,
            event=data["event"],
            star_system=data["StarSystem"],
            system_address=data["SystemAddress"],
            star_pos=data.get("StarPos", []),
            station_name=data.get("StationName"),
            station_type=data.get("StationType"),
            market_id=data.get("MarketID"),
            docked=data.get("Docked", False),
            raw_data=data,
        )

    def _parse_fsd_jump(
        self, data: Dict[str, Any], timestamp: datetime
    ) -> FSDJumpEvent:
        """Parse FSDJump event"""
        return FSDJumpEvent(
            timestamp=timestamp,
            event=data["event"],
            star_system=data["StarSystem"],
            system_address=data["SystemAddress"],
            star_pos=data.get("StarPos", []),
            jump_dist=data.get("JumpDist", 0.0),
            fuel_used=data.get("FuelUsed", 0.0),
            fuel_level=data.get("FuelLevel", 0.0),
            raw_data=data,
        )

    def _parse_docked(self, data: Dict[str, Any], timestamp: datetime) -> DockedEvent:
        """Parse Docked event"""
        return DockedEvent(
            timestamp=timestamp,
            event=data["event"],
            station_name=data["StationName"],
            station_type=data["StationType"],
            star_system=data["StarSystem"],
            system_address=data["SystemAddress"],
            market_id=data["MarketID"],
            station_faction=data.get("StationFaction"),
            station_government=data.get("StationGovernment"),
            station_economy=data.get("StationEconomy"),
            station_economies=data.get("StationEconomies", []),
            raw_data=data,
        )

    def _parse_commander(
        self, data: Dict[str, Any], timestamp: datetime
    ) -> CommanderEvent:
        """Parse Commander event"""
        return CommanderEvent(
            timestamp=timestamp,
            event=data["event"],
            name=data["Name"],
            fid=data["FID"],
            raw_data=data,
        )

    def _parse_carrier_location(
        self, data: Dict[str, Any], timestamp: datetime
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

    def _parse_carrier_stats(
        self, data: Dict[str, Any], timestamp: datetime
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
            name=data.get("Name", "Unknown Carrier"),
            callsign=data.get("Callsign"),
            market_id=data.get("MarketID"),
            raw_data=data,
        )

    def _parse_carrier_trade_order(
        self, data: Dict[str, Any], timestamp: datetime
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
        # Sentinel -1 means "not provided in this journal line".
        stock = data.get("Stock", -1)
        outstanding = data.get("Outstanding", -1)

        return CarrierTradeOrderEvent(
            timestamp=timestamp,
            event=data["event"],
            carrier_id=data["CarrierID"],
            commodity=data.get("Commodity", ""),
            commodity_localised=data.get("Commodity_Localised"),
            purchase_order=data.get("PurchaseOrder", 0),
            sale_order=data.get("SaleOrder", 0),
            stock=stock,
            outstanding=outstanding,
            price=data.get("Price", 0),
            raw_data=data,
        )
