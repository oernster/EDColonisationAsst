"""Colonisation, location and movement events.

Split out of test_journal_parser.py when that file passed the module cap.
These tests need no shared scaffolding beyond their own imports.
"""

import json

from src.models.journal_events import (
    CarrierJumpCancelledEvent,
    CarrierJumpRequestEvent,
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    CommanderEvent,
    DockedEvent,
    FSDJumpEvent,
    LocationEvent,
)


def test_parse_construction_depot_event(parser, sample_journal_line):
    """Test parsing ColonisationConstructionDepot event"""
    event = parser.parse_line(sample_journal_line)

    assert event is not None
    assert isinstance(event, ColonisationConstructionDepotEvent)
    assert event.market_id == 123456
    assert event.station_name == "Test Station"
    assert event.system_name == "Test System"
    assert event.construction_progress == 50.0
    assert len(event.commodities) == 1


def test_parse_contribution_event(parser):
    """Test parsing ColonisationContribution event"""
    line = (
        '{"timestamp":"2025-11-29T01:00:00Z","event":"ColonisationContribution",'
        '"MarketID":123456,"Commodity":"Steel","Commodity_Localised":"Steel",'
        '"Quantity":100,"TotalQuantity":600,"CreditsReceived":123400}'
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, ColonisationContributionEvent)
    assert event.market_id == 123456
    assert event.commodity == "Steel"
    assert event.quantity == 100
    assert event.total_quantity == 600
    assert event.credits_received == 123400


def test_parse_contribution_event_contributions_array(parser):
    """Test parsing ColonisationContribution with Contributions array schema."""
    line = json.dumps(
        {
            "timestamp": "2025-12-15T20:37:20Z",
            "event": "ColonisationContribution",
            "MarketID": 3960951554,
            "Contributions": [
                {
                    "Name": "$Titanium_name;",
                    "Name_Localised": "Titanium",
                    "Amount": 23,
                }
            ],
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, ColonisationContributionEvent)
    assert event.market_id == 3960951554
    assert event.commodity == "$Titanium_name;"
    assert event.commodity_localised == "Titanium"
    assert event.quantity == 23
    assert event.total_quantity == 23


def test_parse_location_event(parser):
    """Test parsing Location event"""
    line = json.dumps(
        {
            "timestamp": "2025-11-29T01:00:00Z",
            "event": "Location",
            "StarSystem": "Test System",
            "SystemAddress": 987654,
            "StarPos": [1.0, 2.0, 3.0],
            "StationName": "Test Station",
            "StationType": "Coriolis",
            "MarketID": 123456,
            "Docked": True,
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, LocationEvent)
    assert event.star_system == "Test System"
    assert event.system_address == 987654
    assert event.docked is True
    assert event.station_name == "Test Station"
    assert event.station_type == "Coriolis"
    assert event.market_id == 123456


def test_parse_fsd_jump_event(parser):
    """Test parsing FSDJump event"""
    line = json.dumps(
        {
            "timestamp": "2025-11-29T01:05:00Z",
            "event": "FSDJump",
            "StarSystem": "Next System",
            "SystemAddress": 111222,
            "StarPos": [10.0, 20.0, 30.0],
            "JumpDist": 12.5,
            "FuelUsed": 3.2,
            "FuelLevel": 10.0,
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, FSDJumpEvent)
    assert event.star_system == "Next System"
    assert event.jump_dist == 12.5
    assert event.fuel_used == 3.2
    assert event.fuel_level == 10.0


def test_parse_docked_event(parser):
    """Test parsing Docked event"""
    line = json.dumps(
        {
            "timestamp": "2025-11-29T01:10:00Z",
            "event": "Docked",
            "StationName": "Dock Station",
            "StationType": "Outpost",
            "StarSystem": "Dock System",
            "SystemAddress": 333444,
            "MarketID": 777,
            "StationFaction": {"Name": "Faction"},
            "StationGovernment": "Democracy",
            "StationEconomy": "Industrial",
            "StationEconomies": [],
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, DockedEvent)
    assert event.station_name == "Dock Station"
    assert event.station_type == "Outpost"
    assert event.star_system == "Dock System"
    assert event.system_address == 333444
    assert event.market_id == 777
    assert event.station_government == "Democracy"


def test_parse_commander_event(parser):
    """Test parsing Commander event"""
    line = json.dumps(
        {
            "timestamp": "2025-11-29T01:15:00Z",
            "event": "Commander",
            "Name": "CMDR Test",
            "FID": "ABC123",
        }
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, CommanderEvent)
    assert event.name == "CMDR Test"
    assert event.fid == "ABC123"


def test_parse_carrier_jump_request_event(parser):
    """A booked carrier jump, verbatim from the journal."""
    line = (
        '{ "timestamp":"2026-06-16T19:53:56Z", "event":"CarrierJumpRequest", '
        '"CarrierType":"FleetCarrier", "CarrierID":3700569600, '
        '"SystemName":"Fong Wang", "Body":"Fong Wang 4", '
        '"SystemAddress":3274669295979, "BodyID":14, '
        '"DepartureTime":"2026-06-16T20:09:10Z" }'
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, CarrierJumpRequestEvent)
    assert event.carrier_id == 3700569600
    assert event.system_name == "Fong Wang"
    assert event.system_address == 3274669295979
    assert event.body == "Fong Wang 4"
    assert event.departure_time is not None
    assert event.departure_time.hour == 20
    assert event.departure_time.minute == 9


def test_parse_carrier_jump_request_without_a_departure_time(parser):
    """Older journals omit DepartureTime and Body; the jump still parses."""
    line = (
        '{"timestamp":"2026-06-16T19:53:56Z","event":"CarrierJumpRequest",'
        '"CarrierID":3700569600,"SystemName":"Fong Wang",'
        '"SystemAddress":3274669295979}'
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, CarrierJumpRequestEvent)
    assert event.departure_time is None
    assert event.body is None


def test_parse_carrier_jump_cancelled_event(parser):
    """An abandoned jump carries nothing but the carrier it belongs to."""
    line = (
        '{ "timestamp":"2026-04-18T16:29:19Z", "event":"CarrierJumpCancelled", '
        '"CarrierType":"FleetCarrier", "CarrierID":3700569600 }'
    )

    event = parser.parse_line(line)

    assert event is not None
    assert isinstance(event, CarrierJumpCancelledEvent)
    assert event.carrier_id == 3700569600


def test_parse_irrelevant_event(parser):
    """Test that irrelevant events are ignored"""
    line = '{"timestamp":"2025-11-29T01:00:00Z","event":"Scan","BodyName":"Test Body"}'

    event = parser.parse_line(line)

    assert event is None


def test_parse_invalid_json(parser):
    """Test handling of invalid JSON"""
    line = "not valid json"

    event = parser.parse_line(line)

    assert event is None


def test_parse_empty_line(parser):
    """Test handling of empty line"""
    event = parser.parse_line("")

    assert event is None
