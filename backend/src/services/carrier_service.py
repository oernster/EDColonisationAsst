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

from datetime import timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from ..models.api_models import (
    CarrierStateResponse,
    CurrentCarrierResponse,
    MyCarriersResponse,
)
from ..models.carriers import (
    CarrierCargoItem,
    CarrierIdentity,
    CarrierOrder,
    CarrierOrderType,
    CarrierRole,
    CarrierSpaceUsage,
    CarrierState,
)
from ..models.journal_events import (
    CarrierLocationEvent,
    CarrierStatsEvent,
    CarrierTradeOrderEvent,
    DockedEvent,
    JournalEvent,
)
from ..utils.logger import get_logger
from .market_export_service import load_market_export

logger = get_logger(__name__)


def _prettify_commodity_name(raw_name: str, localised: str | None = None) -> str:
    """
    Produce a human‑friendly commodity name for display.

    Priority:
      1. Use the journal's localized name when provided (Commodity_Localised).
      2. Apply lightweight cleanup heuristics to the internal name as a fallback.

    The goal is to avoid obviously unformatted identifiers such as
    "fruitandvegetables" where possible, without trying to reimplement the
    entire commodity name table in code.
    """
    # Prefer the explicit localized label from the journal if available.
    if localised:
        return localised

    name = raw_name or ""
    name = name.strip()
    if not name:
        return raw_name

    # Strip common journal wrappers like "$Foo_Bar_Name;" if they ever appear
    # in carrier events.
    if name.startswith("$") and name.endswith(";"):
        name = name[1:-1]

    # Replace underscores with spaces.
    name = name.replace("_", " ")

    # Known manual overrides for common unspaced identifiers.
    overrides = {
        "fruitandvegetables": "Fruit and Vegetables",
    }
    key = name.lower().replace(" ", "")
    if key in overrides:
        return overrides[key]

    # Title-case the name, but keep small connector words (and, of, in, the,
    # etc.) lower-case unless they are the first word.
    words = name.split()
    if not words:
        return name

    lowercase_words = {
        "and",
        "or",
        "of",
        "in",
        "on",
        "the",
        "for",
        "to",
        "at",
        "from",
        "by",
        "as",
    }

    normalised_words: list[str] = []
    for idx, w in enumerate(words):
        base = w.lower()
        if idx > 0 and base in lowercase_words:
            normalised_words.append(base)
        else:
            # Capitalise the first character and lower-case the rest.
            normalised_words.append(base[:1].upper() + base[1:])

    return " ".join(normalised_words)


def _normalise_carrier_commodity_key(name: str) -> str:
    """
    Normalise a carrier commodity identifier into a stable key.

    This ensures that logically identical commodities with different raw
    representations (e.g. "titanium", "Titanium", "$Titanium_Name;") are
    treated as the same thing for order aggregation and cancellation.
    """
    key = (name or "").strip().lower()
    if not key:
        return key

    # Strip journal-style wrappers.
    if key.startswith("$") and key.endswith(";"):
        key = key[1:-1]

    # Strip a trailing "_name" suffix if present.
    if key.endswith("_name"):
        key = key[: -len("_name")]

    # Normalise separators and whitespace.
    key = key.replace("_", " ")
    key = key.replace(" ", "")

    return key


# ---------------------------------------------------------------------------
# Low-level event selection helpers
# ---------------------------------------------------------------------------


def find_latest_docked_carrier(events: List[JournalEvent]) -> Optional[DockedEvent]:
    """Return the most recent DockedEvent at a Fleet carrier, if any."""
    for event in reversed(events):
        if isinstance(event, DockedEvent) and event.station_type == "FleetCarrier":
            return event
    return None


def find_latest_carrier_stats_for_id(
    events: List[JournalEvent],
    carrier_id: int,
) -> Optional[CarrierStatsEvent]:
    """Return the latest CarrierStatsEvent for the given carrier id, if any."""
    for event in reversed(events):
        if isinstance(event, CarrierStatsEvent) and event.carrier_id == carrier_id:
            return event
    return None


def find_latest_carrier_stats_for_market_id(
    events: List[JournalEvent],
    market_id: int,
) -> Optional[CarrierStatsEvent]:
    """Return the latest CarrierStatsEvent for the given carrier market id.

    CarrierStats uses CarrierID, which is usually the same as Docked.MarketID,
    but not always. Prefer explicit matching when possible.
    """
    for event in reversed(events):
        if not isinstance(event, CarrierStatsEvent):
            continue
        if event.carrier_id == market_id:
            return event
        # Some journals may include MarketID inside raw_data.
        raw_market_id = event.raw_data.get("MarketID")
        if isinstance(raw_market_id, int) and raw_market_id == market_id:
            return event
    return None


def find_latest_carrier_stats_for_callsign(
    events: List[JournalEvent],
    callsign: str,
) -> Optional[CarrierStatsEvent]:
    """Return the latest CarrierStatsEvent matching the given callsign.

    Some users report Fleet carrier ids differing between Docked.MarketID and
    CarrierStats/CarrierTradeOrder.CarrierID. In those cases, matching on the
    callsign (Docked.StationName) is a practical fallback.
    """

    target = (callsign or "").strip().lower()
    if not target:
        return None

    for event in reversed(events):
        if not isinstance(event, CarrierStatsEvent):
            continue

        cs = event.callsign or event.raw_data.get("Callsign")
        if isinstance(cs, str) and cs.strip().lower() == target:
            return event

    return None


def find_latest_carrier_location_for_id(
    events: List[JournalEvent],
    carrier_id: int,
) -> Optional[CarrierLocationEvent]:
    """Return the latest CarrierLocationEvent for the given carrier id, if any."""
    for event in reversed(events):
        if isinstance(event, CarrierLocationEvent) and event.carrier_id == carrier_id:
            return event
    return None


# ---------------------------------------------------------------------------
# Identity and orders
# ---------------------------------------------------------------------------


def build_identity_from_journal(
    docked_event: DockedEvent,
    stats: Optional[CarrierStatsEvent],
    location: Optional[CarrierLocationEvent],
) -> CarrierIdentity:
    """Construct a CarrierIdentity from journal events.

    Notes
    -----
    - CarrierStats is emitted for the commander's own carrier.
    - Current journal data does not reliably distinguish an official
      squadron carrier from a personal carrier with squadron docking
      access, so we do *not* infer CarrierRole.SQUADRON here.
    """
    # Fleet carriers expose both a Docked.MarketID and CarrierStats/CarrierTradeOrder.CarrierID.
    # In most journals these match, but some users report mismatches. Prefer:
    #   1) CarrierStats.MarketID when present,
    #   2) CarrierStats.CarrierID,
    #   3) Docked.MarketID.
    carrier_unique_id = (
        stats.market_id
        if stats is not None and isinstance(getattr(stats, "market_id", None), int)
        else (stats.carrier_id if stats is not None else docked_event.market_id)
    )
    last_seen_system = (
        location.star_system if location is not None else docked_event.star_system
    )
    last_seen_timestamp = (
        stats.timestamp
        if stats is not None and stats.timestamp is not None
        else docked_event.timestamp
    )

    # Determine role heuristically.
    role = CarrierRole.OTHER
    if stats is not None:
        # Treat any carrier for which we see CarrierStats as OWN.
        # We intentionally do *not* infer a dedicated squadron carrier
        # from the DockingAccess field, because that only controls who
        # may dock there and does not identify the squadron's official
        # carrier.
        role = CarrierRole.OWN

    # Docking access and services, when available.
    docking_access: Optional[str] = None
    services: Optional[list[str]] = None

    # Start with any activated crew roles from CarrierStats.Crew, which
    # represent the installed/active carrier services (e.g. Exploration,
    # Outfitting, PioneerSupplies, VistaGenomics, Bartender, etc.).
    service_names_set: set[str] = set()
    raw_services = None

    if stats is not None:
        docking_access = stats.raw_data.get("DockingAccess")

        crew_list = stats.raw_data.get("Crew") or []
        if isinstance(crew_list, list):
            for crew in crew_list:
                if not isinstance(crew, dict):
                    continue
                if not crew.get("Activated"):
                    continue
                crew_role = crew.get("CrewRole")
                if not isinstance(crew_role, str):
                    continue
                role_lower = crew_role.lower()
                # Ignore non-service roles such as Captain.
                if role_lower == "captain":
                    continue
                service_names_set.add(role_lower)

        # Some journal variants may also expose services directly on CarrierStats.
        raw_services = stats.raw_data.get("Services") or stats.raw_data.get(
            "StationServices"
        )

    # Fall back to StationServices on the Docked event if CarrierStats
    # does not expose a services list explicitly.
    if raw_services is None:
        raw_services = docked_event.raw_data.get("StationServices")

    if isinstance(raw_services, list):
        for item in raw_services:
            if isinstance(item, str):
                service_names_set.add(item.lower())
            elif isinstance(item, dict):
                name = item.get("Name") or item.get("name")
                if isinstance(name, str):
                    service_names_set.add(name.lower())

    if service_names_set:
        # Sort for stable output.
        services = sorted(service_names_set)

    # Choose the most descriptive name/callsign we have.
    name = stats.name if stats is not None and stats.name else docked_event.station_name
    callsign = stats.callsign if stats is not None else None

    return CarrierIdentity(
        carrier_id=carrier_unique_id,
        market_id=docked_event.market_id,
        name=name,
        callsign=callsign,
        role=role,
        docking_access=docking_access,
        last_seen_system=last_seen_system,
        last_seen_timestamp=last_seen_timestamp,
        services=services,
    )


def build_orders_for_carrier(
    events: List[JournalEvent],
    carrier_id: int,
) -> Tuple[List[CarrierCargoItem], List[CarrierOrder], List[CarrierOrder]]:
    """Build cargo, buy and sell orders for a given carrier from CarrierTradeOrder events.

    The journal events look like (examples from your logs):

        {
          "timestamp":"2025-12-15T11:17:37Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"titanium",
          "SaleOrder":23,
          "Price":4446
        }

        {
          "timestamp":"2025-12-15T11:20:15Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"tritium",
          "PurchaseOrder":1,
          "Price":51294
        }

        {
          "timestamp":"2025-12-15T11:20:20Z",
          "event":"CarrierTradeOrder",
          "CarrierID":3700569600,
          "CarrierType":"FleetCarrier",
          "BlackMarket":false,
          "Commodity":"tritium",
          "CancelTrade":true
        }

    We infer order_type via the presence of PurchaseOrder vs SaleOrder.

    Semantics
    ---------
    - Orders are modelled as the *latest known state per commodity*, not as
      a historical list. Subsequent CarrierTradeOrder events for the same
      commodity overwrite earlier ones.
    - CancelTrade events remove any existing buy/sell order and associated
      cargo entry for that commodity.
    - For SELL orders we only treat Stock/Outstanding as indicative of current
      *market stock* when present. The configured SaleOrder size is not a cargo
      snapshot and must not be used as a stock proxy.
    """
    # Latest buy/sell order per commodity.
    buy_orders_by_commodity: dict[str, CarrierOrder] = {}
    sell_orders_by_commodity: dict[str, CarrierOrder] = {}

    # Aggregate cargo stock per commodity based on SELL orders. This does not
    # represent the full physical cargo hold, but it provides a useful view of
    # "stock assigned to the market" for each commodity.
    cargo_by_commodity: dict[str, dict[str, object]] = {}

    for event in events:
        if not isinstance(event, CarrierTradeOrderEvent):
            continue
        if event.carrier_id != carrier_id:
            continue

        commodity_key = _normalise_carrier_commodity_key(event.commodity or "")
        if not commodity_key:
            # Ignore events with no usable commodity identifier.
            continue

        raw = event.raw_data or {}

        # Explicit cancel: clear any existing orders and cargo entry.
        if raw.get("CancelTrade"):
            buy_orders_by_commodity.pop(commodity_key, None)
            sell_orders_by_commodity.pop(commodity_key, None)
            cargo_by_commodity.pop(commodity_key, None)
            continue

        # Some journal variants clear an order by emitting a new CarrierTradeOrder
        # line with SaleOrder/PurchaseOrder set to 0 (rather than CancelTrade).
        # Treat explicit zero values as a cancellation for that order type.
        sale_present = "SaleOrder" in raw
        purchase_present = "PurchaseOrder" in raw
        sale_value = raw.get("SaleOrder")
        purchase_value = raw.get("PurchaseOrder")

        def _as_int(val: object) -> int | None:
            if isinstance(val, bool):
                return None
            if isinstance(val, int):
                return val
            if isinstance(val, float):
                return int(round(val))
            return None

        sale_int = _as_int(sale_value)
        purchase_int = _as_int(purchase_value)

        cleared_any = False
        if sale_present and sale_int == 0:
            sell_orders_by_commodity.pop(commodity_key, None)
            cargo_by_commodity.pop(commodity_key, None)
            cleared_any = True
        if purchase_present and purchase_int == 0:
            buy_orders_by_commodity.pop(commodity_key, None)
            cleared_any = True

        # If this event only exists to clear orders, stop processing.
        if cleared_any and not ((sale_int or 0) > 0 or (purchase_int or 0) > 0):
            continue

        # Determine order type
        order_type: Optional[CarrierOrderType] = None
        if event.sale_order > 0:
            order_type = CarrierOrderType.SELL
        elif event.purchase_order > 0:
            order_type = CarrierOrderType.BUY
        else:
            # Neither sale nor purchase order (and no CancelTrade): ignore.
            continue

        # Original amount is the configured order size.
        original_amount = event.sale_order if order_type == CarrierOrderType.SELL else event.purchase_order

        # Remaining amount (Outstanding) is optional in journal output.
        # When not provided we keep it as the configured size for display
        # purposes, but we do NOT use it to infer cargo stock.
        remaining_amount = event.outstanding if event.outstanding >= 0 else original_amount

        # Derive a best-effort view of *current market stock* for SELL orders.
        # Priority:
        #   1. Explicit Stock when present.
        #   2. Outstanding when present.
        # We intentionally do NOT fall back to SaleOrder (configured size).
        derived_stock: int | None = None
        if order_type == CarrierOrderType.SELL:
            if event.stock >= 0:
                derived_stock = event.stock
            elif event.outstanding >= 0:
                derived_stock = event.outstanding

        # If we could not infer a sensible stock value, keep None so that the
        # API surface can distinguish "unknown" from an explicit zero.
        order_stock: Optional[int]
        if order_type == CarrierOrderType.SELL and derived_stock is not None:
            order_stock = max(derived_stock, 0)
        elif event.stock >= 0:
            order_stock = max(event.stock, 0)
        else:
            order_stock = None

        # Choose a human‑friendly display name, preferring the journal's
        # localized label when available and falling back to a prettified
        # internal name (e.g. "fruitandvegetables" → "Fruit and Vegetables").
        display_name = _prettify_commodity_name(
            raw_name=event.commodity,
            localised=event.commodity_localised,
        )

        order = CarrierOrder(
            order_type=order_type,
            commodity_name=event.commodity,
            commodity_name_localised=display_name,
            price=event.price,
            original_amount=max(original_amount, 0),
            remaining_amount=max(remaining_amount, 0),
            stock=order_stock,
        )

        if order_type == CarrierOrderType.SELL:
            # Latest SELL order wins for this commodity.
            sell_orders_by_commodity[commodity_key] = order
            # A carrier cannot practically have both BUY and SELL orders for the
            # same commodity; discard any stale BUY for this key.
            buy_orders_by_commodity.pop(commodity_key, None)

            # Reflect SELL orders into a simple cargo/market-stock view.
            # Only include commodities when we have a stock value (Stock or
            # Outstanding) from the journal.
            if derived_stock is None:
                # Unknown stock: do not show a per-commodity row.
                cargo_by_commodity.pop(commodity_key, None)
            else:
                stock_qty = max(int(derived_stock), 0)
                if stock_qty == 0:
                    cargo_by_commodity.pop(commodity_key, None)
                else:
                    display_name = _prettify_commodity_name(
                        raw_name=event.commodity,
                        localised=event.commodity_localised,
                    )
                    cargo_by_commodity[commodity_key] = {
                        "commodity_name": event.commodity,
                        "commodity_name_localised": display_name,
                        "stock": stock_qty,
                        "reserved": 0,
                        "capacity": None,
                    }
        else:
            # Latest BUY order wins for this commodity.
            buy_orders_by_commodity[commodity_key] = order
            # Likewise, a BUY order replaces any previous SELL configuration for
            # the same commodity.
            sell_orders_by_commodity.pop(commodity_key, None)

    # Convert cargo map into CarrierCargoItem list
    cargo_items: List[CarrierCargoItem] = []
    for data in cargo_by_commodity.values():
        cargo_items.append(
            CarrierCargoItem(
                commodity_name=data["commodity_name"],  # type: ignore[arg-type]
                commodity_name_localised=data[
                    "commodity_name_localised"
                ],  # type: ignore[arg-type]
                stock=int(data["stock"]),  # type: ignore[arg-type]
                reserved=int(data["reserved"]),  # type: ignore[arg-type]
                capacity=data["capacity"],  # type: ignore[arg-type]
            )
        )

    buy_orders = list(buy_orders_by_commodity.values())
    sell_orders = list(sell_orders_by_commodity.values())

    return cargo_items, buy_orders, sell_orders


# ---------------------------------------------------------------------------
# High-level composition helpers (used by API layer)
# ---------------------------------------------------------------------------


def build_current_carrier_response(
    events: List[JournalEvent],
) -> CurrentCarrierResponse:
    """Construct CurrentCarrierResponse from a sequence of journal events."""
    if not events:
        return CurrentCarrierResponse(docked_at_carrier=False, carrier=None)

    docked_carrier = find_latest_docked_carrier(events)
    if docked_carrier is None:
        return CurrentCarrierResponse(docked_at_carrier=False, carrier=None)

    stats = find_latest_carrier_stats_for_id(events, docked_carrier.market_id)
    location = find_latest_carrier_location_for_id(events, docked_carrier.market_id)
    identity = build_identity_from_journal(docked_carrier, stats, location)

    return CurrentCarrierResponse(docked_at_carrier=True, carrier=identity)


def build_current_carrier_state_response(
    events: List[JournalEvent],
    *,
    journal_dir: Path | None = None,
) -> Optional[CarrierStateResponse]:
    """Construct CarrierStateResponse for the currently docked carrier.

    Returns:
        CarrierStateResponse if a Fleet carrier docking context can be
        determined from the events, or None if the commander is not docked
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
        stats = find_latest_carrier_stats_for_callsign(events, docked_carrier.station_name)

    location = find_latest_carrier_location_for_id(events, docked_carrier.market_id)
    if location is None and stats is not None:
        # If Docked.MarketID does not match CarrierID, CarrierLocation will also
        # typically be keyed by CarrierID.
        location = find_latest_carrier_location_for_id(events, stats.carrier_id)
    identity = build_identity_from_journal(docked_carrier, stats, location)

    carrier_trade_id = identity.carrier_id or docked_carrier.market_id

    # CarrierTradeOrder events are typically emitted in bursts that represent a
    # *snapshot* of the carrier market configuration. Some sessions may only
    # emit deltas. To reduce stale/phantom orders persisting forever, we try to
    # detect a recent snapshot burst and, when present, treat it as authoritative.
    # Prefer orders from the current docking context.
    events_since_docked = [
        e
        for e in events
        if getattr(e, "timestamp", None) is not None and e.timestamp >= docked_carrier.timestamp
    ]
    trade_events_since_docked: list[CarrierTradeOrderEvent] = [
        e
        for e in events_since_docked
        if isinstance(e, CarrierTradeOrderEvent)
        and e.carrier_id == carrier_trade_id
    ]

    trade_orders_scope: str = "none"

    # Use the newest journal timestamp as a proxy for "now" so tests remain
    # deterministic, and so we can detect stale trade-order data when the
    # user is actively playing but trade orders have not been emitted recently.
    journal_now = max((e.timestamp for e in events), default=docked_carrier.timestamp)

    trade_events: list[CarrierTradeOrderEvent] = [
        e
        for e in events
        if isinstance(e, CarrierTradeOrderEvent) and e.carrier_id == carrier_trade_id
    ]

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

    # Market.json snapshot merge
    # --------------------------------
    # CarrierTradeOrder journal lines are not always emitted as a full snapshot;
    # sometimes they are deltas (e.g. you change ONE buy order and only that
    # commodity is written). If we treat those deltas as authoritative, the UI
    # can incorrectly "delete" other existing orders.
    #
    # Market.json is a snapshot and is typically updated when the carrier market
    # changes, so we merge it in to fill any missing commodities.
    if trade_orders_scope in ("none", "stale", "since_docked"):
        try:
            # Prefer the directory passed by the API layer so unit tests can
            # control Market.json inputs deterministically.
            if journal_dir is None:
                from ..utils.journal import get_journal_directory  # local import

                resolved = get_journal_directory()
            else:
                resolved = journal_dir

            snap = load_market_export(resolved)
        except Exception:
            snap = None

        if (
            snap is not None
            and snap.station_type == "FleetCarrier"
            and snap.market_id is not None
            and docked_carrier.market_id is not None
            and snap.market_id == docked_carrier.market_id
        ):
            # Convert Market.json items into CarrierOrder rows.
            # ED semantics:
            #   - Demand > 0: carrier buys from commander (BUY order)
            #               Price shown is SellPrice.
            #   - Stock > 0: carrier sells to commander (SELL order)
            #               Price shown is BuyPrice.
            from ..models.carriers import CarrierOrderType

            buy_from_market_by_key: dict[str, CarrierOrder] = {}
            sell_from_market_by_key: dict[str, CarrierOrder] = {}
            cargo_from_market_by_key: dict[str, CarrierCargoItem] = {}

            for it in snap.items:
                display = it.name_localised or it.commodity_key
                key = it.commodity_key

                if it.demand > 0:
                    price = it.sell_price if it.sell_price > 0 else it.buy_price
                    buy_from_market_by_key[key] = CarrierOrder(
                        order_type=CarrierOrderType.BUY,
                        commodity_name=key,
                        commodity_name_localised=display,
                        price=max(price, 0),
                        original_amount=it.demand,
                        remaining_amount=it.demand,
                        stock=None,
                    )

                if it.stock > 0:
                    price = it.buy_price if it.buy_price > 0 else it.sell_price
                    sell_from_market_by_key[key] = CarrierOrder(
                        order_type=CarrierOrderType.SELL,
                        commodity_name=key,
                        commodity_name_localised=display,
                        price=max(price, 0),
                        original_amount=it.stock,
                        remaining_amount=it.stock,
                        stock=it.stock,
                    )
                    cargo_from_market_by_key[key] = CarrierCargoItem(
                        commodity_name=key,
                        commodity_name_localised=display,
                        stock=it.stock,
                        reserved=0,
                        capacity=None,
                    )

            buy_by_key: dict[str, CarrierOrder] = {
                (o.commodity_name or "").lower(): o for o in (buy_orders or [])
            }
            sell_by_key: dict[str, CarrierOrder] = {
                (o.commodity_name or "").lower(): o for o in (sell_orders or [])
            }

            # If the market snapshot is newer than the newest CarrierTradeOrder
            # line we saw, treat it as authoritative (replace lists). Otherwise,
            # treat it as a supplemental snapshot and only FILL missing
            # commodities to avoid phantom deletions.
            market_is_newer = (
                snap.timestamp is not None
                and latest_trade_ts is not None
                and snap.timestamp >= latest_trade_ts
            )

            if market_is_newer or trade_orders_scope in ("none", "stale"):
                buy_orders = list(buy_from_market_by_key.values())
                sell_orders = list(sell_from_market_by_key.values())
                cargo = list(cargo_from_market_by_key.values())
                trade_orders_scope = "market_export"
            else:
                # Fill missing commodities only.
                for key, order in buy_from_market_by_key.items():
                    if key.lower() not in buy_by_key:
                        buy_by_key[key.lower()] = order
                for key, order in sell_from_market_by_key.items():
                    if key.lower() not in sell_by_key:
                        sell_by_key[key.lower()] = order
                buy_orders = list(buy_by_key.values())
                sell_orders = list(sell_by_key.values())
                # Only fill cargo rows when we have a sell-side stock snapshot.
                if not cargo and cargo_from_market_by_key:
                    cargo = list(cargo_from_market_by_key.values())
                trade_orders_scope = "since_docked"

            # Prefer the Market.json timestamp for snapshot_time when used.
            if snap.timestamp is not None and snap.timestamp > snapshot_time:
                snapshot_time = snap.timestamp

    # Derive cargo and capacity metrics from CarrierStats.SpaceUsage when present.
    total_cargo_tonnage: Optional[int] = None
    total_capacity_tonnage: Optional[int] = None
    free_space_tonnage: Optional[int] = None
    space_usage_model: Optional[CarrierSpaceUsage] = None

    if stats is not None:
        try:
            space_usage = stats.raw_data.get("SpaceUsage") or {}
            cargo_tonnage = space_usage.get("Cargo")
            total_capacity = space_usage.get("TotalCapacity")
            free_space = space_usage.get("FreeSpace")

            # Additional breakdown fields often present in CarrierStats.SpaceUsage.
            crew_usage = space_usage.get("Crew")
            module_packs = space_usage.get("ModulePacks")
            cargo_reserved = space_usage.get("CargoSpaceReserved")

            if isinstance(cargo_tonnage, (int, float)):
                total_cargo_tonnage = int(round(cargo_tonnage))
            if isinstance(total_capacity, (int, float)):
                total_capacity_tonnage = int(round(total_capacity))
            if isinstance(free_space, (int, float)):
                free_space_tonnage = int(round(free_space))

            def _as_int(val: object) -> Optional[int]:
                if isinstance(val, int):
                    return val
                if isinstance(val, float):
                    return int(round(val))
                return None

            # Preserve a raw SpaceUsage breakdown for frontend calculations.
            space_usage_model = CarrierSpaceUsage(
                total_capacity=_as_int(total_capacity),
                crew=_as_int(crew_usage),
                module_packs=_as_int(module_packs),
                cargo=_as_int(cargo_tonnage),
                cargo_space_reserved=_as_int(cargo_reserved),
                free_space=_as_int(free_space),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to derive cargo/capacity metrics from CarrierStats",
                exc_info=True,
            )

    state = CarrierState(
        identity=identity,
        cargo=cargo,
        total_cargo_tonnage=total_cargo_tonnage,
        total_capacity_tonnage=total_capacity_tonnage,
        free_space_tonnage=free_space_tonnage,
        space_usage=space_usage_model,
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        trade_orders_scope=trade_orders_scope,
        snapshot_time=snapshot_time,
    )
    return CarrierStateResponse(carrier=state)


def build_my_carriers_response(events: List[JournalEvent]) -> MyCarriersResponse:
    """Build MyCarriersResponse listing the commander's Fleet carriers.

    This mirrors the behaviour of the original /api/carriers/mine logic:

    - Uses CarrierStats as the authoritative source for the commander's
      carriers.
    - Uses CarrierLocation to enrich carriers with last-known system and
      address.
    - Prefers a real Docked event (with StationServices) when available to
      construct CarrierIdentity; falls back to a synthetic DockedEvent
      otherwise.
    - Does not infer an explicit separate 'squadron carrier' list from
      DockingAccess; squadron_carriers remains empty.
    """
    if not events:
        return MyCarriersResponse(own_carriers=[], squadron_carriers=[])

    latest_location_by_id: dict[int, CarrierLocationEvent] = {}
    latest_docked_by_market_id: dict[int, DockedEvent] = {}

    for event in events:
        if isinstance(event, CarrierLocationEvent):
            latest_location_by_id[event.carrier_id] = event
        elif isinstance(event, DockedEvent) and event.station_type == "FleetCarrier":
            latest_docked_by_market_id[event.market_id] = event

    own_carriers: List[CarrierIdentity] = []
    squadron_carriers: List[CarrierIdentity] = []

    seen_ids: set[int] = set()
    for event in events:
        if not isinstance(event, CarrierStatsEvent):
            continue

        carrier_id = event.carrier_id
        if carrier_id in seen_ids:
            continue
        seen_ids.add(carrier_id)

        location = latest_location_by_id.get(carrier_id)
        docked = latest_docked_by_market_id.get(carrier_id)

        if docked is not None:
            identity = build_identity_from_journal(docked, event, location)
        else:
            fake_docked = DockedEvent(
                timestamp=event.timestamp,
                event=event.event,
                station_name=event.name or "Unknown Carrier",
                station_type="FleetCarrier",
                star_system=location.star_system if location is not None else "",
                system_address=location.system_address if location is not None else 0,
                market_id=carrier_id,
                station_faction={},
                station_government="",
                station_economy="",
                station_economies=[],
                raw_data=event.raw_data,
            )
            identity = build_identity_from_journal(fake_docked, event, location)

        own_carriers.append(identity)

    return MyCarriersResponse(
        own_carriers=own_carriers, squadron_carriers=squadron_carriers
    )
