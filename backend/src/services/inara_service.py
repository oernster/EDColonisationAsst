"""Service for fetching data from the Inara.cz API"""

import asyncio
from datetime import datetime, timedelta
from typing import Any

from ..config import InaraConfig, get_config
from ..utils.logger import get_logger

logger = get_logger(__name__)

INARA_API_URL = "https://inara.cz/inapi/v1/"

# Simple in-process rate limiting and per-system caching for Inara API calls
# NOTE: These limits are intentionally conservative to avoid Inara API bans.
# Community guidance is ~2 requests/min; 35s keeps us safely under that.
_MIN_CALL_INTERVAL_SECONDS = 35.0  # minimum delay between any two Inara calls
_CACHE_TTL = timedelta(minutes=15)

_last_call_at: datetime | None = None
_ban_until: datetime | None = None
_rate_limit_lock = asyncio.Lock()
_system_cache: dict[str, tuple[datetime, list[dict[str, Any]]]] = {}


class InaraService:
    def __init__(self, inara_config: InaraConfig):
        self.config = inara_config
        self.app_name = inara_config.app_name
        # Keep this aligned with the app version used elsewhere.
        # Canonical version is loaded from the top-level VERSION file.
        from .. import __version__

        self.app_version = __version__

    async def get_system_colonisation_data(
        self, system_name: str
    ) -> list[dict[str, Any]]:
        """
        Fetch colonisation-related data for a specific system from Inara.

        NOTE:
        There is currently no confirmed INAPI v1 event that exposes the
        construction/colonisation data this application needs (stations or
        planetary bases under construction, required commodities, etc.).
        Previous attempts incorrectly used community-goal events, which are
        unrelated to this feature and caused confusing errors and logs.

        Until a proper colonisation-related Inara event is identified, this
        method intentionally performs **no HTTP requests** and always returns
        an empty list so that the rest of the application relies solely on
        local journal data for colonisation tracking.
        """
        logger.debug(
            "Inara colonisation integration not implemented for system %s; "
            "returning no remote colonisation data.",
            system_name,
        )
        return []


def get_inara_service() -> InaraService:
    """Get an instance of the InaraService"""
    config = get_config()
    return InaraService(inara_config=config.inara)
