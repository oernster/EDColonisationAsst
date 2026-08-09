"""API routes for Elite: Dangerous player journal"""

from fastapi import APIRouter, HTTPException

from ..models.journal_events import (
    CommanderEvent,
    DockedEvent,
    FSDJumpEvent,
    LocationEvent,
)
from ..services.journal_parser import JournalParser
from ..utils.journal import get_journal_directory, get_latest_journal_file
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/journal", tags=["journal"])
logger = get_logger(__name__)


@router.get("/status")
async def get_journal_status():
    """Get the latest journal status: the current system and the commander.

    Both are read from the newest journal file on demand. Every game session
    opens its journal with a `Commander` event, so the commander's name comes
    from the same file that answers where they are; no stored setting needed.
    """
    try:
        journal_dir = get_journal_directory()
        latest_file = get_latest_journal_file(journal_dir)

        if not latest_file:
            return {
                "current_system": None,
                "commander_name": None,
                "message": "No journal files found.",
            }

        parser = JournalParser()
        events = parser.parse_file(latest_file)

        # Walk backwards so the newest reading of each wins: the latest
        # location, FSD jump or docked event names the current system, and the
        # latest Commander event names who is playing.
        current_system = None
        commander_name = None
        for event in reversed(events):
            if current_system is None and isinstance(
                event, (LocationEvent, FSDJumpEvent, DockedEvent)
            ):
                current_system = event.star_system
            if commander_name is None and isinstance(event, CommanderEvent):
                commander_name = event.name
            if current_system is not None and commander_name is not None:
                break

        return {"current_system": current_system, "commander_name": commander_name}

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
