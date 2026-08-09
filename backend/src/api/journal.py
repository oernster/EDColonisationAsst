"""API routes for Elite: Dangerous player journal"""

from fastapi import APIRouter, HTTPException

from ..models.journal_events import (
    CommanderEvent,
    DockedEvent,
    FSDJumpEvent,
    JournalEvent,
    LoadGameEvent,
    LocationEvent,
    UndockedEvent,
)
from ..services.journal_parser import JournalParser
from ..utils.journal import get_journal_directory, get_latest_journal_file
from ..utils.logger import get_logger

router = APIRouter(prefix="/api/journal", tags=["journal"])
logger = get_logger(__name__)


_NO_JOURNAL_STATUS = {
    "current_system": None,
    "commander_name": None,
    "credits_balance": None,
    "is_docked": None,
    "station_name": None,
    "station_type": None,
}


def _derive_status(events: list[JournalEvent]) -> dict:
    """Reduce a journal's events to the commander's current status.

    Walks backwards so the newest reading of each fact wins: the latest
    location-style event names the current system, the latest Commander event
    names who is playing, the latest LoadGame carries the credit balance the
    session opened with and the newest of Docked/Undocked/FSDJump/Location
    settles whether they are docked and at what.
    """
    status = dict(_NO_JOURNAL_STATUS)
    docked_settled = False
    for event in reversed(events):
        if status["current_system"] is None and isinstance(
            event, (LocationEvent, FSDJumpEvent, DockedEvent)
        ):
            status["current_system"] = event.star_system
        if status["commander_name"] is None and isinstance(event, CommanderEvent):
            status["commander_name"] = event.name
        if status["credits_balance"] is None and isinstance(event, LoadGameEvent):
            status["credits_balance"] = event.credits_balance
        if not docked_settled:
            if isinstance(event, DockedEvent):
                docked_settled = True
                status["is_docked"] = True
                status["station_name"] = event.station_name
                status["station_type"] = event.station_type
            elif isinstance(event, (UndockedEvent, FSDJumpEvent)):
                docked_settled = True
                status["is_docked"] = False
            elif isinstance(event, LocationEvent):
                docked_settled = True
                status["is_docked"] = event.docked
                if event.docked:
                    status["station_name"] = event.station_name
                    status["station_type"] = event.station_type
    return status


@router.get("/status")
async def get_journal_status():
    """Get the latest journal status: where the commander is and who they are.

    Everything is read from the newest journal file on demand. Every game
    session opens its journal with `Commander` and `LoadGame` events, so the
    commander's name and credit balance come from the same file that answers
    where they are; no stored setting needed. The balance is the one the
    session loaded with, because the journal records no running balance.
    """
    try:
        journal_dir = get_journal_directory()
        latest_file = get_latest_journal_file(journal_dir)

        if not latest_file:
            return dict(_NO_JOURNAL_STATUS, message="No journal files found.")

        parser = JournalParser()
        events = parser.parse_file(latest_file)

        return _derive_status(events)

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
