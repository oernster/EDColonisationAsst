"""The health endpoint, and what it says about startup.

Split out of routes.py, which had grown into the module limit's danger band
while holding two unrelated things: the colonisation resources, and the
liveness check the packaged runtime polls before it opens a browser.

Health is worth its own module for a second reason. It is the only endpoint
with a caller that is not the web UI: the startup splash polls it every half
second while the backend is still coming up, and now reads how far the
journal import has got from the same response, so that the splash can show a
real bar rather than a barber pole.
"""

from __future__ import annotations

from pathlib import Path
import platform

from fastapi import APIRouter

from ..config import get_config
from ..models.api_models import HealthResponse, StartupProgressResponse
from ..services.startup_progress import (
    startup_explanation,
    startup_progress,
    startup_progress_message,
)

router = APIRouter(prefix="/api", tags=["health"])


def _startup_progress_response() -> StartupProgressResponse:
    """Read the startup tracker into its wire shape.

    The wording is decided in the service rather than here, so that what the
    splash says stays inside the coverage gate: backend/src/runtime is not.
    """
    snapshot = startup_progress.snapshot()
    return StartupProgressResponse(
        stage=snapshot.stage.value,
        files_done=snapshot.files_done,
        files_total=snapshot.files_total,
        bytes_done=snapshot.bytes_done,
        bytes_total=snapshot.bytes_total,
        percent=snapshot.percent,
        message=startup_progress_message(snapshot),
        explanation=startup_explanation(snapshot),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint"""
    config = get_config()
    journal_dir = Path(config.journal.directory)

    from .. import __build_id__, __version__

    return HealthResponse(
        status="healthy",
        version=__version__,
        build_id=__build_id__ or "",
        python_version=platform.python_version(),
        journal_directory=str(journal_dir),
        journal_accessible=journal_dir.exists(),
        startup=_startup_progress_response(),
    )


__all__ = ["health_check", "router"]
