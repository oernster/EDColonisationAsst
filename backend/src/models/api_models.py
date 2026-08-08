"""API request and response models"""

from pydantic import BaseModel, Field

from .carriers import CarrierIdentity, CarrierState
from .colonisation import CommodityAggregate, ConstructionSite


class SystemResponse(BaseModel):
    """Response model for system colonisation data"""

    system_name: str = Field(description="Star system name")
    construction_sites: list[ConstructionSite] = Field(
        description="Construction sites in system"
    )
    total_sites: int = Field(description="Total number of sites")
    completed_sites: int = Field(description="Number of completed sites")
    in_progress_sites: int = Field(description="Number of in-progress sites")
    completion_percentage: float = Field(description="Overall completion percentage")


class SiteResponse(BaseModel):
    """Response model for a single construction site"""

    site: ConstructionSite = Field(description="Construction site data")


class SystemListResponse(BaseModel):
    """Response model for list of systems"""

    systems: list[str] = Field(description="List of system names with construction")


class SiteListResponse(BaseModel):
    """Response model for a list of construction sites, categorized by status."""

    in_progress_sites: list[ConstructionSite] = Field(
        description="List of sites currently under construction"
    )
    completed_sites: list[ConstructionSite] = Field(
        description="List of completed construction sites"
    )


class CommodityAggregateResponse(BaseModel):
    """Response model for aggregated commodity data"""

    commodities: list[CommodityAggregate] = Field(
        description="Aggregated commodity data"
    )


class ErrorResponse(BaseModel):
    """Error response model"""

    error: str = Field(description="Error message")
    detail: str | None = Field(None, description="Detailed error information")
    status_code: int = Field(description="HTTP status code")


class StartupProgressResponse(BaseModel):
    """How far backend startup has got, for the splash to draw.

    The splash already polls health to decide when to open the browser, so
    this rides along on the same request rather than adding an endpoint.
    """

    stage: str = Field(description="Coarse phase of startup, e.g. importing_journals")
    files_done: int = Field(default=0, description="Journal files read so far")
    files_total: int = Field(default=0, description="Journal files to read in total")
    bytes_done: int = Field(default=0, description="Bytes of journal read so far")
    bytes_total: int = Field(default=0, description="Bytes of journal to read")
    percent: int | None = Field(
        default=None,
        description=(
            "Completion by bytes, or null when no total is known yet. Bytes "
            "rather than files, because journal files vary hugely in size and "
            "counting files makes the bar lurch."
        ),
    )
    message: str | None = Field(
        default=None,
        description="Status line for this stage, or null to keep the current one.",
    )
    explanation: str | None = Field(
        default=None,
        description="Why this stage is slow, when there is a reason worth giving.",
    )


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="healthy", description="Service status")
    version: str = Field(description="Application version")
    build_id: str = Field(
        description="Build identifier (for diagnosing stale installs)"
    )
    python_version: str = Field(description="Python runtime version")
    journal_directory: str = Field(description="Configured journal directory")
    journal_accessible: bool = Field(
        description="Whether journal directory is accessible"
    )
    startup: StartupProgressResponse | None = Field(
        default=None,
        description="Startup progress, for the splash screen to report.",
    )


# WebSocket message models removed. Live updates now use AJAX long-polling.


class AppSettings(BaseModel):
    """Application settings model"""

    journal_directory: str
    inara_api_key: str | None
    inara_commander_name: str | None
    prefer_local_for_commander_systems: bool = Field(
        default=True,
        description=(
            "When true (default), prefer local journal data for systems where the "
            "current commander has construction sites and use Inara data primarily "
            "for other systems. When false, Inara data is preferred wherever it is "
            "available."
        ),
    )


class CurrentCarrierResponse(BaseModel):
    """Response model for the player's current carrier docking context."""

    docked_at_carrier: bool = Field(
        description="True if the commander is currently docked at a fleet carrier."
    )
    carrier: CarrierIdentity | None = Field(
        default=None,
        description=(
            "Identity of the carrier the commander is currently docked at, if any. "
            "When docked_at_carrier is False, this will be null."
        ),
    )


class CarrierStateResponse(BaseModel):
    """Response model for a reconstructed carrier state snapshot."""

    carrier: CarrierState | None = Field(
        default=None,
        description=(
            "Current reconstructed state of the carrier (cargo + orders). "
            "May be null if the carrier cannot be resolved from recent journals."
        ),
    )


class MyCarriersResponse(BaseModel):
    """Response model listing the commander's own and squadron carriers."""

    own_carriers: list[CarrierIdentity] = Field(
        default_factory=list,
        description="Fleet carriers owned by the current commander.",
    )
    squadron_carriers: list[CarrierIdentity] = Field(
        default_factory=list,
        description="Fleet carriers belonging to the commander's squadron.",
    )
