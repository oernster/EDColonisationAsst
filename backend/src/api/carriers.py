"""API routes for Fleet carriers.

These endpoints expose a derived view of fleet carrier state to power the
Frontend Fleet carriers tab. Data is reconstructed on demand from the
latest Elite: Dangerous journal file; no additional persistence is used.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException

from ..models.api_models import (
    CarrierStateResponse,
    CurrentCarrierResponse,
    MyCarriersResponse,
)
from ..models.journal_events import JournalEvent
from ..services.journal_parser import JournalParser
from ..services.carrier_service import (
    build_current_carrier_response,
    build_current_carrier_state_response,
    build_my_carriers_response,
)
from ..utils.journal import get_journal_directory, get_journal_files
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/carriers", tags=["carriers"])


def _load_recent_journal_events() -> Tuple[List[JournalEvent], Optional[Path], Optional[str]]:
    """Parse recent journal files and return all relevant events.

    Fleet carrier related events are not guaranteed to appear in the *latest*
    Journal.*.log file. To support the Fleet Carriers UI (including when the
    commander is not currently docked), we scan multiple recent journal files
    and then derive the most recent carrier state from the combined stream.

    Returns:
        (events, newest_file_path_str) where newest_file_path_str is None if there
        are no journal files available.
    """
    try:
        journal_dir = get_journal_directory()
        all_files = get_journal_files(journal_dir)
    except FileNotFoundError:
        logger.warning("Journal directory not found while querying carrier state.")
        return [], None, None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error resolving journal directory: %s", exc)
        return [], None, None

    if not all_files:
        logger.info("No Journal.*.log files found when querying carrier state.")
        return [], journal_dir, None

    # Only parse a bounded set of files for performance.
    # If the commander has not played in a long time, scanning the last ~25
    # journal files is typically sufficient to recover the most recent carrier
    # identity + trade orders.
    MAX_RECENT_FILES = 25
    files_to_parse = all_files[-MAX_RECENT_FILES:]

    parser = JournalParser()
    events: List[JournalEvent] = []
    for file_path in files_to_parse:
        events.extend(parser.parse_file(file_path))

    newest_file = files_to_parse[-1]
    return events, journal_dir, str(newest_file)


@router.get("/current", response_model=CurrentCarrierResponse)
async def get_current_carrier() -> CurrentCarrierResponse:
    """Return the carrier (if any) the commander is currently docked at.

    This is derived purely from the latest journal file by finding the
    most recent Docked event whose StationType is FleetCarrier and
    enriching it with CarrierStats/CarrierLocation where available.
    """
    events, _journal_dir, _ = _load_recent_journal_events()
    return build_current_carrier_response(events)


@router.get("/current/state", response_model=CarrierStateResponse)
async def get_current_carrier_state() -> CarrierStateResponse:
    """Return a reconstructed snapshot of the currently docked carrier.

    The snapshot currently includes:
      - Identity (name, callsign, role, last-seen system)
      - A best-effort cargo view derived from CarrierTradeOrder SELL orders
      - Buy and sell orders derived from CarrierTradeOrder events
      - Total cargo tonnage from CarrierStats.SpaceUsage.Cargo when available

    As more carrier-specific events become available (e.g. explicit cargo
    storage snapshots), this view can be refined.
    """
    events, journal_dir, _ = _load_recent_journal_events()
    if not events:
        raise HTTPException(status_code=404, detail="No journal data available")

    response = build_current_carrier_state_response(events, journal_dir=journal_dir)
    if response is None:
        raise HTTPException(
            status_code=404,
            detail="Commander is not currently docked at a fleet carrier",
        )
    return response


@router.get("/mine", response_model=MyCarriersResponse)
async def get_my_carriers() -> MyCarriersResponse:
    """Return a list of the commander's own and squadron carriers.

    This endpoint walks the latest journal file and looks for CarrierStats
    and CarrierLocation events, grouping by carrier id. It does *not* try
    to discover arbitrary third-party carriers beyond what the journal
    exposes for this commander.
    """
    events, _journal_dir, _ = _load_recent_journal_events()
    return build_my_carriers_response(events)
