"""Journal file parser service.

`JournalParser` reads Elite: Dangerous journal lines and turns the ones this
application cares about into typed events. It owns three things: which events
are relevant, how a file is walked and how a line is dispatched. The per-event
parsing itself lives in three modules beside this one, grouped by how much
work each group does:

- colonisation_event_parser: the two events whose journal format has changed
  in service, so the only parsers carrying real normalisation.
- carrier_event_parser: the three fleet carrier events.
- commander_event_parser: Location, FSDJump, Docked and Commander.

`_EVENT_PARSERS` is the dispatch table. It replaced an if/elif chain that
restated the event names a second time; `RELEVANT_EVENTS` still names them
separately because it is a subclass extension point, so parse_line handles a
subclass widening it past what the table knows.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
import json
from pathlib import Path
from typing import Any, ClassVar

from ..models.journal_events import JournalEvent
from ..utils.logger import get_logger
from .carrier_event_parser import (
    parse_carrier_jump_cancelled,
    parse_carrier_jump_request,
    parse_carrier_location,
    parse_carrier_stats,
    parse_carrier_trade_order,
)
from .colonisation_event_parser import parse_construction_depot, parse_contribution
from .commander_event_parser import (
    parse_commander,
    parse_docked,
    parse_fsd_jump,
    parse_location,
)
from .market_event_parser import parse_market_transaction

logger = get_logger(__name__)

EventParser = Callable[[dict[str, Any], datetime], JournalEvent]

# Journal event name to the function that parses it.
_EVENT_PARSERS: dict[str, EventParser] = {
    "ColonisationConstructionDepot": parse_construction_depot,
    "ColonisationContribution": parse_contribution,
    "Location": parse_location,
    "FSDJump": parse_fsd_jump,
    "Docked": parse_docked,
    "Commander": parse_commander,
    "CarrierLocation": parse_carrier_location,
    "CarrierStats": parse_carrier_stats,
    "CarrierTradeOrder": parse_carrier_trade_order,
    "CarrierJumpRequest": parse_carrier_jump_request,
    "CarrierJumpCancelled": parse_carrier_jump_cancelled,
    "MarketBuy": parse_market_transaction,
    "MarketSell": parse_market_transaction,
}


class IJournalParser(ABC):
    """Interface for journal file parser"""

    @abstractmethod
    def parse_file(self, file_path: Path) -> list[JournalEvent]:
        """Parse a journal file and return list of events"""

    @abstractmethod
    def parse_line(self, line: str) -> JournalEvent | None:
        """Parse a single line from journal file"""


class JournalParser(IJournalParser):
    """
    Parses Elite: Dangerous journal files.
    Follows Single Responsibility Principle - only responsible for parsing.
    """

    # Event types we care about
    RELEVANT_EVENTS: ClassVar[set[str]] = {
        # Colonisation-related events. Frontier is a UK studio and writes the
        # UK spelling, so the z-spelling is deliberately not accepted.
        "ColonisationConstructionDepot",
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
        # Fleet carrier movement. A booked jump and its abandonment; arrival
        # is a CarrierLocation, so it needs no event of its own here.
        "CarrierJumpRequest",
        "CarrierJumpCancelled",
        # Market transactions. Only those against the commander's own carrier
        # are used, purely to carry a Market.json hold snapshot forward.
        "MarketBuy",
        "MarketSell",
    }

    def parse_file(self, file_path: Path) -> list[JournalEvent]:
        """
        Parse a journal file and return list of relevant events

        Args:
            file_path: Path to journal file

        Returns:
            List of parsed journal events
        """
        events: list[JournalEvent] = []

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
                    except Exception as e:  # noqa: BLE001
                        # Deliberately broad, per line. These are lines the
                        # game wrote across years of format changes, so one
                        # this parser cannot read must not abandon the rest
                        # of the file. The loop continues below.
                        logger.warning(
                            f"Failed to parse line {line_num} in {file_path.name}: {e}"
                        )
                        continue

            logger.info(f"Parsed {len(events)} relevant events from {file_path.name}")
            return events

        except Exception as e:  # noqa: BLE001
            # Deliberately broad, per file. A journal being written by the
            # game while it is read, a permissions problem or an encoding
            # surprise all end here. An empty event list means this file
            # contributed nothing, which the caller already handles.
            logger.error(f"Failed to parse file {file_path}: {e}")
            return []

    def parse_line(self, line: str) -> JournalEvent | None:
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
            timestamp = datetime.fromisoformat(data.get("timestamp", ""))

            parser = _EVENT_PARSERS.get(event_type)
            if parser is None:
                # A subclass has widened RELEVANT_EVENTS past what the table
                # handles. Treat it as not relevant rather than raising.
                return None

            return parser(data, timestamp)

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON: {e}")
            return None
        except Exception as e:  # noqa: BLE001
            # Deliberately broad. json.JSONDecodeError is the expected case,
            # but the per-event parsers build pydantic models from whatever
            # the game wrote, so a validation error is just as likely and
            # neither should drop the rest of the file.
            logger.warning(f"Error parsing line: {e}")
            return None


__all__ = ["IJournalParser", "JournalParser"]
