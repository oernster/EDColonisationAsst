"""Reading the carrier's own systems out of a CarrierStats event.

CarrierStats carries far more than the identity and space usage the rest of
this package takes from it: the fuel tank, the jump range, the balances and
the full crew roster all arrive in the same line. This module lifts those out.

The one rule worth stating is that nothing here invents a value. Every field
is read only if the journal supplied it and of the type expected, because the
alternative is a fuel gauge that reads zero when the truth is that this
particular event never mentioned fuel. A carrier the commander has merely
seen, and older journals generally, both produce sparser events than a
current CarrierStats for an owned carrier.
"""

from __future__ import annotations

from typing import Any

from ..models.carrier_status import (
    CarrierCrewMember,
    CarrierFinance,
    CarrierStatus,
)
from ..models.journal_events import CarrierStatsEvent
from ..utils.logger import get_logger

logger = get_logger(__name__)

_FINANCE_KEY = "Finance"
_CREW_KEY = "Crew"

# Journal field to model field, for the flat integer money values.
_FINANCE_INTS = {
    "CarrierBalance": "carrier_balance",
    "ReserveBalance": "reserve_balance",
    "AvailableBalance": "available_balance",
    "ReservePercent": "reserve_percent",
    "TaxRate_rearm": "tax_rate_rearm",
    "TaxRate_refuel": "tax_rate_refuel",
    "TaxRate_repair": "tax_rate_repair",
}


def _int_or_none(value: Any) -> int | None:
    """Return the value when it is a whole number, else None.

    Booleans are excluded deliberately: Python treats True as 1, and a journal
    that put a flag where a balance belongs should read as missing, not as one
    credit.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _float_or_none(value: Any) -> float | None:
    """Return the value as a float when it is numeric, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _finance(raw: dict[str, Any]) -> CarrierFinance | None:
    """Build the finance view, or None when the event carried no Finance."""
    finance = raw.get(_FINANCE_KEY)
    if not isinstance(finance, dict):
        return None

    fields = {
        attribute: _int_or_none(finance.get(key))
        for key, attribute in _FINANCE_INTS.items()
    }
    return CarrierFinance(**fields)


def _crew(raw: dict[str, Any]) -> list[CarrierCrewMember]:
    """Build the crew roster, keeping the journal's own order."""
    crew = raw.get(_CREW_KEY)
    if not isinstance(crew, list):
        return []

    members: list[CarrierCrewMember] = []
    for entry in crew:
        if not isinstance(entry, dict):
            continue
        role = entry.get("CrewRole")
        if not isinstance(role, str):
            continue

        enabled = entry.get("Enabled")
        name = entry.get("CrewName")
        members.append(
            CarrierCrewMember(
                role=role,
                activated=bool(entry.get("Activated")),
                enabled=enabled if isinstance(enabled, bool) else None,
                name=name if isinstance(name, str) else None,
            )
        )
    return members


def derive_carrier_status(stats: CarrierStatsEvent | None) -> CarrierStatus | None:
    """Derive the carrier's running state from its latest CarrierStats.

    Args:
        stats: The newest CarrierStats event for the carrier, if one was seen.

    Returns:
        The carrier's status, or None when no CarrierStats is available at
        all, which is the honest answer for a carrier the journals only
        mention in passing.
    """
    if stats is None:
        return None

    raw = stats.raw_data
    return CarrierStatus(
        fuel_level=_int_or_none(raw.get("FuelLevel")),
        jump_range_current=_float_or_none(raw.get("JumpRangeCurr")),
        jump_range_max=_float_or_none(raw.get("JumpRangeMax")),
        pending_decommission=bool(raw.get("PendingDecommission")),
        finance=_finance(raw),
        crew=_crew(raw),
    )


__all__ = ["derive_carrier_status"]
