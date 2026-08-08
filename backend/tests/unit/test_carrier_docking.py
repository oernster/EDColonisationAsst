"""Tests for deciding whether the commander is on their carrier RIGHT NOW.

This pins a bug that shipped and was visible in the interface: the panel told
a commander they were docked at their carrier while they were actually docked
at Jameson Memorial in Shinrarta Dezhra, in another system entirely.

The cause was asking the wrong question. "The most recent Docked event at a
carrier" is a fact about the past and stays true forever once it happens.
"Where is the commander now" is settled by the NEWEST event that speaks to it,
whatever that event turns out to be, and the search has to stop there.

Note throughout that this is a question about the COMMANDER. The carrier is
never docked anywhere: it holds station in a star system or it has a jump
booked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.src.models.journal_events import (
    DockedEvent,
    FSDJumpEvent,
    JournalEvent,
    LocationEvent,
    UndockedEvent,
)
from backend.src.services.carrier_events import find_current_carrier_docking

CARRIER_MARKET_ID = 3700569600
CARRIER_CALLSIGN = "X7J-BQG"
START = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _at(minutes: int) -> datetime:
    """A timestamp that many minutes after the start of the scenario."""
    return START + timedelta(minutes=minutes)


def _docked_at_carrier(minutes: int = 0) -> DockedEvent:
    """The commander landing on their own carrier."""
    return DockedEvent(
        timestamp=_at(minutes),
        event="Docked",
        station_name=CARRIER_CALLSIGN,
        station_type="FleetCarrier",
        star_system="Fong Wang",
        system_address=3274669295979,
        market_id=CARRIER_MARKET_ID,
        station_faction={"Name": "FleetCarrier"},
        station_government="$government_Carrier;",
        station_economy="$economy_Carrier;",
        station_economies=[],
    )


def _docked_at_station(minutes: int) -> DockedEvent:
    """The commander landing somewhere that is not a carrier."""
    return DockedEvent(
        timestamp=_at(minutes),
        event="Docked",
        station_name="Jameson Memorial",
        station_type="Orbis",
        star_system="Shinrarta Dezhra",
        system_address=3932277478106,
        market_id=128666762,
        station_faction={"Name": "The Pilots Federation"},
        station_government="$government_Democracy;",
        station_economy="$economy_HighTech;",
        station_economies=[],
    )


def _location(
    minutes: int,
    *,
    docked: bool,
    station_type: str | None,
    station_name: str | None,
    market_id: int | None,
) -> LocationEvent:
    """A Location event, which the game writes on starting a session."""
    return LocationEvent(
        timestamp=_at(minutes),
        event="Location",
        star_system="Shinrarta Dezhra" if station_type == "Orbis" else "Fong Wang",
        system_address=3932277478106,
        docked=docked,
        station_type=station_type,
        station_name=station_name,
        market_id=market_id,
        raw_data={},
    )


def test_standing_on_the_carrier_is_reported() -> None:
    """The plain case, with nothing since to contradict it."""
    docking = find_current_carrier_docking([_docked_at_carrier()])

    assert docking is not None
    assert docking.station_name == CARRIER_CALLSIGN


def test_docking_somewhere_else_ends_it() -> None:
    """The shipped bug, exactly as it appeared on screen.

    Docked at the carrier, flew away, docked at Jameson Memorial. The panel
    went on saying "You are docked here" against the carrier.
    """
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _docked_at_station(60),
    ]

    assert find_current_carrier_docking(events) is None


def test_undocking_ends_it() -> None:
    """Leaving the pad is enough; nowhere else need be visited."""
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        UndockedEvent(
            timestamp=_at(30),
            event="Undocked",
            station_name=CARRIER_CALLSIGN,
            station_type="FleetCarrier",
            market_id=CARRIER_MARKET_ID,
        ),
    ]

    assert find_current_carrier_docking(events) is None


def test_jumping_away_ends_it() -> None:
    """In witchspace to another system is not aboard, whatever came before."""
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        FSDJumpEvent(
            timestamp=_at(45),
            event="FSDJump",
            star_system="Shinrarta Dezhra",
            system_address=3932277478106,
            jump_dist=45.2,
            fuel_used=2.1,
            fuel_level=30.0,
        ),
    ]

    assert find_current_carrier_docking(events) is None


def test_a_session_starting_aboard_the_carrier_is_recognised() -> None:
    """Logging in on your own carrier: Location is the only evidence.

    The Docked event happened in a previous session, so refusing to read a
    Location would report the commander as not aboard when they plainly are.
    """
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _location(
            120,
            docked=True,
            station_type="FleetCarrier",
            station_name=CARRIER_CALLSIGN,
            market_id=CARRIER_MARKET_ID,
        ),
    ]

    docking = find_current_carrier_docking(events)

    assert docking is not None
    assert docking.market_id == CARRIER_MARKET_ID


def test_a_session_starting_aboard_with_no_earlier_docking_still_works() -> None:
    """With no Docked event in the scanned window, the Location carries it."""
    events: list[JournalEvent] = [
        _location(
            5,
            docked=True,
            station_type="FleetCarrier",
            station_name=CARRIER_CALLSIGN,
            market_id=CARRIER_MARKET_ID,
        ),
    ]

    docking = find_current_carrier_docking(events)

    assert docking is not None
    assert docking.station_name == CARRIER_CALLSIGN
    assert docking.station_type == "FleetCarrier"


def test_a_session_starting_at_a_station_is_not_aboard() -> None:
    """Oliver's actual journal state: docked at Jameson Memorial, an Orbis."""
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _location(
            120,
            docked=True,
            station_type="Orbis",
            station_name="Jameson Memorial",
            market_id=128666762,
        ),
    ]

    assert find_current_carrier_docking(events) is None


def test_a_session_starting_in_open_space_is_not_aboard() -> None:
    """Location with Docked false settles it just as firmly."""
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _location(
            120,
            docked=False,
            station_type=None,
            station_name=None,
            market_id=None,
        ),
    ]

    assert find_current_carrier_docking(events) is None


def test_returning_to_the_carrier_after_leaving_is_reported_again() -> None:
    """The state machine has to run both ways, not just latch off."""
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _docked_at_station(60),
        _docked_at_carrier(180),
    ]

    docking = find_current_carrier_docking(events)

    assert docking is not None
    assert docking.station_name == CARRIER_CALLSIGN


def test_an_empty_stream_says_nothing() -> None:
    """No evidence is not evidence of being aboard."""
    assert find_current_carrier_docking([]) is None


def test_a_carrier_location_without_a_market_id_is_still_read() -> None:
    """Older journals omit MarketID, which leaves nothing to match on.

    The Location still says the commander is on a carrier, so it is taken at
    its word rather than discarded for missing a field.
    """
    events: list[JournalEvent] = [
        _docked_at_carrier(),
        _location(
            120,
            docked=True,
            station_type="FleetCarrier",
            station_name=CARRIER_CALLSIGN,
            market_id=None,
        ),
    ]

    docking = find_current_carrier_docking(events)

    assert docking is not None
    assert docking.station_name == CARRIER_CALLSIGN
