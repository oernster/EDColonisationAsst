"""Coverage tests for src.services.journal_parser.

Closes the remaining statement gaps in JournalParser and the abstract
IJournalParser interface using real JSON journal lines and small
hand-written subclasses. No mock libraries are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from src.models.journal_events import JournalEvent
from src.services.journal_parser import IJournalParser, JournalParser


class PassthroughParser(IJournalParser):
    """Minimal concrete parser delegating to the abstract method bodies.

    Calling the abstract bodies via super() executes their pass statements,
    which is the only way to cover them without instantiating the ABC.
    """

    def parse_file(self, file_path: Path) -> List[JournalEvent]:
        return super().parse_file(file_path)  # type: ignore[safe-super]

    def parse_line(self, line: str) -> Optional[JournalEvent]:
        return super().parse_line(line)  # type: ignore[safe-super]


class ExtendedEventsParser(JournalParser):
    """Parser accepting one extra event type that has no dedicated handler.

    This exercises the defensive trailing return None in parse_line for a
    relevant event that falls through every dispatch branch.
    """

    RELEVANT_EVENTS = JournalParser.RELEVANT_EVENTS | {"Music"}


def test_abstract_parser_bodies_return_none(tmp_path: Path) -> None:
    """The abstract interface bodies are plain pass statements."""
    parser = PassthroughParser()
    assert parser.parse_file(tmp_path / "Journal.none.log") is None
    assert parser.parse_line("{}") is None


def test_parse_file_skips_blank_lines(tmp_path: Path) -> None:
    """Blank lines inside a journal file are skipped without error."""
    parser = JournalParser()
    path = tmp_path / "Journal.blank.log"
    location_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "Location",
            "StarSystem": "Blank System",
            "SystemAddress": 9,
        }
    )
    path.write_text("\n   \n" + location_line + "\n\n", encoding="utf-8")

    events = parser.parse_file(path)

    assert len(events) == 1
    assert events[0].raw_data["StarSystem"] == "Blank System"


def test_parse_line_relevant_event_without_handler_returns_none() -> None:
    """A relevant event with no dispatch branch falls through to None."""
    parser = ExtendedEventsParser()
    line = json.dumps({"timestamp": "2026-01-01T00:00:00Z", "event": "Music"})

    assert parser.parse_line(line) is None


def test_depot_without_station_name_or_commodities() -> None:
    """Depot events missing station and commodity keys get placeholders."""
    parser = JournalParser()
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "ColonisationConstructionDepot",
            "MarketID": 4242,
            "ConstructionProgress": 5.0,
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert event.station_name == "Unknown Station"
    assert event.system_name == "Unknown System"
    assert event.commodities == []


def test_contribution_with_unsupported_schema_returns_none() -> None:
    """Contribution events with no recognised payload shape yield None.

    The parser raises ValueError internally and parse_line converts that
    into a warning plus a None result.
    """
    parser = JournalParser()
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "ColonisationContribution",
            "MarketID": 777,
        }
    )

    assert parser.parse_line(line) is None


def test_contribution_with_empty_contributions_list_returns_none() -> None:
    """An empty Contributions array is treated as an unsupported schema."""
    parser = JournalParser()
    line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "ColonisationContribution",
            "MarketID": 778,
            "Contributions": [],
        }
    )

    assert parser.parse_line(line) is None
