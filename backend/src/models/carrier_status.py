"""The carrier's own systems: fuel, finance and crew.

Split from carriers.py rather than added to it, on two counts. The file was
close enough to the module cap that this would have pushed it over, and these
models answer a different question from the ones there: carriers.py describes
what a carrier *is* and what it is carrying, while this describes how it is
running.

Every field is optional. The journal has changed shape across years of game
updates, and a carrier the commander has merely seen rather than owns yields a
CarrierStats event with far less in it than their own, so a missing number
means "not reported" and never zero.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CarrierFinance(BaseModel):
    """The carrier's balances and the tax it charges."""

    carrier_balance: int | None = Field(
        default=None,
        description="Total credits held by the carrier.",
    )
    reserve_balance: int | None = Field(
        default=None,
        description="Credits set aside to cover upkeep.",
    )
    available_balance: int | None = Field(
        default=None,
        description=(
            "Credits free to spend, which is the balance less the reserve and "
            "any outstanding commitments."
        ),
    )
    reserve_percent: int | None = Field(
        default=None,
        description="Share of income diverted into the reserve, as a percentage.",
    )
    tax_rate_rearm: int | None = Field(
        default=None,
        description="Percentage the carrier adds to restock, when that service runs.",
    )
    tax_rate_refuel: int | None = Field(
        default=None,
        description="Percentage the carrier adds to refuel, when that service runs.",
    )
    tax_rate_repair: int | None = Field(
        default=None,
        description="Percentage the carrier adds to repair, when that service runs.",
    )


class CarrierCrewMember(BaseModel):
    """One crew position aboard the carrier.

    A position exists whether or not it has been hired, which is what
    `activated` says. `enabled` is a second, narrower question: a hired
    service can still be switched off, and only the journal for an activated
    role reports it.
    """

    role: str = Field(
        description="The service this position runs, as the journal names it."
    )
    activated: bool = Field(
        default=False,
        description="Whether the position has been hired at all.",
    )
    enabled: bool | None = Field(
        default=None,
        description=(
            "Whether an activated service is currently switched on. None when "
            "the position was never activated, which the journal leaves silent."
        ),
    )
    name: str | None = Field(
        default=None,
        description="The crew member's name, reported only once hired.",
    )


class CarrierStatus(BaseModel):
    """How the carrier is running, as opposed to what it is carrying."""

    fuel_level: int | None = Field(
        default=None,
        description="Tritium in the carrier's own fuel tank, in tonnes.",
    )
    jump_range_current: float | None = Field(
        default=None,
        description=(
            "How far the carrier can jump right now, in light years. Falls "
            "below the maximum as the tank empties or the load grows."
        ),
    )
    jump_range_max: float | None = Field(
        default=None,
        description="The carrier's best possible jump, in light years.",
    )
    pending_decommission: bool = Field(
        default=False,
        description=(
            "Whether the carrier is scheduled to be scrapped. True is worth "
            "shouting about, since it ends with the carrier and its cargo gone."
        ),
    )
    finance: CarrierFinance | None = Field(
        default=None,
        description="Balances and tax rates, when the journal reported them.",
    )
    crew: list[CarrierCrewMember] = Field(
        default_factory=list,
        description="Every crew position, hired or not, in the journal's order.",
    )
