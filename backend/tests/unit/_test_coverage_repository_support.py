"""Shared scaffolding for the test_coverage_repository modules.

Split out of test_coverage_repository.py when that file passed the module cap.
Not named test_* on purpose: pytest collects only the modules that use it.

The fakes here all stand in for the database file path. Each one delegates the
real filesystem work to a genuine tmp_path file while making one specific
operation fail, which is how the defensive paths in colonisation_db are driven
without mock libraries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from src.models.colonisation import Commodity, ConstructionSite


def make_site(market_id: int = 42) -> ConstructionSite:
    """Build a minimal but realistic construction site for round-trips."""
    return ConstructionSite(
        market_id=market_id,
        station_name="Coverage Station",
        station_type="Orbital Construction Depot",
        system_name="Coverage System",
        system_address=555,
        construction_progress=25.0,
        construction_complete=False,
        construction_failed=False,
        commodities=[
            Commodity(
                name="steel",
                name_localised="Steel",
                required_amount=100,
                provided_amount=10,
                payment=999,
            )
        ],
        last_updated=datetime.now(UTC),
    )


def create_db_with_metadata(db_path: Path, version: str | None) -> None:
    """Create a real SQLite DB containing only the metadata table.

    When version is None the table is left empty so that the schema-version
    lookup finds no row at all.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if version is not None:
            cursor.execute(
                "INSERT INTO metadata (key, value) VALUES ('db_schema_version', ?)",
                (version,),
            )
        conn.commit()


class ExplodingDir:
    """Stand-in for a Path parent whose mkdir always fails."""

    def mkdir(self, *args: object, **kwargs: object) -> None:
        raise OSError("simulated mkdir failure")


class FakeDbFile:
    """Hand-written fake for the database file path.

    Delegates real filesystem work to a genuine tmp_path file while letting
    tests inject failures for mkdir or unlink. sqlite3.connect accepts this
    object because it implements the os.PathLike protocol.
    """

    def __init__(
        self,
        real: Path,
        unlink_exc: Exception | None = None,
        exploding_parent: bool = False,
    ) -> None:
        self._real = real
        self._unlink_exc = unlink_exc
        self._exploding_parent = exploding_parent

    @property
    def parent(self) -> object:
        if self._exploding_parent:
            return ExplodingDir()
        return self._real.parent

    def exists(self) -> bool:
        return self._real.exists()

    def unlink(self) -> None:
        if self._unlink_exc is not None:
            raise self._unlink_exc
        self._real.unlink()

    def __fspath__(self) -> str:
        return str(self._real)

    def __str__(self) -> str:
        return str(self._real)


class UnreadableUntilResetDbFile:
    """DB path fake that cannot be opened until it has been unlinked.

    Before the reset it points sqlite at a directory, which makes
    sqlite3.connect fail immediately without ever holding a file handle
    (a garbage file would leave the failed connection holding a Windows
    handle that blocks the subsequent unlink). After unlink it points at
    a real writable file so the rebuild succeeds.
    """

    def __init__(self, unreadable: Path, good: Path) -> None:
        self._unreadable = unreadable
        self._good = good
        self._reset = False

    @property
    def parent(self) -> Path:
        return self._good.parent

    def exists(self) -> bool:
        return True

    def unlink(self) -> None:
        self._reset = True

    def __fspath__(self) -> str:
        return str(self._good if self._reset else self._unreadable)

    def __str__(self) -> str:
        return self.__fspath__()
