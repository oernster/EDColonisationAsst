"""Colonisation data repository.

`ColonisationRepository` is the only thing in the application that reads or
writes the colonisation database. Two concerns were lifted out of it once it
passed the module cap, both chosen because neither takes part in a query's
transaction:

- colonisation_db: where the file is, what schema version it holds and how a
  connection is opened. All of it runs once, in `__init__`, before any lock.
- colonisation_mapping: rebuilding a `ConstructionSite` from a row and
  normalising a commodity key. Both are pure.

Concurrency, which did not move and must not:

- `self._lock` is a non-reentrant `asyncio.Lock`. Every method that opens a
  connection takes it. Every method that calls one of those must NOT take it
  as well or it deadlocks, which is why `get_stats` and `update_commodity` are
  the two without it: they are composed of the others.
- Each connection is opened inside its own `with` block, so one transaction
  never spans two methods. `update_commodity` is therefore a read and a write
  in two separate transactions, not one; the comment on it records why.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from datetime import UTC, datetime
import json
import sqlite3

from ..models.colonisation import ConstructionSite
from ..utils.logger import get_logger
from .colonisation_db import ColonisationDatabase, resolve_db_file
from .colonisation_mapping import normalise_commodity_key, row_to_site

logger = get_logger(__name__)

DB_FILE = resolve_db_file()


class IColonisationRepository(ABC):
    """Interface for colonisation data repository"""

    @abstractmethod
    async def add_construction_site(self, site: ConstructionSite) -> None:
        """Add or update construction site data"""

    @abstractmethod
    async def get_site_by_market_id(self, market_id: int) -> ConstructionSite | None:
        """Get construction site by market ID"""

    @abstractmethod
    async def get_sites_by_system(self, system_name: str) -> list[ConstructionSite]:
        """Get all construction sites in a system"""

    @abstractmethod
    async def get_all_systems(self) -> list[str]:
        """Get list of all known systems with construction"""

    @abstractmethod
    async def get_all_sites(self) -> list[ConstructionSite]:
        """Get all construction sites from the database"""

    @abstractmethod
    async def get_stats(self) -> dict[str, int]:
        """Get basic statistics about stored construction sites"""

    @abstractmethod
    async def update_commodity(
        self, market_id: int, commodity_name: str, provided_amount: int
    ) -> None:
        """Update commodity provided amount for a site"""

    @abstractmethod
    async def clear_all(self) -> None:
        """Clear all data (mainly for testing)"""


class ColonisationRepository(IColonisationRepository):
    """
    SQLite-based persistent storage for colonisation data.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        # Read at construction rather than per query. DB_FILE is a module
        # constant in production; the tests that redirect it do so before
        # building the repository.
        self._database = ColonisationDatabase(DB_FILE)
        self._database.initialise()

    def _get_db_connection(self) -> sqlite3.Connection:
        return self._database.connect()

    async def add_construction_site(self, site: ConstructionSite) -> None:
        async with self._lock:
            site.last_updated = datetime.now(UTC)
            # Use model_dump (Pydantic v2) instead of deprecated dict()
            commodities_json = json.dumps([c.model_dump() for c in site.commodities])

            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO construction_sites
                    (market_id, station_name, station_type, system_name, system_address,
                    construction_progress, construction_complete, construction_failed,
                    commodities, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        site.market_id,
                        site.station_name,
                        site.station_type,
                        site.system_name,
                        site.system_address,
                        site.construction_progress,
                        site.construction_complete,
                        site.construction_failed,
                        commodities_json,
                        site.last_updated.isoformat(),
                    ),
                )
                conn.commit()
            logger.info(
                "REPOSITORY: Added/updated site %s in %s with data: %s",
                site.station_name,
                site.system_name,
                site.model_dump(),
            )

    async def get_site_by_market_id(self, market_id: int) -> ConstructionSite | None:
        async with self._lock:
            with self._get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM construction_sites WHERE market_id = ?", (market_id,)
                )
                row = cursor.fetchone()
                return row_to_site(row) if row else None

    async def get_sites_by_system(self, system_name: str) -> list[ConstructionSite]:
        async with self._lock:
            with self._get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM construction_sites "
                    "WHERE system_name = ? ORDER BY station_name",
                    (system_name,),
                )
                rows = cursor.fetchall()
                return [row_to_site(row) for row in rows if row]

    async def get_all_systems(self) -> list[str]:
        async with self._lock:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT DISTINCT system_name FROM construction_sites "
                    "ORDER BY system_name"
                )
                rows = cursor.fetchall()
                systems = [row[0] for row in rows]
                logger.info(f"REPOSITORY: Returning {len(systems)} systems: {systems}")
                return systems

    async def get_all_sites(self) -> list[ConstructionSite]:
        async with self._lock:
            with self._get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM construction_sites "
                    "ORDER BY system_name, station_name"
                )
                rows = cursor.fetchall()
                return [row_to_site(row) for row in rows if row]

    async def get_stats(self) -> dict[str, int]:
        """
        Get basic statistics about stored construction sites.

        Does not take the lock. get_all_sites below takes it and the lock is
        not reentrant.

        Returns:
            Dict[str, int]: {
                "total_systems": number of distinct systems,
                "total_sites": total number of sites,
                "in_progress_sites": sites not yet completed,
                "completed_sites": completed sites,
            }
        """
        sites = await self.get_all_sites()
        total_sites = len(sites)
        completed_sites = sum(1 for s in sites if s.construction_complete)

        stats = {
            "total_systems": len({s.system_name for s in sites}),
            "total_sites": total_sites,
            "in_progress_sites": total_sites - completed_sites,
            "completed_sites": completed_sites,
        }
        logger.info(f"REPOSITORY: Stats calculated: {stats}")
        return stats

    async def update_commodity(
        self, market_id: int, commodity_name: str, provided_amount: int
    ) -> None:
        """
        Update commodity provided amount for a site.

        Note:
            This method intentionally does NOT acquire self._lock directly,
            because both get_site_by_market_id() and add_construction_site()
            handle their own locking. Acquiring the lock here and then calling
            those methods would result in a deadlock with the non-reentrant
            asyncio.Lock. The read and the write are therefore two separate
            transactions rather than one.

        Matching strategy:
            Elite Dangerous can emit slightly different identifiers for the
            same commodity across events (e.g. "aluminium" vs
            "$Aluminium_Name;"). To ensure ColonisationContribution events
            update the correct Commodity row even when the raw strings differ,
            we compare normalised keys derived via normalise_commodity_key(...)
            on both the stored commodity name and the incoming commodity_name.
        """
        site = await self.get_site_by_market_id(market_id)
        if not site:
            logger.warning(
                "Cannot update commodity: site with market ID %s not found", market_id
            )
            return

        target_key = normalise_commodity_key(commodity_name)
        if not target_key:
            logger.warning(
                "Cannot update commodity: empty commodity name for market ID %s",
                market_id,
            )
            return

        updated = False
        for commodity in site.commodities:
            if normalise_commodity_key(commodity.name) == target_key:
                # Use the latest observed cumulative total. Journal semantics
                # guarantee that TotalQuantity is non-decreasing, so a simple
                # assignment is sufficient; however, guard against any
                # unexpected regressions by taking the maximum.
                commodity.provided_amount = max(
                    commodity.provided_amount, provided_amount
                )
                updated = True
                break

        if not updated:
            logger.warning(
                "Commodity %s (normalised key=%s) not found at site %s (market_id=%s)",
                commodity_name,
                target_key,
                site.station_name,
                market_id,
            )
            return

        await self.add_construction_site(site)
        logger.debug(
            "Updated commodity %s at %s (market_id=%s) to provided_amount=%s",
            commodity_name,
            site.station_name,
            market_id,
            provided_amount,
        )

    async def clear_all(self) -> None:
        async with self._lock:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM construction_sites")
                conn.commit()
            logger.info("Cleared all colonisation data")


__all__ = ["DB_FILE", "ColonisationRepository", "IColonisationRepository"]
