"""The carrier's balance over time, from the readings the journals carry.

This exists because the thing actually wanted, an upkeep bill, cannot be had.
The journal records no upkeep event, and the balance movements it does record
cannot be attributed: measured across six months of real journals the reserve
balance never moved at all, and of seventy downward movements not one fell on
a weekly cadence, because they are mixed in with tritium purchases, crew
changes and trade income. Anything labelled "upkeep" here would be invention.

So this reports what was observed and nothing more: when the balance changed,
what it changed to, and by how much. No cause is attached to any movement.

Two further honesties are built in. Only movements are kept, because the game
writes the same balance hundreds of times in a session and a list of unchanged
numbers says nothing. And the window is described explicitly, because the game
only writes while the commander is playing, so the history has gaps that
reached sixty-three days in the journals this was measured against.
"""

from __future__ import annotations

from ..models.carrier_status import CarrierBalanceEntry, CarrierBalanceHistory
from ..models.journal_events import CarrierStatsEvent, JournalEvent
from ..utils.logger import get_logger

logger = get_logger(__name__)

# How many movements to carry to the interface. The full history runs to
# hundreds; what a commander reads at a glance is the recent few, and the
# summary above them covers the whole window regardless.
MAX_ENTRIES = 12

_FINANCE_KEY = "Finance"
_BALANCE_KEY = "CarrierBalance"


def _balance_of(event: CarrierStatsEvent) -> int | None:
    """Read the carrier balance out of a CarrierStats event, if it carries one.

    Booleans are rejected for the same reason as everywhere else in this
    package: Python counts True as 1, and a flag misread as a balance would
    show up as a carrier holding a single credit.
    """
    finance = event.raw_data.get(_FINANCE_KEY)
    if not isinstance(finance, dict):
        return None

    balance = finance.get(_BALANCE_KEY)
    if isinstance(balance, bool) or not isinstance(balance, int):
        return None
    return balance


def derive_balance_history(
    events: list[JournalEvent],
    carrier_id: int,
    *,
    limit: int = MAX_ENTRIES,
) -> CarrierBalanceHistory:
    """Derive the balance history for one carrier.

    Args:
        events: The journal event stream, oldest first.
        carrier_id: The carrier whose balance to follow.
        limit: How many of the most recent movements to keep.

    Returns:
        The history. Empty when the journals carry no balance for this
        carrier, which is not the same as a balance of zero.
    """
    movements: list[CarrierBalanceEntry] = []
    previous: int | None = None
    first_balance: int | None = None
    first_seen = None
    last_seen = None

    for event in events:
        if not isinstance(event, CarrierStatsEvent) or event.carrier_id != carrier_id:
            continue

        balance = _balance_of(event)
        if balance is None:
            continue

        if first_balance is None:
            first_balance = balance
            first_seen = event.timestamp

        last_seen = event.timestamp

        if previous is not None and balance != previous:
            movements.append(
                CarrierBalanceEntry(
                    recorded_at=event.timestamp,
                    balance=balance,
                    change=balance - previous,
                )
            )

        previous = balance

    if previous is None:
        return CarrierBalanceHistory()

    net_change = None if first_balance is None else previous - first_balance

    return CarrierBalanceHistory(
        # Newest first: the recent few are what gets read.
        entries=list(reversed(movements))[:limit],
        current_balance=previous,
        observed_from=first_seen,
        observed_to=last_seen,
        net_change=net_change,
        movements=len(movements),
    )


__all__ = ["MAX_ENTRIES", "derive_balance_history"]
