"""Journal event data models"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JournalEvent(BaseModel):
    """Base class for all journal events"""

    timestamp: datetime = Field(description="Event timestamp")
    event: str = Field(description="Event type")
    raw_data: dict[str, Any] = Field(default_factory=dict, description="Raw event data")


class ColonisationConstructionDepotEvent(JournalEvent):
    """ColonisationConstructionDepot event - construction site status"""

    market_id: int = Field(description="Market ID")
    station_name: str = Field(description="Station name")
    station_type: str = Field(description="Station type")
    system_name: str = Field(description="System name")
    system_address: int = Field(description="System address")
    construction_progress: float = Field(description="Construction progress percentage")
    construction_complete: bool = Field(
        default=False, description="Construction complete flag"
    )
    construction_failed: bool = Field(
        default=False, description="Construction failed flag"
    )
    commodities: list[dict[str, Any]] = Field(
        default_factory=list, description="List of required commodities"
    )


class ColonisationContributionEvent(JournalEvent):
    """ColonisationContribution event - player contribution"""

    market_id: int = Field(description="Market ID")
    commodity: str = Field(description="Commodity name")
    commodity_localised: str | None = Field(
        None, description="Localized commodity name"
    )
    quantity: int = Field(description="Quantity contributed")
    total_quantity: int = Field(description="Total quantity now provided")
    credits_received: int = Field(description="Credits received for contribution")


class LocationEvent(JournalEvent):
    """Location event - current location"""

    star_system: str = Field(description="Star system name")
    system_address: int = Field(description="System address")
    star_pos: list[float] = Field(
        default_factory=list, description="Star position coordinates"
    )
    station_name: str | None = Field(None, description="Station name if docked")
    station_type: str | None = Field(None, description="Station type if docked")
    market_id: int | None = Field(None, description="Market ID if docked")
    docked: bool = Field(default=False, description="Whether docked at station")


class FSDJumpEvent(JournalEvent):
    """FSDJump event - hyperspace jump"""

    star_system: str = Field(description="Destination star system")
    system_address: int = Field(description="System address")
    star_pos: list[float] = Field(
        default_factory=list, description="Star position coordinates"
    )
    jump_dist: float = Field(description="Jump distance in light years")
    fuel_used: float = Field(description="Fuel used")
    fuel_level: float = Field(description="Remaining fuel level")


class DockedEvent(JournalEvent):
    """Docked event - docking at station"""

    station_name: str = Field(description="Station name")
    station_type: str = Field(description="Station type")
    star_system: str = Field(description="Star system name")
    system_address: int = Field(description="System address")
    market_id: int = Field(description="Market ID")
    station_faction: dict[str, Any] = Field(description="Station faction info")
    station_government: str = Field(description="Station government type")
    station_economy: str = Field(description="Station economy type")
    station_economies: list[dict[str, Any]] = Field(description="Station economies")


class UndockedEvent(JournalEvent):
    """Undocked event - leaving a station or a carrier's pad.

    Only the fact of it matters here. Whatever the commander was docked at,
    this ends it, which is what stops a carrier reporting the commander as
    still aboard hours after they left.
    """

    station_name: str | None = Field(default=None, description="Station departed")
    station_type: str | None = Field(default=None, description="Station type departed")
    market_id: int | None = Field(default=None, description="Market ID departed")


class CommanderEvent(JournalEvent):
    """Commander event - commander information"""

    name: str = Field(description="Commander name")
    fid: str = Field(description="Frontier ID")


class LoadGameEvent(JournalEvent):
    """LoadGame event - the session as it begins.

    Carries the credit balance at the moment the game loaded. The journal
    records no running balance afterwards, so this is the freshest reading
    that exists and is presented as such.
    """

    commander: str | None = Field(default=None, description="Commander name")
    credits_balance: int | None = Field(
        default=None, description="Credit balance when the session loaded"
    )


class CarrierLocationEvent(JournalEvent):
    """CarrierLocation event - location of a fleet carrier."""

    carrier_id: int = Field(description="Unique carrier ID")
    star_system: str = Field(description="Star system name")
    system_address: int = Field(description="System address")


class CarrierStatsEvent(JournalEvent):
    """
    CarrierStats event - basic information about a fleet carrier owned by the commander.

    This event is primarily used to identify the commander's own carrier(s) and
    surface a human-friendly name and callsign for the Fleet carriers UI.
    """

    carrier_id: int = Field(description="Unique carrier ID")
    name: str = Field(description="Carrier name")
    callsign: str | None = Field(
        default=None, description="Carrier callsign (e.g. ABC-123)"
    )
    market_id: int | None = Field(
        default=None,
        description=(
            "Market ID for the carrier when available in the journal payload. "
            "Some environments may differ between CarrierID and MarketID; this "
            "field helps reconcile trade order association."
        ),
    )


class CarrierJumpRequestEvent(JournalEvent):
    """CarrierJumpRequest event - a jump booked to another star system.

    A carrier is never docked anywhere: it sits in a star system or it is
    between them. This event opens the second case. The carrier stays put
    until DepartureTime, which is roughly fifteen to twenty minutes out, so
    the pending window is long enough to be worth showing with a countdown.

    Arrival is not this event's business: it is a CarrierLocation for the
    same carrier at the requested SystemAddress. See carrier_transit.
    """

    carrier_id: int = Field(description="Unique carrier ID")
    system_name: str = Field(description="Destination star system name")
    system_address: int = Field(description="Destination system address")
    body: str | None = Field(
        default=None, description="Destination body the carrier will hold at"
    )
    departure_time: datetime | None = Field(
        default=None,
        description=(
            "When the carrier leaves. Absent in older journals, which costs "
            "the countdown but not the in-transit state itself."
        ),
    )


class CarrierJumpCancelledEvent(JournalEvent):
    """CarrierJumpCancelled event - a booked jump abandoned before departure.

    Carries nothing but the carrier id: which jump it cancels is decided by
    time order, since only the newest request can be outstanding.
    """

    carrier_id: int = Field(description="Unique carrier ID")


class CarrierTradeOrderEvent(JournalEvent):
    """
    CarrierTradeOrder event - buy or sell orders configured on a fleet carrier.

    NOTE: The Elite Dangerous journal schema for carriers includes several fields
    (PurchaseOrder, SaleOrder, Stock, Outstanding, Price, etc.). This model keeps
    the most relevant ones while still preserving the full raw_data.
    """

    carrier_id: int = Field(description="Unique carrier ID")
    commodity: str = Field(description="Commodity or material name")
    commodity_localised: str | None = Field(
        default=None, description="Localized commodity or material name"
    )
    purchase_order: int = Field(
        default=0,
        description=(
            "Total units the carrier intends to buy (PurchaseOrder, if present)"
        ),
    )
    sale_order: int = Field(
        default=0,
        description="Total units the carrier intends to sell (SaleOrder, if present)",
    )
    stock: int = Field(
        default=0,
        description="Current stock held on the carrier related to this order",
    )
    outstanding: int = Field(
        default=0,
        description="Remaining units to be fulfilled for this order (Outstanding)",
    )
    price: int = Field(default=0, description="Price per unit in credits")


class MarketTransactionEvent(JournalEvent):
    """
    MarketBuy or MarketSell - the commander trading commodities at a market.

    These matter to the carrier domain for one reason. Against the commander's
    own fleet carrier they are the only journal lines that move its hold, so
    they are what carries a Market.json snapshot forward between refreshes.
    Buying takes tonnage out of the carrier; selling puts tonnage in.

    Direction is a flag rather than the event name so that the hold derivation
    never has to know journal spellings.
    """

    market_id: int | None = Field(
        default=None, description="Market the transaction took place at"
    )
    commodity: str = Field(default="", description="Internal commodity name")
    commodity_localised: str | None = Field(
        default=None, description="Localized commodity name for display"
    )
    count: int = Field(default=0, ge=0, description="Tonnes traded")
    is_purchase: bool = Field(
        default=False,
        description="True when the commander bought, which removes carrier stock",
    )
