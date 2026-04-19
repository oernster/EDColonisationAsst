"""REST API routes"""

from pathlib import Path
import platform
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import get_config
from ..models.api_models import (
    SystemResponse,
    SiteResponse,
    SiteListResponse,
    SystemListResponse,
    CommodityAggregateResponse,
    ErrorResponse,
    HealthResponse,
)
from ..repositories.colonisation_repository import IColonisationRepository
from ..services.data_aggregator import IDataAggregator
from ..services.system_tracker import ISystemTracker
from ..utils.logger import get_logger
from ..services.change_bus import change_bus

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["colonisation"])


# Dependency injection - these will be set by main.py
_repository: Optional[IColonisationRepository] = None
_aggregator: Optional[IDataAggregator] = None
_system_tracker: Optional[ISystemTracker] = None


def set_dependencies(
    repository: IColonisationRepository,
    aggregator: IDataAggregator,
    system_tracker: ISystemTracker,
) -> None:
    """Set dependencies for the API routes"""
    global _repository, _aggregator, _system_tracker
    _repository = repository
    _aggregator = aggregator
    _system_tracker = system_tracker


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint"""
    config = get_config()
    journal_dir = Path(config.journal.directory)

    from .. import __version__, __build_id__

    return HealthResponse(
        status="healthy",
        version=__version__,
        build_id=__build_id__ or "",
        python_version=platform.python_version(),
        journal_directory=str(journal_dir),
        journal_accessible=journal_dir.exists(),
    )


@router.get("/watcher/status", response_model=dict)
async def get_watcher_status() -> dict:
    """Return a small diagnostic snapshot for the journal watcher.

    This endpoint is intended for UI self-diagnostics in the packaged runtime.
    """
    config = get_config()
    journal_dir = Path(config.journal.directory)

    try:
        # Import locally to avoid cycles in test imports.
        from ..main import app as fastapi_app

        watcher = getattr(fastapi_app.state, "file_watcher", None)
    except Exception:
        watcher = None

    running = bool(getattr(watcher, "is_running", lambda: False)()) if watcher else False
    watched = str(getattr(watcher, "watched_directory", lambda: None)() or "") if watcher else ""
    watchdog_status = (
        getattr(watcher, "watchdog_status", lambda: {"configured": False, "alive": False})()
        if watcher
        else {"configured": False, "alive": False}
    )
    poller_status = (
        getattr(watcher, "poller_status", lambda: {"running": False})() if watcher else {"running": False}
    )

    handler = getattr(watcher, "_handler", None) if watcher else None  # noqa: SLF001

    handler_diag = None
    if handler is not None:
        handler_diag = {
            "last_watchdog_event_at": getattr(handler, "last_watchdog_event_at", None),
            "last_watchdog_event_type": getattr(handler, "last_watchdog_event_type", None),
            "last_watchdog_event_path": getattr(handler, "last_watchdog_event_path", None),
            "last_processed_at": getattr(handler, "last_processed_at", None),
            "last_processed_file": getattr(handler, "last_processed_file", None),
            "last_error": getattr(handler, "last_error", None),
            "last_events_parsed": getattr(handler, "last_events_parsed", None),
            "last_updated_systems": getattr(handler, "last_updated_systems", None),
            "last_depot_market_ids": getattr(handler, "last_depot_market_ids", None),
        }

    return {
        "configured_journal_directory": str(journal_dir),
        "configured_directory_exists": journal_dir.exists(),
        "watcher_running": running,
        "watcher_directory": watched or None,
        "watchdog": watchdog_status,
        "poller": poller_status,
        "handler": handler_diag,
    }


@router.get("/systems", response_model=SystemListResponse)
async def get_systems() -> SystemListResponse:
    """Get list of all systems with construction sites"""
    if _repository is None:
        raise HTTPException(status_code=500, detail="Repository not initialized")

    systems = await _repository.get_all_systems()
    return SystemListResponse(systems=systems)


@router.get("/systems/search", response_model=SystemListResponse)
async def search_systems(
    q: str = Query(..., min_length=1, description="Search query")
) -> SystemListResponse:
    """Search for systems by name (autocomplete)"""
    if _repository is None:
        raise HTTPException(status_code=500, detail="Repository not initialized")

    all_systems = await _repository.get_all_systems()

    # Simple case-insensitive substring search
    query_lower = q.lower()
    matching_systems = [
        system for system in all_systems if query_lower in system.lower()
    ]

    return SystemListResponse(systems=matching_systems)


@router.get("/systems/current", response_model=dict)
async def get_current_system() -> dict:
    """Get the player's current system"""
    if _system_tracker is None:
        raise HTTPException(status_code=500, detail="System tracker not initialized")

    current_system = _system_tracker.get_current_system()
    current_station = _system_tracker.get_current_station()
    is_docked = _system_tracker.is_docked()

    return {
        "system_name": current_system,
        "station_name": current_station,
        "is_docked": is_docked,
    }


@router.get("/system", response_model=SystemResponse)
async def get_system_data(
    name: str = Query(..., description="System name")
) -> SystemResponse:
    """Get colonisation data for a specific system"""
    if _aggregator is None:
        raise HTTPException(status_code=500, detail="Aggregator not initialized")

    system_data = await _aggregator.aggregate_by_system(name)

    if system_data.total_sites == 0:
        raise HTTPException(
            status_code=404, detail=f"No construction sites found in system: {name}"
        )

    return SystemResponse(
        system_name=system_data.system_name,
        construction_sites=system_data.construction_sites,
        total_sites=system_data.total_sites,
        completed_sites=system_data.completed_sites,
        in_progress_sites=system_data.in_progress_sites,
        completion_percentage=system_data.completion_percentage,
    )


@router.get("/system/commodities", response_model=CommodityAggregateResponse)
async def get_system_commodities(
    name: str = Query(..., description="System name")
) -> CommodityAggregateResponse:
    """Get aggregated commodity data for a system"""
    if _aggregator is None:
        raise HTTPException(status_code=500, detail="Aggregator not initialized")

    system_data = await _aggregator.aggregate_by_system(name)

    if system_data.total_sites == 0:
        raise HTTPException(
            status_code=404, detail=f"No construction sites found in system: {name}"
        )

    commodities = await _aggregator.aggregate_commodities(
        system_data.construction_sites
    )

    return CommodityAggregateResponse(commodities=commodities)


@router.get("/sites/{market_id}", response_model=SiteResponse)
async def get_site(market_id: int) -> SiteResponse:
    """Get specific construction site by market ID"""
    if _repository is None:
        raise HTTPException(status_code=500, detail="Repository not initialized")

    site = await _repository.get_site_by_market_id(market_id)

    if site is None:
        raise HTTPException(
            status_code=404, detail=f"Construction site not found: {market_id}"
        )

    return SiteResponse(site=site)


@router.get("/sites", response_model=SiteListResponse)
async def get_all_sites() -> SiteListResponse:
    """Get all construction sites, categorized by status, aggregated from all sources."""
    if _repository is None or _aggregator is None:
        raise HTTPException(status_code=500, detail="Dependencies not initialized")

    all_systems = await _repository.get_all_systems()
    all_sites = []

    for system_name in all_systems:
        system_data = await _aggregator.aggregate_by_system(system_name)
        all_sites.extend(system_data.construction_sites)

    in_progress = [site for site in all_sites if not site.is_complete]
    completed = [site for site in all_sites if site.is_complete]

    return SiteListResponse(in_progress_sites=in_progress, completed_sites=completed)


@router.get("/stats", response_model=dict)
async def get_stats() -> dict:
    """Get overall statistics"""
    if _repository is None:
        raise HTTPException(status_code=500, detail="Repository not initialized")

    stats = await _repository.get_stats()

    return stats


@router.post("/debug/reload-journals", response_model=dict)
async def reload_journals() -> dict:
    """Debug endpoint to manually reload journal files.

    This now reuses the same parsing/processing pipeline as the live
    FileWatcher so that:
      - Location / FSDJump / Docked events update the SystemTracker
      - Docked-at-construction-site events create sites with correct
        system/station metadata
      - ColonisationConstructionDepot snapshots update those sites
        instead of creating 'Unknown System' records.
    """
    from pathlib import Path
    from ..services.journal_parser import JournalParser
    from ..config import get_config

    if _repository is None:
        raise HTTPException(status_code=500, detail="Repository not initialized")

    # Clear existing data before reloading
    await _repository.clear_all()

    config = get_config()
    journal_dir = Path(config.journal.directory)

    if not journal_dir.exists():
        raise HTTPException(
            status_code=404, detail=f"Journal directory not found: {journal_dir}"
        )

    parser = JournalParser()
    processed_files: list[str] = []
    total_events = 0

    # Import here to avoid circulars at module import time
    from ..services.file_watcher import JournalFileHandler
    from ..services.system_tracker import SystemTracker
    from ..models.journal_events import ColonisationConstructionDepotEvent

    # Use a single tracker/handler so system context is preserved across files
    tracker = SystemTracker()
    handler = JournalFileHandler(parser, tracker, _repository, None)

    # Find all journal files
    journal_files = sorted(
        journal_dir.glob("Journal.*.log"),
        key=lambda p: p.stat().st_mtime,
    )

    # Process all files
    for journal_file in journal_files:
        # Let the handler parse and process all relevant events
        await handler._process_file(journal_file)

        # For simple stats, count colonisation depot events in this file
        events = parser.parse_file(journal_file)
        file_events = [
            e for e in events if isinstance(e, ColonisationConstructionDepotEvent)
        ]
        if file_events:
            processed_files.append(journal_file.name)
            total_events += len(file_events)

    # Notify UI clients (AJAX long-poll) that data changed.
    try:
        await change_bus.bump()
    except Exception:
        pass

    return {
        "processed_files": processed_files,
        "total_events": total_events,
        "journal_directory": str(journal_dir),
    }
