"""API routes for Fleet carriers.

These endpoints expose a derived view of fleet carrier state to power the
Frontend Fleet carriers tab. Data is reconstructed on demand from a window of
recent Elite: Dangerous journal files; no additional persistence is used.

Two questions run through this module and are deliberately kept apart: where
the COMMANDER is and what the CARRIER is doing. Where the commander is
standing does not change what the carrier holds, so a commander who has walked
away still gets their carrier's state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..models.api_models import (
    CarrierStateResponse,
    CurrentCarrierResponse,
    MyCarriersResponse,
)
from ..models.journal_events import JournalEvent
from ..services.carrier_service import (
    build_current_carrier_response,
    build_current_carrier_state_response,
    build_my_carriers_response,
)
from ..services.journal_parser import JournalParser
from ..utils.journal import get_journal_directory, get_journal_files
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/carriers", tags=["carriers"])


def _now() -> datetime:
    """The current UTC time.

    The only wall-clock read in the carrier stack. The services below take it
    as an argument so they stay deterministic under test; retiring a booked
    carrier jump the application never saw complete is the one question they
    cannot answer from journal events alone.
    """
    return datetime.now(UTC)


def _load_recent_journal_events() -> tuple[list[JournalEvent], Path | None, str | None]:
    """Parse recent journal files and return all relevant events.

    Fleet carrier related events are not guaranteed to appear in the *latest*
    Journal.*.log file. To support the Fleet Carriers UI (including when the
    commander is not currently docked), we scan multiple recent journal files
    and then derive the most recent carrier state from the combined stream.

    Returns:
        (events, journal_dir, newest_file_path_str). The directory is where the
        carrier's Market.json export is looked for; both it and the newest file
        are None when no journal files are available.
    """
    try:
        journal_dir = get_journal_directory()
        all_files = get_journal_files(journal_dir)
    except FileNotFoundError:
        logger.warning("Journal directory not found while querying carrier state.")
        return [], None, None
    except Exception:
        # Deliberately broad, below an HTTP boundary. The missing-directory
        # case is handled above as the expected one, so anything reaching here
        # is unanticipated. An empty result renders as "no carrier data"
        # rather than failing the whole request. The traceback goes to the log
        # so the cause stays recoverable.
        logger.exception("Unexpected error resolving journal directory")
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
    events: list[JournalEvent] = []
    for file_path in files_to_parse:
        events.extend(parser.parse_file(file_path))

    newest_file = files_to_parse[-1]
    return events, journal_dir, str(newest_file)


@router.get("/current", response_model=CurrentCarrierResponse)
async def get_current_carrier() -> CurrentCarrierResponse:
    """Return the carrier (if any) the commander is currently docked at.

    Currently, not once. The answer comes from the newest event that settles
    the question, out of Docked, Undocked, FSDJump and Location, so it goes
    false the moment the commander leaves. Asking only for the last Docked at a
    fleet carrier gives an answer that stays true forever.

    The carrier is then enriched with CarrierStats/CarrierLocation where
    available.
    """
    events, _journal_dir, _ = _load_recent_journal_events()
    return build_current_carrier_response(events, now=_now())


@router.get("/current/state", response_model=CarrierStateResponse)
async def get_current_carrier_state() -> CarrierStateResponse:
    """Return a reconstructed snapshot of the commander's carrier.

    The snapshot includes:
      - Identity (name, callsign, role, last-seen system) and, when a jump is
        booked, where the carrier is heading and when it leaves
      - The per-commodity hold, anchored on the carrier's own Market.json
        export and carried forward by the commander's trades against it,
        with the age of that export and any tonnage it cannot account for
      - Buy and sell orders derived from CarrierTradeOrder events
      - Capacity metrics from CarrierStats.SpaceUsage when available
      - Fuel, jump range, finances, tax rates and crew
      - The balance history over the window the journal covers
      - commander_aboard, which is the only field that answers for the
        commander rather than for the carrier

    Being aboard is not a precondition. A 404 here means no carrier could be
    resolved from the journal window at all, not that the commander has
    undocked from one.
    """
    events, journal_dir, _ = _load_recent_journal_events()
    if not events:
        raise HTTPException(status_code=404, detail="No journal data available")

    response = build_current_carrier_state_response(
        events, journal_dir=journal_dir, now=_now()
    )
    if response is None:
        raise HTTPException(
            status_code=404,
            detail="Commander is not currently docked at a fleet carrier",
        )
    return response


@router.get("/mine", response_model=MyCarriersResponse)
async def get_my_carriers() -> MyCarriersResponse:
    """Return a list of the commander's own and squadron carriers.

    This endpoint walks the same window of recent journal files and looks for
    CarrierStats and CarrierLocation events, grouping by carrier id. It does
    *not* try to discover arbitrary third-party carriers beyond what the
    journal exposes for this commander.
    """
    events, _journal_dir, _ = _load_recent_journal_events()
    return build_my_carriers_response(events, now=_now())
