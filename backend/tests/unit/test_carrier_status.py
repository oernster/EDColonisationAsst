"""Tests for the carrier status derivation.

The rule these pin is that nothing is invented. CarrierStats has changed shape
across years of game updates, and a carrier the commander merely passed by
yields a far sparser event than their own, so every reading is either present
in the journal or absent from the result. A fuel gauge reading empty because
the event never mentioned fuel would be worse than no gauge at all.

The full event below is a real one, field for field.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.src.models.journal_events import CarrierStatsEvent
from backend.src.services.carrier_status import derive_carrier_status

CARRIER_ID = 3700569600
SEEN_AT = datetime(2026, 6, 21, 17, 54, 26, tzinfo=UTC)

FULL_EVENT: dict[str, Any] = {
    "timestamp": "2026-06-21T17:54:26Z",
    "event": "CarrierStats",
    "CarrierID": CARRIER_ID,
    "CarrierType": "FleetCarrier",
    "Callsign": "X7J-BQG",
    "Name": "MIDNIGHT ELOQUENCE",
    "DockingAccess": "friends",
    "AllowNotorious": False,
    "FuelLevel": 1000,
    "JumpRangeCurr": 500.0,
    "JumpRangeMax": 500.0,
    "PendingDecommission": False,
    "SpaceUsage": {
        "TotalCapacity": 25000,
        "Crew": 1150,
        "Cargo": 6274,
        "CargoSpaceReserved": 0,
        "ShipPacks": 0,
        "ModulePacks": 0,
        "FreeSpace": 17576,
    },
    "Finance": {
        "CarrierBalance": 3401638229,
        "ReserveBalance": 31632848,
        "AvailableBalance": 3280907361,
        "ReservePercent": 1,
        "TaxRate_rearm": 15,
        "TaxRate_refuel": 15,
        "TaxRate_repair": 15,
    },
    "Crew": [
        {"CrewRole": "BlackMarket", "Activated": False},
        {
            "CrewRole": "Captain",
            "Activated": True,
            "Enabled": True,
            "CrewName": "Swara Phillips",
        },
        {
            "CrewRole": "Refuel",
            "Activated": True,
            "Enabled": False,
            "CrewName": "Sara Carey",
        },
    ],
}


def _stats(raw: dict[str, Any]) -> CarrierStatsEvent:
    """A CarrierStats event carrying the given payload."""
    return CarrierStatsEvent(
        timestamp=SEEN_AT,
        event="CarrierStats",
        carrier_id=CARRIER_ID,
        name=raw.get("Name", ""),
        callsign=raw.get("Callsign"),
        raw_data=raw,
    )


def test_no_stats_event_yields_no_status() -> None:
    """A carrier never reported on has an unknown status, not a blank one."""
    assert derive_carrier_status(None) is None


def test_a_real_event_is_read_field_for_field() -> None:
    """The whole surface, against a genuine journal line."""
    status = derive_carrier_status(_stats(FULL_EVENT))

    assert status is not None
    assert status.fuel_level == 1000
    assert status.jump_range_current == 500.0
    assert status.jump_range_max == 500.0
    assert status.pending_decommission is False

    assert status.finance is not None
    assert status.finance.carrier_balance == 3401638229
    assert status.finance.reserve_balance == 31632848
    assert status.finance.available_balance == 3280907361
    assert status.finance.reserve_percent == 1
    assert status.finance.tax_rate_rearm == 15
    assert status.finance.tax_rate_refuel == 15
    assert status.finance.tax_rate_repair == 15


def test_the_crew_roster_keeps_the_journals_order_and_detail() -> None:
    """Hired, switched off and never bought are three different answers."""
    status = derive_carrier_status(_stats(FULL_EVENT))

    assert status is not None
    assert [member.role for member in status.crew] == [
        "BlackMarket",
        "Captain",
        "Refuel",
    ]

    black_market, captain, refuel = status.crew
    assert black_market.activated is False
    assert black_market.enabled is None
    assert black_market.name is None

    assert captain.activated is True
    assert captain.enabled is True
    assert captain.name == "Swara Phillips"

    # Hired but switched off, which from the outside looks like never bought.
    assert refuel.activated is True
    assert refuel.enabled is False


def test_a_pending_decommission_is_carried_through() -> None:
    """The one reading worth shouting about."""
    status = derive_carrier_status(_stats({**FULL_EVENT, "PendingDecommission": True}))

    assert status is not None
    assert status.pending_decommission is True


def test_a_sparse_event_reports_nothing_rather_than_zero() -> None:
    """The whole point: absent is absent, never an invented zero."""
    status = derive_carrier_status(_stats({"CarrierID": CARRIER_ID}))

    assert status is not None
    assert status.fuel_level is None
    assert status.jump_range_current is None
    assert status.jump_range_max is None
    assert status.pending_decommission is False
    assert status.finance is None
    assert status.crew == []


def test_a_finance_block_of_the_wrong_shape_is_ignored() -> None:
    """A journal that put something else under Finance yields no finances."""
    status = derive_carrier_status(_stats({**FULL_EVENT, "Finance": "unavailable"}))

    assert status is not None
    assert status.finance is None


def test_missing_finance_fields_are_left_unset() -> None:
    """A partial Finance block reports what it has and nothing more."""
    status = derive_carrier_status(
        _stats({**FULL_EVENT, "Finance": {"CarrierBalance": 42}})
    )

    assert status is not None
    assert status.finance is not None
    assert status.finance.carrier_balance == 42
    assert status.finance.available_balance is None
    assert status.finance.tax_rate_refuel is None


def test_a_crew_block_of_the_wrong_shape_is_ignored() -> None:
    """Same defence, for the roster."""
    status = derive_carrier_status(_stats({**FULL_EVENT, "Crew": "none aboard"}))

    assert status is not None
    assert status.crew == []


def test_unreadable_crew_entries_are_skipped_not_guessed() -> None:
    """An entry with no role names nothing, so it cannot be shown."""
    status = derive_carrier_status(
        _stats(
            {
                **FULL_EVENT,
                "Crew": [
                    "not a crew member",
                    {"Activated": True},
                    {"CrewRole": 12345},
                    {"CrewRole": "Rearm", "Activated": True},
                ],
            }
        )
    )

    assert status is not None
    assert [member.role for member in status.crew] == ["Rearm"]


def test_crew_fields_of_the_wrong_type_read_as_absent() -> None:
    """A name that is not a name, and a flag that is not a flag."""
    status = derive_carrier_status(
        _stats(
            {
                **FULL_EVENT,
                "Crew": [
                    {
                        "CrewRole": "Repair",
                        "Activated": True,
                        "Enabled": "yes",
                        "CrewName": 99,
                    }
                ],
            }
        )
    )

    assert status is not None
    assert status.crew[0].enabled is None
    assert status.crew[0].name is None


def test_a_flag_where_a_number_belongs_reads_as_absent() -> None:
    """True is 1 to Python, and a fuel level of one tonne would be a lie."""
    status = derive_carrier_status(
        _stats({**FULL_EVENT, "FuelLevel": True, "JumpRangeCurr": True})
    )

    assert status is not None
    assert status.fuel_level is None
    assert status.jump_range_current is None


def test_a_whole_number_jump_range_is_still_a_range() -> None:
    """Journals vary between 500 and 500.0; both are the same distance."""
    status = derive_carrier_status(_stats({**FULL_EVENT, "JumpRangeCurr": 500}))

    assert status is not None
    assert status.jump_range_current == 500.0


def test_text_where_a_number_belongs_reads_as_absent() -> None:
    """Nothing is coerced, because a wrong reading is worse than none."""
    status = derive_carrier_status(
        _stats(
            {
                **FULL_EVENT,
                "FuelLevel": "full",
                "JumpRangeCurr": "unknown",
                "Finance": {**FULL_EVENT["Finance"], "CarrierBalance": "lots"},
            }
        )
    )

    assert status is not None
    assert status.fuel_level is None
    assert status.jump_range_current is None
    assert status.finance is not None
    assert status.finance.carrier_balance is None
