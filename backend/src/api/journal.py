"""API routes for Elite: Dangerous player journal"""

from fastapi import APIRouter, HTTPException

from ..models.journal_events import DockedEvent, FSDJumpEvent, LocationEvent
from ..services.journal_parser import JournalParser
from ..utils.journal import get_journal_directory, get_latest_journal_file
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/journal", tags=["journal"])
logger = get_logger(__name__)


@router.get("/status")
async def get_journal_status():
    """Get the latest journal status, including the current system."""
    try:
        journal_dir = get_journal_directory()
        latest_file = get_latest_journal_file(journal_dir)

        if not latest_file:
            return {"current_system": None, "message": "No journal files found."}

        parser = JournalParser()
        events = parser.parse_file(latest_file)

        # Find the latest location, FSD jump or docked event to determine
        # the current system
        current_system = None
        for event in reversed(events):
            if isinstance(event, (LocationEvent, FSDJumpEvent, DockedEvent)):
                current_system = event.star_system
                break

        return {"current_system": current_system}

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        # Deliberately broad; correct at an HTTP boundary, because everything
        # not already an HTTPException is by definition unanticipated, so
        # the client must get a 500 rather than a stack trace. The detail is
        # deliberately generic so nothing internal leaks into the response;
        # the real error goes to the log.
        logger.error(f"Error getting journal status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
