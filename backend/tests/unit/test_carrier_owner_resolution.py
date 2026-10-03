"""Which carrier "your carrier" means when the commander is not aboard one.

Not aboard, the state view used the newest Docked at ANY fleet carrier. One
visit to somebody else's carrier and the panel showed theirs, role OTHER, with
no capacity. The commander's own carrier is the one their CarrierStats names;
the last carrier docked at is the answer only when no CarrierStats exists.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from src.models.journal_events import JournalEvent
from src.services.carrier_service import build_current_carrier_state_response
from src.services.journal_parser import JournalParser

_OWN_ID = 3700000001
_OWN_CALLSIGN = "OWN-001"
_STRANGER_ID = 3700000099
_STRANGER_CALLSIGN = "STR-099"
_NOW = datetime(2025, 1, 1, 12, tzinfo=UTC)


def _events(*raw: dict) -> list[JournalEvent]:
    parser = JournalParser()
    parsed = [parser.parse_line(json.dumps(entry)) for entry in raw]
    assert all(event is not None for event in parsed)
    return parsed


def _docked(stamp: str, market_id: int, callsign: str) -> dict:
    return {
        "timestamp": stamp,
        "event": "Docked",
        "StationName": callsign,
        "StationType": "FleetCarrier",
        "StarSystem": "Sol",
        "SystemAddress": 1,
        "MarketID": market_id,
        "StationFaction": {"Name": "FleetCarrier"},
        "StationGovernment": "$government_Carrier;",
        "StationEconomy": "$economy_Carrier;",
        "StationEconomies": [],
    }


def _undocked(stamp: str) -> dict:
    return {"timestamp": stamp, "event": "Undocked", "StationName": "x"}


_OWN_STATS = {
    "timestamp": "2025-01-01T09:00:00Z",
    "event": "CarrierStats",
    "CarrierID": _OWN_ID,
    "Callsign": _OWN_CALLSIGN,
    "Name": "MY OWN CARRIER",
}


def _resolved_carrier_id(events: list[JournalEvent]) -> int | None:
    response = build_current_carrier_state_response(events, now=_NOW)
    if response is None or response.carrier is None:
        return None
    return response.carrier.identity.carrier_id


def test_a_visit_to_a_stranger_does_not_replace_the_own_carrier() -> None:
    events = _events(
        _OWN_STATS,
        _docked("2025-01-01T09:10:00Z", _OWN_ID, _OWN_CALLSIGN),
        _undocked("2025-01-01T09:20:00Z"),
        _docked("2025-01-01T10:00:00Z", _STRANGER_ID, _STRANGER_CALLSIGN),
        _undocked("2025-01-01T10:10:00Z"),
    )

    assert _resolved_carrier_id(events) == _OWN_ID


def test_the_own_carrier_is_matched_by_callsign_when_ids_differ() -> None:
    events = _events(
        _OWN_STATS,
        _docked("2025-01-01T09:10:00Z", _OWN_ID + 1, _OWN_CALLSIGN.lower()),
        _undocked("2025-01-01T09:20:00Z"),
        _docked("2025-01-01T10:00:00Z", _STRANGER_ID, _STRANGER_CALLSIGN),
        _undocked("2025-01-01T10:10:00Z"),
    )

    assert _resolved_carrier_id(events) == _OWN_ID


def test_an_own_carrier_never_docked_at_shows_no_stranger() -> None:
    events = _events(
        _OWN_STATS,
        _docked("2025-01-01T10:00:00Z", _STRANGER_ID, _STRANGER_CALLSIGN),
        _undocked("2025-01-01T10:10:00Z"),
    )

    assert _resolved_carrier_id(events) is None


def test_with_no_carrier_in_the_journal_there_is_no_answer() -> None:
    events = _events(_undocked("2025-01-01T10:10:00Z"))

    assert _resolved_carrier_id(events) is None


def test_without_carrier_stats_the_last_carrier_docked_at_is_the_answer() -> None:
    events = _events(
        _docked("2025-01-01T10:00:00Z", _STRANGER_ID, _STRANGER_CALLSIGN),
        _undocked("2025-01-01T10:10:00Z"),
    )

    assert _resolved_carrier_id(events) == _STRANGER_ID
