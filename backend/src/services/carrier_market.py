"""Market.json reconciliation and CarrierStats space-usage arithmetic.

Two passages lifted out of :func:`build_current_carrier_state_response`, which
was doing three jobs in one function. Both are pure: they take what they need
and return a frozen result rather than mutating the caller's locals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..models.carriers import (
    CarrierCargoItem,
    CarrierOrder,
    CarrierSpaceUsage,
)
from ..models.journal_events import CarrierStatsEvent, DockedEvent
from ..utils.logger import get_logger
from .market_export_service import MarketExportSnapshot, load_market_export

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MarketMergeResult:
    """Orders after reconciliation with the Market.json snapshot."""

    cargo: list[CarrierCargoItem]
    buy_orders: list[CarrierOrder]
    sell_orders: list[CarrierOrder]
    snapshot_time: datetime
    trade_orders_scope: str
    # The export this merge read, carried out so the hold derivation can anchor
    # on the same one rather than reading the file a second time.
    market_snapshot: MarketExportSnapshot | None = None


@dataclass(frozen=True, slots=True)
class SpaceUsageMetrics:
    """Tonnages derived from a CarrierStats SpaceUsage payload."""

    total_cargo_tonnage: int | None = None
    total_capacity_tonnage: int | None = None
    free_space_tonnage: int | None = None
    space_usage: CarrierSpaceUsage | None = None


def merge_market_export(
    *,
    cargo: list[CarrierCargoItem],
    buy_orders: list[CarrierOrder],
    sell_orders: list[CarrierOrder],
    snapshot_time: datetime,
    trade_orders_scope: str,
    journal_dir: Path | None,
    docked_carrier: DockedEvent,
    latest_trade_ts: datetime | None,
) -> MarketMergeResult:
    """Fill gaps in the journal-derived orders from the Market.json snapshot."""
    # Market.json snapshot merge
    # --------------------------------
    # CarrierTradeOrder journal lines are not always emitted as a full snapshot;
    # sometimes they are deltas (e.g. you change ONE buy order and only that
    # commodity is written). If we treat those deltas as authoritative, the UI
    # can incorrectly "delete" other existing orders.
    #
    # Market.json is a snapshot and is typically updated when the carrier market
    # changes, so we merge it in to fill any missing commodities.
    #
    snap: MarketExportSnapshot | None = None

    # trade_orders_scope is assigned only the three values tested here, so this
    # guard is exhaustive; the false arc is excluded from branch coverage.
    if trade_orders_scope in ("none", "stale", "since_docked"):  # pragma: no branch
        try:
            # Prefer the directory passed by the API layer so unit tests can
            # control Market.json inputs deterministically.
            if journal_dir is None:
                from ..utils.journal import get_journal_directory  # local import

                resolved = get_journal_directory()
            else:
                resolved = journal_dir

            snap = load_market_export(resolved)
        except Exception:  # noqa: BLE001
            # Deliberately broad. Resolving the journal directory reads
            # user configuration and the export read parses a file the game
            # owns. The Market.json merge below is an enrichment: without a
            # snapshot the response falls back to the journal trade orders,
            # which is the documented behaviour rather than a degraded one.
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
    return MarketMergeResult(
        cargo=cargo,
        buy_orders=buy_orders,
        sell_orders=sell_orders,
        snapshot_time=snapshot_time,
        trade_orders_scope=trade_orders_scope,
        market_snapshot=snap,
    )


def derive_space_usage(stats: CarrierStatsEvent | None) -> SpaceUsageMetrics:
    """Derive cargo and capacity tonnages from CarrierStats.SpaceUsage."""
    # Derive cargo and capacity metrics from CarrierStats.SpaceUsage when present.
    total_cargo_tonnage: int | None = None
    total_capacity_tonnage: int | None = None
    free_space_tonnage: int | None = None
    space_usage_model: CarrierSpaceUsage | None = None

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
                total_cargo_tonnage = round(cargo_tonnage)
            if isinstance(total_capacity, (int, float)):
                total_capacity_tonnage = round(total_capacity)
            if isinstance(free_space, (int, float)):
                free_space_tonnage = round(free_space)

            def _as_int(val: object) -> int | None:
                if isinstance(val, int):
                    return val
                if isinstance(val, float):
                    return round(val)
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
        except Exception:
            # Deliberately broad. raw_data is the untouched CarrierStats
            # payload, so this arithmetic walks keys the game may rename or
            # omit between updates. Leaving the metrics unset renders as
            # 'unknown' in the UI, which is honest; a raised exception here
            # would lose the carrier identity as well.
            logger.warning(
                "Failed to derive cargo/capacity metrics from CarrierStats",
                exc_info=True,
            )
    return SpaceUsageMetrics(
        total_cargo_tonnage=total_cargo_tonnage,
        total_capacity_tonnage=total_capacity_tonnage,
        free_space_tonnage=free_space_tonnage,
        space_usage=space_usage_model,
    )
