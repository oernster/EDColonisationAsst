"""Translation between what SQLite stores and what the domain models expect.

Two translations, both pure and both about the same problem: the same thing
arrives written two different ways.

- `row_to_site` turns a stored row back into a `ConstructionSite`, rebuilding
  the commodities that were flattened into a JSON column.
- `normalise_commodity_key` reduces the several spellings Elite uses for one
  commodity to a single key, so a contribution can find the row a depot
  snapshot created.

Neither touches a connection, so neither takes part in a transaction.
"""

from __future__ import annotations

from datetime import datetime
import json
import sqlite3

from ..models.colonisation import Commodity, ConstructionSite


def normalise_commodity_key(name: str) -> str:
    """Normalise a journal commodity identifier into a stable key.

    Elite Dangerous sometimes uses slightly different strings for the same
    underlying commodity across events, for example:

      - "aluminium"
      - "$Aluminium_Name;"

    To ensure ColonisationContribution events can always be matched to the
    commodities discovered via ColonisationConstructionDepot snapshots, we
    convert both sides to a canonical, lower-case token:

      - strip surrounding whitespace
      - lower-case
      - strip a leading "$" and trailing ";" if present
      - strip a trailing "_name" suffix if present

    The original, user-facing name remains in Commodity.name_localised.
    """
    key = name.strip().lower()
    if not key:
        return key

    # Strip journal-style wrappers like "$Aluminium_Name;"
    if key.startswith("$") and key.endswith(";"):
        key = key[1:-1]

    # Strip a trailing "_name" suffix if present.
    return key.removesuffix("_name")


def row_to_site(row: sqlite3.Row | None) -> ConstructionSite | None:
    """Rebuild a ConstructionSite from a stored row; None for no row."""
    if not row:
        return None

    commodities = [Commodity(**c) for c in json.loads(row["commodities"])]
    return ConstructionSite(
        market_id=row["market_id"],
        station_name=row["station_name"],
        station_type=row["station_type"],
        system_name=row["system_name"],
        system_address=row["system_address"],
        construction_progress=row["construction_progress"],
        construction_complete=row["construction_complete"],
        construction_failed=row["construction_failed"],
        commodities=commodities,
        last_updated=datetime.fromisoformat(row["last_updated"]),
    )


__all__ = ["normalise_commodity_key", "row_to_site"]
