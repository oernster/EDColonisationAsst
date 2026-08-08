"""Domain logic for Fleet carrier state reconstruction.

This module contains side-effect free helpers used by the /api/carriers
endpoints to:

- Interpret Elite Dangerous journal events related to Fleet carriers.
- Derive CarrierIdentity instances from Docked, CarrierStats and
  CarrierLocation events.
- Build current cargo, buy and sell orders from CarrierTradeOrder
  events.
- Derive per-carrier state suitable for API exposure.

The goal is to keep src.api.carriers focused on HTTP concerns (routing,
status codes, response models) while this module encapsulates the
journal interpretation rules. This separation improves testability and
helps keep API modules under the desired line length threshold.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from ..models.api_models import (
    CarrierStateResponse,
    CurrentCarrierResponse,
)
from ..models.carriers import (
    CarrierState,
)
from ..models.journal_events import (
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
    DockedEvent,
    JournalEvent,
    MarketTransactionEvent,
)
from ..utils.logger import get_logger

# carrier_service is the public surface for the carrier domain: the API
# module and the tests import from here, so the split below is invisible to
# them. __all__ is what says these re-exports are intentional; without it
# they read as unused imports and an auto-fixer deletes them.
from .carrier_events import (
    find_latest_carrier_location_for_id,
    find_latest_carrier_stats_for_callsign,
    find_latest_carrier_stats_for_id,
    find_latest_carrier_stats_for_market_id,
    find_latest_docked_carrier,
)
from .carrier_fleet import build_my_carriers_response
from .carrier_hold import derive_carrier_hold
from .carrier_identity import build_identity_from_journal
from .carrier_market import derive_space_usage, merge_market_export
from .carrier_naming import (
    _normalise_carrier_commodity_key,
    _prettify_commodity_name,
)
from .carrier_orders import build_orders_for_carrier
from .carrier_status import derive_carrier_status
from .carrier_transit import derive_carrier_transit

logger = get_logger(__name__)

__all__ = [
    "_normalise_carrier_commodity_key",
    "_prettify_commodity_name",
    "build_current_carrier_response",
    "build_current_carrier_state_response",
    "build_identity_from_journal",
    "build_my_carriers_response",
    "build_orders_for_carrier",
    "derive_carrier_transit",
    "find_latest_carrier_location_for_id",
    "find_latest_carrier_stats_for_callsign",
    "find_latest_carrier_stats_for_id",
    "find_latest_carrier_stats_for_market_id",
    "find_latest_docked_carrier",
]


# ---------------------------------------------------------------------------
# Low-level event selection helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Identity and orders
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# High-level composition helpers (used by API layer)
# ---------------------------------------------------------------------------


def _journal_carrier_id(
    docked_carrier: DockedEvent,
    stats: CarrierStatsEvent | None,
) -> int:
    """Return the CarrierID the jump events are keyed by.

    CarrierJumpRequest and CarrierJumpCancelled both carry CarrierID, which is
    what CarrierStats reports. Docked.MarketID usually matches it and is the
    only key available when no CarrierStats has been seen.
    """
    if stats is not None:
        return stats.carrier_id
    return docked_carrier.market_id


def build_current_carrier_response(
    events: list[JournalEvent],
    *,
    now: datetime | None = None,
) -> CurrentCarrierResponse:
    """Construct CurrentCarrierResponse from a sequence of journal events.

    Args:
        events: The journal event stream, oldest first.
        now: Current time, passed through to the transit derivation.
    """
    if not events:
        return CurrentCarrierResponse(docked_at_carrier=False, carrier=None)

    docked_carrier = find_latest_docked_carrier(events)
    if docked_carrier is None:
        return CurrentCarrierResponse(docked_at_carrier=False, carrier=None)

    stats = find_latest_carrier_stats_for_id(events, docked_carrier.market_id)
    location = find_latest_carrier_location_for_id(events, docked_carrier.market_id)
    transit = derive_carrier_transit(
        events, _journal_carrier_id(docked_carrier, stats), now=now
    )
    identity = build_identity_from_journal(docked_carrier, stats, location, transit)

    return CurrentCarrierResponse(docked_at_carrier=True, carrier=identity)


def build_current_carrier_state_response(
    events: list[JournalEvent],
    *,
    journal_dir: Path | None = None,
    now: datetime | None = None,
) -> CarrierStateResponse | None:
    """Construct CarrierStateResponse for the currently docked carrier.

    Args:
        events: The journal event stream, oldest first.
        journal_dir: Where to look for the Market.json export.
        now: Current time, passed through to the transit derivation.

    Returns:
        CarrierStateResponse if a Fleet carrier docking context can be
        determined from the events, None if the commander is not docked
        at a Fleet carrier.
    """
    if not events:
        return None

    docked_carrier = find_latest_docked_carrier(events)
    if docked_carrier is None:
        return None

    stats = find_latest_carrier_stats_for_market_id(events, docked_carrier.market_id)
    if stats is None:
        # Fallback: match CarrierStats by callsign (Docked.StationName).
        stats = find_latest_carrier_stats_for_callsign(
            events, docked_carrier.station_name
        )

    location = find_latest_carrier_location_for_id(events, docked_carrier.market_id)
    if location is None and stats is not None:
        # If Docked.MarketID does not match CarrierID, CarrierLocation will also
        # typically be keyed by CarrierID.
        location = find_latest_carrier_location_for_id(events, stats.carrier_id)
    transit = derive_carrier_transit(
        events, _journal_carrier_id(docked_carrier, stats), now=now
    )
    identity = build_identity_from_journal(docked_carrier, stats, location, transit)

    carrier_trade_id = identity.carrier_id or docked_carrier.market_id

    # CarrierTradeOrder events are typically emitted in bursts that represent a
    # *snapshot* of the carrier market configuration. Some sessions may only
    # emit deltas. To reduce stale/phantom orders persisting forever, we try to
    # detect a recent snapshot burst and treat it as authoritative when present.
    # Prefer orders from the current docking context.
    events_since_docked = [
        e
        for e in events
        if getattr(e, "timestamp", None) is not None
        and e.timestamp >= docked_carrier.timestamp
    ]
    trade_events_since_docked: list[CarrierTradeOrderEvent] = [
        e
        for e in events_since_docked
        if isinstance(e, CarrierTradeOrderEvent) and e.carrier_id == carrier_trade_id
    ]

    trade_orders_scope: str = "none"

    # Use the newest journal timestamp as a proxy for "now" so tests remain
    # deterministic; so we can detect stale trade-order data when the
    # user is actively playing but trade orders have not been emitted recently.
    journal_now = max((e.timestamp for e in events), default=docked_carrier.timestamp)

    selected_trade_events: list[JournalEvent]
    latest_trade_ts = None

    # Strategy (anti-hallucination):
    # For the *currently docked* carrier state endpoint, only treat
    # CarrierTradeOrder events observed in the current Docked-at-carrier
    # context as authoritative. Falling back to older history can cause the UI
    # to show sell orders that are no longer present in-game.
    if trade_events_since_docked:
        selected_trade_events = list(trade_events_since_docked)
        latest_trade_ts = max(e.timestamp for e in trade_events_since_docked)
        trade_orders_scope = "since_docked"
    else:
        selected_trade_events = []
        latest_trade_ts = None
        trade_orders_scope = "none"

    # Staleness guardrail (only applicable when we have a post-dock snapshot):
    # if the latest trade-order timestamp is older than the general journal
    # activity by too much, do not surface it.
    STALE_AFTER = timedelta(minutes=30)
    if (
        latest_trade_ts is not None
        and trade_orders_scope == "since_docked"
        and (journal_now - latest_trade_ts) > STALE_AFTER
    ):
        selected_trade_events = []
        trade_orders_scope = "stale"

    # Snapshot time baseline.
    # We compute this early so that Market.json fallback can safely bump it.
    snapshot_time = docked_carrier.timestamp
    if stats is not None and stats.timestamp > snapshot_time:
        snapshot_time = stats.timestamp
    if location is not None and location.timestamp > snapshot_time:
        snapshot_time = location.timestamp
    if latest_trade_ts is not None and latest_trade_ts > snapshot_time:
        snapshot_time = latest_trade_ts

    cargo, buy_orders, sell_orders = build_orders_for_carrier(
        selected_trade_events, carrier_trade_id
    )

    merged = merge_market_export(
        cargo=cargo,
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        snapshot_time=snapshot_time,
        trade_orders_scope=trade_orders_scope,
        journal_dir=journal_dir,
        docked_carrier=docked_carrier,
        latest_trade_ts=latest_trade_ts,
        # Passed whole, deliberately NOT the staleness-filtered list: a cancel
        # dropped for being old still has to override an export written before
        # it; otherwise the order it cancelled comes back.
        trade_events=trade_events_since_docked,
    )
    cargo = merged.cargo
    buy_orders = merged.buy_orders
    sell_orders = merged.sell_orders
    snapshot_time = merged.snapshot_time
    trade_orders_scope = merged.trade_orders_scope

    metrics = derive_space_usage(stats)
    total_cargo_tonnage = metrics.total_cargo_tonnage
    total_capacity_tonnage = metrics.total_capacity_tonnage
    free_space_tonnage = metrics.free_space_tonnage
    space_usage_model = metrics.space_usage

    # The hold is anchored on the same export the merge above already read, then
    # carried forward by the commander's own trades against this carrier. It is
    # deliberately independent of trade_orders_scope: what the carrier holds is
    # not the same question as what it is currently offering.
    hold = derive_carrier_hold(
        snapshot=merged.market_snapshot,
        transactions=[e for e in events if isinstance(e, MarketTransactionEvent)],
        carrier_market_id=docked_carrier.market_id,
        reported_tonnage=total_cargo_tonnage,
        fallback_items=cargo,
    )

    state = CarrierState(
        identity=identity,
        cargo=hold.items,
        cargo_snapshot_time=hold.snapshot_time,
        cargo_unaccounted_tonnage=hold.unaccounted_tonnage,
        total_cargo_tonnage=total_cargo_tonnage,
        total_capacity_tonnage=total_capacity_tonnage,
        free_space_tonnage=free_space_tonnage,
        space_usage=space_usage_model,
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        trade_orders_scope=trade_orders_scope,
        status=derive_carrier_status(stats),
        snapshot_time=snapshot_time,
    )
    return CarrierStateResponse(carrier=state)
