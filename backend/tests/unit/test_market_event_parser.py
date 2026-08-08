"""Tests for the MarketBuy and MarketSell parser.

One parser serves both events, so what matters is that direction is read from
the event name and that a tonnage the game did not write the way we expect
becomes nothing moved rather than a parse failure.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json

from backend.src.models.journal_events import MarketTransactionEvent
from backend.src.services.journal_parser import JournalParser
from backend.src.services.market_event_parser import parse_market_transaction
import pytest

_WHEN = datetime(2026, 6, 21, 17, 51, 30, tzinfo=UTC)


def _line(event: str, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "timestamp": "2026-06-21T17:51:30Z",
        "event": event,
        "MarketID": 3700569600,
        "Type": "tritium",
        "Count": 80,
    }
    data.update(overrides)
    return data


def test_a_purchase_is_flagged_as_one() -> None:
    """Buying takes tonnage out of the carrier, so the direction must survive."""
    event = parse_market_transaction(_line("MarketBuy"), _WHEN)

    assert event.is_purchase is True
    assert event.market_id == 3700569600
    assert event.commodity == "tritium"
    assert event.count == 80
    assert event.timestamp == _WHEN
    assert event.raw_data["event"] == "MarketBuy"


def test_a_sale_is_not_a_purchase() -> None:
    """Selling puts tonnage in; the shape is otherwise the same."""
    event = parse_market_transaction(
        _line("MarketSell", Type_Localised="Fruit and Vegetables"), _WHEN
    )

    assert event.is_purchase is False
    assert event.commodity_localised == "Fruit and Vegetables"


def test_a_missing_localised_name_is_left_unset() -> None:
    """Most journal lines omit it, which is not an error."""
    assert (
        parse_market_transaction(_line("MarketSell"), _WHEN).commodity_localised is None
    )


def test_an_absent_market_and_commodity_do_not_fail_the_parse() -> None:
    """A line the game wrote differently still yields an event."""
    data = {"timestamp": "2026-06-21T17:51:30Z", "event": "MarketSell"}

    event = parse_market_transaction(data, _WHEN)

    assert event.market_id is None
    assert event.commodity == ""
    assert event.count == 0


@pytest.mark.parametrize("event", ["MarketBuy", "MarketSell"])
def test_the_journal_parser_treats_market_lines_as_relevant(event: str) -> None:
    """Registering the parser is not enough on its own.

    `RELEVANT_EVENTS` decides what survives the walk, so a line that is parsed
    but not relevant never reaches the hold derivation. Dropping either name
    would take the whole per-commodity hold out silently; every other test
    here builds events directly and would not notice.
    """
    parsed = JournalParser().parse_line(json.dumps(_line(event)))

    assert isinstance(parsed, MarketTransactionEvent)
    assert parsed.market_id == 3700569600
    assert parsed.is_purchase is (event == "MarketBuy")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (80, 80),
        (80.6, 80),
        (-5, 0),
        (None, 0),
        ("80", 0),
        (True, 0),
    ],
)
def test_tonnage_reads_only_real_numbers(raw: object, expected: int) -> None:
    """Anything unusable counts as nothing moved.

    True is called out because bool subclasses int, so an unguarded conversion
    would smuggle it through as one tonne.
    """
    assert (
        parse_market_transaction(_line("MarketBuy", Count=raw), _WHEN).count == expected
    )
