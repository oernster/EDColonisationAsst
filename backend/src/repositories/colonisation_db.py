"""Location, schema and connections for the colonisation SQLite database.

Everything here runs once, at repository construction, before any query and
outside the repository's lock. That is what makes it separable from
`ColonisationRepository`: nothing in this module takes part in a transaction
that a query also takes part in, so moving it moves no transaction boundary.

The schema is versioned rather than migrated. A database that does not
advertise `CURRENT_DB_SCHEMA_VERSION` is deleted and rebuilt empty, which is
only safe because every row in it can be rebuilt from the commander's journal
files: `prime_colonisation_database_if_empty` does exactly that on the next
start. So raise the version for a change that makes an existing file
unreadable, never for one SQLite can absorb on its own.

Failures here are logged rather than raised. A packaged install that cannot
create its database directory should still start and say why, rather than
dying before the user sees a window.
"""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3

from ..utils.logger import get_logger
from ..utils.runtime import is_frozen

logger = get_logger(__name__)

# Increment this when we make a breaking change to the on-disk schema for the
# colonisation database. The repository will reset (delete and recreate) any
# existing DB that does not advertise this version in its metadata table.
CURRENT_DB_SCHEMA_VERSION = 1

_DB_FILENAME = "colonisation.db"
_FROZEN_DIR_NAME = "EDColonisationAsst"
_FROZEN_FALLBACK_DIR_NAME = ".edcolonisationasst"
_SCHEMA_VERSION_KEY = "db_schema_version"


def resolve_db_file() -> Path:
    """
    Determine the location of the colonisation SQLite database.

    - In DEV mode (non-frozen): keep the DB inside the source tree, beside the
      packages that use it:

        backend/src/colonisation.db

      This is derived from this module's own location, so this module has to
      stay one directory below `src` for it to hold.

    - In FROZEN mode (packaged EXE via Nuitka): store the DB under a
      user-local, writable directory so it persists across runs and does
      not live in Nuitka's temporary onefile extraction directory:

        %LOCALAPPDATA%\\EDColonisationAsst\\colonisation.db

      If LOCALAPPDATA is not set for any reason, fall back to the user's
      home directory.
    """
    if not is_frozen():
        return Path(__file__).parent.parent / _DB_FILENAME

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        base = Path(local_appdata) / _FROZEN_DIR_NAME
    else:
        base = Path.home() / _FROZEN_FALLBACK_DIR_NAME

    return base / _DB_FILENAME


class ColonisationDatabase:
    """Owns where the database file is and what shape it is in.

    Holds no connection: every caller opens its own inside a `with` block, so
    a connection never outlives the transaction it was opened for.
    """

    def __init__(self, db_file: Path) -> None:
        self._db_file = db_file

    def connect(self) -> sqlite3.Connection:
        """Open a connection, creating the containing directory if needed."""
        # Ensure the parent directory for the DB exists before connecting,
        # especially in FROZEN mode where we store the DB under
        # %LOCALAPPDATA%\\EDColonisationAsst.
        db_dir = self._db_file.parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("Failed to create DB directory %s: %s", db_dir, exc)
            # Let sqlite3.connect raise a clearer error below.
        return sqlite3.connect(self._db_file)

    def initialise(self) -> None:
        """
        Ensure the on-disk database matches the expected schema version.

        Behaviour:
            - If no DB file exists, create it, create tables and set the current
              schema version.
            - If a DB file exists but has no version metadata or a different
              version, delete it once and recreate it with the current schema
              version.

        On first run (or after reset), the FastAPI lifespan helper
        `prime_colonisation_database_if_empty` is responsible for repopulating
        the fresh DB from the user's journal files.
        """
        # If the DB file does not exist at all, just create it and stamp the
        # version.
        if not self._db_file.exists():
            self._create_tables()
            self._write_schema_version(CURRENT_DB_SCHEMA_VERSION)
            return

        # DB file exists; check metadata.
        if self.read_schema_version() == CURRENT_DB_SCHEMA_VERSION:
            return

        self._delete_outdated_file()
        self._create_tables()
        self._write_schema_version(CURRENT_DB_SCHEMA_VERSION)

    def read_schema_version(self) -> int | None:
        """
        Read the current schema version from the metadata table, if present.

        Returns:
            The stored integer schema version, None if missing or invalid.
        """
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM metadata WHERE key = ?",
                    (_SCHEMA_VERSION_KEY,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return int(row[0])
        except sqlite3.Error as exc:
            # Reading a metadata row can only fail as a sqlite3.Error here: a missing
            # table on a pre-migration database, a locked file. Treating the version
            # as unknown triggers the migration path.
            logger.warning(
                "Failed to read %s from metadata; treating as unknown: %s",
                _SCHEMA_VERSION_KEY,
                exc,
            )
            return None

    def _delete_outdated_file(self) -> None:
        """Remove a database whose schema this build cannot read."""
        try:
            self._db_file.unlink()
            logger.info(
                "Deleted existing colonisation DB at %s due to missing or "
                "outdated schema metadata; a fresh DB will be created.",
                self._db_file,
            )
        except FileNotFoundError:
            # Someone else may have removed it; that's fine.
            pass
        except OSError as exc:
            # unlink() fails as OSError: the file being held open by another process,
            # a permissions problem. Both are worth reporting to the user rather than
            # crashing the reset.
            logger.error("Failed to delete colonisation DB %s: %s", self._db_file, exc)

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS construction_sites (
                    market_id INTEGER PRIMARY KEY,
                    station_name TEXT NOT NULL,
                    station_type TEXT,
                    system_name TEXT NOT NULL,
                    system_address INTEGER,
                    construction_progress REAL,
                    construction_complete BOOLEAN,
                    construction_failed BOOLEAN,
                    commodities TEXT,
                    last_updated TEXT
                )
            """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """
            )
            conn.commit()

    def _write_schema_version(self, version: int) -> None:
        """Persist the given schema version into the metadata table."""
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (_SCHEMA_VERSION_KEY, str(version)),
            )
            conn.commit()


__all__ = [
    "CURRENT_DB_SCHEMA_VERSION",
    "ColonisationDatabase",
    "resolve_db_file",
]
