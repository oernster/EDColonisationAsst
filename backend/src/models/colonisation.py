"""Colonisation-specific data models"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, computed_field


class CommodityStatus(str, Enum):
    """Status of a commodity requirement"""

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    NOT_STARTED = "not_started"


class DataSource(str, Enum):
    """Source of the colonisation data"""

    JOURNAL = "journal"
    INARA = "inara"


class Commodity(BaseModel):
    """Represents a commodity requirement for construction"""

    name: str = Field(description="Internal commodity name")
    name_localised: str = Field(description="Localized commodity name")
    required_amount: int = Field(ge=0, description="Total amount required")
    provided_amount: int = Field(ge=0, description="Amount already provided")
    payment: int = Field(ge=0, description="Payment per unit in credits")

    @computed_field
    @property
    def remaining_amount(self) -> int:
        """Calculate remaining amount needed"""
        return max(0, self.required_amount - self.provided_amount)

    @computed_field
    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.required_amount == 0:
            return 100.0
        return (self.provided_amount / self.required_amount) * 100.0

    @computed_field
    @property
    def status(self) -> CommodityStatus:
        """Determine commodity status"""
        if self.provided_amount >= self.required_amount:
            return CommodityStatus.COMPLETED
        elif self.provided_amount > 0:
            return CommodityStatus.IN_PROGRESS
        return CommodityStatus.NOT_STARTED


class ConstructionSite(BaseModel):
    """Represents a construction site (depot)"""

    market_id: int = Field(description="Unique market ID")
    station_name: str = Field(description="Station/depot name")
    station_type: str = Field(description="Type of station")
    system_name: str = Field(description="Star system name")
    system_address: int = Field(description="System address")
    construction_progress: float = Field(
        ge=0.0, le=100.0, description="Overall construction progress"
    )
    construction_complete: bool = Field(description="Whether construction is complete")
    construction_failed: bool = Field(description="Whether construction has failed")
    commodities: list[Commodity] = Field(
        default_factory=list, description="Required commodities"
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )
    last_source: DataSource = Field(
        default=DataSource.JOURNAL, description="Source of the last update"
    )

    @computed_field
    @property
    def is_complete(self) -> bool:
        """Check if construction is complete"""
        return self.construction_complete

    @computed_field
    @property
    def total_commodities_needed(self) -> int:
        """Calculate total commodities still needed"""
        return sum(c.remaining_amount for c in self.commodities)

    @computed_field
    @property
    def commodities_progress_percentage(self) -> float:
        """Calculate overall commodity progress"""
        if not self.commodities:
            return 100.0

        total_required = sum(c.required_amount for c in self.commodities)
        if total_required == 0:
            return 100.0

        total_provided = sum(c.provided_amount for c in self.commodities)
        return (total_provided / total_required) * 100.0


class SystemColonisationData(BaseModel):
    """Aggregated colonisation data for a system"""

    system_name: str = Field(description="Star system name")
    construction_sites: list[ConstructionSite] = Field(
        default_factory=list, description="All construction sites in the system"
    )

    @computed_field
    @property
    def total_sites(self) -> int:
        """Total number of construction sites"""
        return len(self.construction_sites)

    @computed_field
    @property
    def completed_sites(self) -> int:
        """Number of completed sites"""
        return sum(1 for site in self.construction_sites if site.is_complete)

    @computed_field
    @property
    def in_progress_sites(self) -> int:
        """Number of in-progress sites"""
        return sum(1 for site in self.construction_sites if not site.is_complete)

    @computed_field
    @property
    def completion_percentage(self) -> float:
        """Overall system completion percentage"""
        if self.total_sites == 0:
            return 0.0
        return (self.completed_sites / self.total_sites) * 100.0


class CommodityAggregate(BaseModel):
    """Aggregated commodity data across multiple sites"""

    commodity_name: str = Field(description="Internal commodity name")
    commodity_name_localised: str = Field(description="Localized commodity name")
    total_required: int = Field(
        ge=0, description="Total amount required across all sites"
    )
    total_provided: int = Field(
        ge=0, description="Total amount provided across all sites"
    )
    sites_requiring: list[str] = Field(
        default_factory=list,
        description="List of station names requiring this commodity",
    )
    average_payment: float = Field(ge=0.0, description="Average payment per unit")

    @computed_field
    @property
    def total_remaining(self) -> int:
        """Calculate total remaining amount"""
        return max(0, self.total_required - self.total_provided)

    @computed_field
    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.total_required == 0:
            return 100.0
        return (self.total_provided / self.total_required) * 100.0
