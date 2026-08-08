"""Fleet carrier domain models.

These models represent a *derived* view of carrier state built from the
Elite Dangerous journal. They are intentionally narrow and focused on
what the Fleet carriers UI needs: identity, cargo snapshot and
buy/sell orders.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CarrierRole(str, Enum):
    """Role of a carrier relative to the current commander."""

    OWN = "own"
    SQUADRON = "squadron"
    OTHER = "other"


class CarrierTransitState(str, Enum):
    """Where a carrier is, as opposed to where it was last seen.

    A carrier is never docked: it is holding station in a star system or it
    is between two of them. A cancelled jump is not a third state, it simply
    returns the carrier to PARKED.
    """

    PARKED = "parked"
    IN_TRANSIT = "in_transit"


class CarrierTransit(BaseModel):
    """A carrier's movement state derived from its jump events."""

    state: CarrierTransitState = Field(
        description="Whether the carrier is holding station or between systems."
    )
    destination_system: str | None = Field(
        default=None,
        description=("Star system the carrier is jumping to. None when it is parked."),
    )
    destination_body: str | None = Field(
        default=None,
        description=(
            "Body the carrier will hold at on arrival, when the journal named one."
        ),
    )
    departure_time: datetime | None = Field(
        default=None,
        description=(
            "When the carrier leaves, which is what a countdown runs against. "
            "None when the journal did not carry one."
        ),
    )


class CarrierIdentity(BaseModel):
    """High-level identity of a fleet carrier."""

    carrier_id: int | None = Field(
        default=None,
        description="Unique carrier ID if known (from CarrierID or equivalent).",
    )
    market_id: int | None = Field(
        default=None,
        description="Market ID associated with the carrier, if available.",
    )
    name: str = Field(description="Carrier name as shown in the HUD.")
    callsign: str | None = Field(
        default=None,
        description="Carrier callsign (e.g. ABC-123), if available from the journal.",
    )
    role: CarrierRole = Field(
        default=CarrierRole.OTHER,
        description=(
            "Relationship of this carrier to the current commander: "
            "'own', 'squadron' or 'other'."
        ),
    )
    docking_access: str | None = Field(
        default=None,
        description=(
            "Docking access policy for the carrier (e.g. 'owner', 'squadron', "
            "'friends', 'all'), when available from CarrierStats."
        ),
    )
    last_seen_system: str | None = Field(
        default=None,
        description=(
            "Last known star system where this carrier was seen in the journals."
        ),
    )
    last_seen_timestamp: datetime | None = Field(
        default=None,
        description="Timestamp of the last journal event involving this carrier.",
    )
    services: list[str] | None = Field(
        default=None,
        description=(
            "Normalised list of services available on the carrier, derived from "
            "CarrierStats.Crew (activated crew roles) and StationServices on the "
            "Docked/CarrierStats events (e.g. exploration, outfitting, "
            "pioneersupplies, vistagenomics, bartender)."
        ),
    )
    transit: CarrierTransit | None = Field(
        default=None,
        description=(
            "Whether the carrier is holding station or jumping, derived from its "
            "CarrierJumpRequest, CarrierJumpCancelled and CarrierLocation events. "
            "None when the journals carry no jump history for it at all."
        ),
    )


class CarrierCargoItem(BaseModel):
    """Commodity-level view of carrier cargo."""

    commodity_name: str = Field(description="Internal commodity name.")
    commodity_name_localised: str = Field(
        description="Localized commodity name for display."
    )
    stock: int = Field(
        ge=0,
        description=(
            "Current stock on the carrier related to this commodity. "
            "Derived from journal events such as CarrierTradeOrder."
        ),
    )
    reserved: int | None = Field(
        default=None,
        description=(
            "Units reserved for active orders (if known). Not all journal "
            "events expose this explicitly."
        ),
    )
    capacity: int | None = Field(
        default=None,
        description=(
            "Maximum capacity for this commodity on the carrier, if known. "
            "If the journal does not expose per-commodity capacity this "
            "field will be None."
        ),
    )


class CarrierOrderType(str, Enum):
    """Type of carrier trade order."""

    BUY = "buy"
    SELL = "sell"


class CarrierOrder(BaseModel):
    """Buy or sell order configured on a carrier."""

    order_type: CarrierOrderType = Field(
        description="Whether this is a buy or sell order."
    )
    commodity_name: str = Field(description="Internal commodity name.")
    commodity_name_localised: str = Field(
        description="Localized commodity name for display."
    )
    price: int = Field(ge=0, description="Price per unit in credits.")
    original_amount: int = Field(
        ge=0,
        description=(
            "Original configured amount for the order (PurchaseOrder/SaleOrder)."
        ),
    )
    remaining_amount: int = Field(
        ge=0,
        description=(
            "Remaining amount to be fulfilled for this order. Typically mapped "
            "from the journal 'Outstanding' field."
        ),
    )
    stock: int | None = Field(
        default=None,
        description=(
            "Current stock related to this order, if reported separately in the "
            "journal (Stock field). This is used when deriving cargo snapshots."
        ),
    )


class CarrierSpaceUsage(BaseModel):
    """Raw CarrierStats.SpaceUsage breakdown, when present in the journal."""

    total_capacity: int | None = Field(
        default=None,
        description="Nominal total carrier cargo capacity in tonnes (usually 25,000).",
    )
    crew: int | None = Field(
        default=None,
        description="Tonnes consumed by crew/services.",
    )
    module_packs: int | None = Field(
        default=None,
        description="Tonnes consumed by installed module packs.",
    )
    cargo: int | None = Field(
        default=None,
        description="Tonnes currently occupied by cargo.",
    )
    cargo_space_reserved: int | None = Field(
        default=None,
        description="Tonnes reserved (typically outstanding buy orders).",
    )
    free_space: int | None = Field(
        default=None,
        description="Tonnes of free space remaining.",
    )


class CarrierState(BaseModel):
    """Current reconstructed state of a single carrier."""

    identity: CarrierIdentity = Field(description="Carrier identity.")
    cargo: list[CarrierCargoItem] = Field(
        default_factory=list,
        description=(
            "Per-commodity carrier hold, largest tonnage first. Anchored on the "
            "Market.json Stock column, which is the carrier's real hold rather "
            "than only what is listed for sale, then carried forward by the "
            "commander's own market transactions against the carrier. Falls back "
            "to CarrierTradeOrder SELL stock when no export is available."
        ),
    )
    cargo_snapshot_time: datetime | None = Field(
        default=None,
        description=(
            "When the Market.json export the hold is anchored on was written. "
            "The game rewrites it on docking and opening the carrier's commodity "
            "market, so this is how old the per-commodity view is. None when the "
            "hold came from trade orders rather than an export."
        ),
    )
    cargo_unaccounted_tonnage: int | None = Field(
        default=None,
        description=(
            "CarrierStats.SpaceUsage.Cargo minus the summed per-commodity hold. "
            "Zero means the snapshot still agrees with the carrier's own total. "
            "Anything else is tonnage that moved by a route the commander's "
            "journal does not record, so the breakdown is that far out of date. "
            "None when no total is available to check against."
        ),
    )
    total_cargo_tonnage: int | None = Field(
        default=None,
        description=(
            "Total cargo tonnage in the carrier hold, taken from CarrierStats."
            "SpaceUsage.Cargo when available. This may exceed the sum of per-"
            "commodity market stock shown in 'cargo'."
        ),
    )
    total_capacity_tonnage: int | None = Field(
        default=None,
        description=(
            "Total carrier capacity in tonnes from "
            "CarrierStats.SpaceUsage.TotalCapacity "
            "when available."
        ),
    )
    free_space_tonnage: int | None = Field(
        default=None,
        description=(
            "Free cargo space in tonnes from CarrierStats.SpaceUsage.FreeSpace when "
            "available. Together with total_cargo_tonnage this approximates the total "
            "cargo capacity after accounting for installed services / loadouts."
        ),
    )

    space_usage: CarrierSpaceUsage | None = Field(
        default=None,
        description=(
            "CarrierStats.SpaceUsage breakdown when available "
            "(TotalCapacity, Crew, ModulePacks, "
            "Cargo, CargoSpaceReserved, FreeSpace)."
        ),
    )
    buy_orders: list[CarrierOrder] = Field(
        default_factory=list, description="Active buy orders on the carrier."
    )
    sell_orders: list[CarrierOrder] = Field(
        default_factory=list, description="Active sell orders on the carrier."
    )

    trade_orders_scope: str | None = Field(
        default=None,
        description=(
            "Indicates which journal window was used to derive buy/sell orders. "
            "Values: 'since_docked' (preferred), 'recent_history' (fallback when no "
            "orders were observed since the latest Docked event), 'stale' "
            "(trade orders exist "
            "but are too old to trust), 'market_export' (Market.json "
            "snapshot) or 'none'."
        ),
    )
    snapshot_time: datetime = Field(
        description="Timestamp of the latest journal event used to build this state."
    )
