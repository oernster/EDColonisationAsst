"""Parsers for the four events describing the commander's own state.

`Location`, `FSDJump` and `Docked` are what SystemTracker follows to know
where the commander is and what they are docked at; `Commander` carries who
they are. The module is named for the commander rather than for the
`Commander` event, which is one of the four.

Every parser here is a direct field map onto its typed event. Nothing in this
module normalises anything, which is the difference between it and
colonisation_event_parser beside it: none of these four events has changed
shape in service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..models.journal_events import (
    CommanderEvent,
    DockedEvent,
    FSDJumpEvent,
    LocationEvent,
    UndockedEvent,
)


def parse_location(data: dict[str, Any], timestamp: datetime) -> LocationEvent:
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


def parse_fsd_jump(data: dict[str, Any], timestamp: datetime) -> FSDJumpEvent:
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


def parse_docked(data: dict[str, Any], timestamp: datetime) -> DockedEvent:
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


def parse_undocked(data: dict[str, Any], timestamp: datetime) -> UndockedEvent:
    """Parse Undocked event.

    Every field is optional. The event's value here is that it happened at
    all, and older journals are inconsistent about what they attach to it.
    """
    return UndockedEvent(
        timestamp=timestamp,
        event=data["event"],
        station_name=data.get("StationName"),
        station_type=data.get("StationType"),
        market_id=data.get("MarketID"),
        raw_data=data,
    )


def parse_commander(data: dict[str, Any], timestamp: datetime) -> CommanderEvent:
    """Parse Commander event"""
    return CommanderEvent(
        timestamp=timestamp,
        event=data["event"],
        name=data["Name"],
        fid=data["FID"],
        raw_data=data,
    )


__all__ = [
    "parse_commander",
    "parse_docked",
    "parse_fsd_jump",
    "parse_location",
]
