"""Coverage tests for src/repositories/colonisation_repository.py.

These tests exercise the code paths not reached by the behavioural test
suite: DB file location resolution in frozen mode, schema-version reset
logic, defensive error handling around directory creation and file
deletion, the abstract interface bodies and the commodity-key edge cases.

All database work uses real SQLite files under pytest tmp_path; no mock
libraries are used anywhere (hand-written fakes plus monkeypatch only).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

import src.repositories.colonisation_repository as repo_mod
from src.models.colonisation import Commodity, ConstructionSite
from src.repositories.colonisation_repository import (
    CURRENT_DB_SCHEMA_VERSION,
    ColonisationRepository,
    IColonisationRepository,
    _get_db_file,
    _normalise_commodity_key,
)


def _make_site(market_id: int = 42) -> ConstructionSite:
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


def _create_db_with_metadata(db_path: Path, version: str | None) -> None:
    """Create a real SQLite DB containing only the metadata table.

    When version is None the table is left empty so that the repository's
    schema-version lookup finds no row at all.
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS metadata "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        if version is not None:
            cursor.execute(
                "INSERT INTO metadata (key, value) " "VALUES ('db_schema_version', ?)",
                (version,),
            )
        conn.commit()


class _ExplodingDir:
    """Stand-in for a Path parent whose mkdir always fails."""

    def mkdir(self, *args: object, **kwargs: object) -> None:
        raise OSError("simulated mkdir failure")


class _FakeDbFile:
    """Hand-written fake for the module-level DB_FILE path.

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
            return _ExplodingDir()
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


# ---------------------------------------------------------------------------
# _get_db_file: dev and frozen resolution
# ---------------------------------------------------------------------------


def test_get_db_file_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """In dev mode the DB lives next to the src package."""
    monkeypatch.setattr(repo_mod, "is_frozen", lambda: False)

    expected = Path(repo_mod.__file__).parent.parent / "colonisation.db"
    assert _get_db_file() == expected


def test_get_db_file_frozen_with_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In frozen mode the DB lives under LOCALAPPDATA when it is set."""
    monkeypatch.setattr(repo_mod, "is_frozen", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    expected = tmp_path / "EDColonisationAsst" / "colonisation.db"
    assert _get_db_file() == expected


def test_get_db_file_frozen_without_localappdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without LOCALAPPDATA the frozen DB falls back to the home directory."""
    monkeypatch.setattr(repo_mod, "is_frozen", lambda: True)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    expected = Path.home() / ".edcolonisationasst" / "colonisation.db"
    assert _get_db_file() == expected


# ---------------------------------------------------------------------------
# _normalise_commodity_key
# ---------------------------------------------------------------------------


def test_normalise_commodity_key_empty_inputs() -> None:
    """Empty or whitespace-only names normalise to the empty string."""
    assert _normalise_commodity_key("") == ""
    assert _normalise_commodity_key("   ") == ""


def test_normalise_commodity_key_journal_wrapper() -> None:
    """Journal-style wrappers and suffixes are stripped to a canonical key."""
    assert _normalise_commodity_key("$Aluminium_Name;") == "aluminium"
    assert _normalise_commodity_key("  Steel ") == "steel"


# ---------------------------------------------------------------------------
# Abstract interface bodies
# ---------------------------------------------------------------------------


async def test_abstract_interface_bodies_execute() -> None:
    """Invoke the abstract coroutine bodies directly.

    The ABC methods contain only pass statements; calling them unbound with
    a placeholder self executes those bodies so they count as covered while
    proving they are inert no-ops.
    """
    placeholder = object()
    site = _make_site()

    assert (
        await IColonisationRepository.add_construction_site(placeholder, site) is None
    )
    assert await IColonisationRepository.get_site_by_market_id(placeholder, 1) is None
    assert await IColonisationRepository.get_sites_by_system(placeholder, "X") is None
    assert await IColonisationRepository.get_all_systems(placeholder) is None
    assert await IColonisationRepository.get_all_sites(placeholder) is None
    assert await IColonisationRepository.get_stats(placeholder) is None
    assert (
        await IColonisationRepository.update_commodity(placeholder, 1, "steel", 1)
        is None
    )
    assert await IColonisationRepository.clear_all(placeholder) is None


# ---------------------------------------------------------------------------
# Database initialisation and schema-version handling
# ---------------------------------------------------------------------------


async def test_fresh_database_created_and_stamped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing DB file is created, tabled and stamped with the version."""
    db_file = tmp_path / "colonisation.db"
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()

    assert db_file.exists()
    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION

    site = _make_site()
    await repo.add_construction_site(site)
    loaded = await repo.get_site_by_market_id(site.market_id)
    assert loaded is not None
    assert loaded.station_name == site.station_name


async def test_existing_database_with_current_version_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-initialisation against a current-version DB preserves its data."""
    db_file = tmp_path / "colonisation.db"
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo1 = ColonisationRepository()
    site = _make_site()
    await repo1.add_construction_site(site)

    repo2 = ColonisationRepository()
    assert repo2._get_schema_version() == CURRENT_DB_SCHEMA_VERSION
    loaded = await repo2.get_site_by_market_id(site.market_id)
    assert loaded is not None


def test_database_without_version_row_is_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB whose metadata table has no version row is deleted and rebuilt."""
    db_file = tmp_path / "colonisation.db"
    _create_db_with_metadata(db_file, version=None)
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()

    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_database_with_outdated_version_is_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB stamped with a different schema version is deleted and rebuilt."""
    db_file = tmp_path / "colonisation.db"
    _create_db_with_metadata(db_file, version="999")
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()

    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION


class _UnreadableUntilResetDbFile:
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


def test_unreadable_database_file_is_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable DB triggers the version-read warning path and a reset."""
    unreadable = tmp_path / "actually-a-directory"
    unreadable.mkdir()
    fake = _UnreadableUntilResetDbFile(unreadable, tmp_path / "colonisation.db")
    monkeypatch.setattr(repo_mod, "DB_FILE", fake)

    repo = ColonisationRepository()

    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_reset_tolerates_unlink_file_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FileNotFoundError during the reset unlink is silently ignored."""
    real_db = tmp_path / "colonisation.db"
    _create_db_with_metadata(real_db, version="999")
    fake = _FakeDbFile(real_db, unlink_exc=FileNotFoundError("already gone"))
    monkeypatch.setattr(repo_mod, "DB_FILE", fake)

    repo = ColonisationRepository()

    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_reset_tolerates_generic_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Any other unlink failure is logged and the schema is still rebuilt."""
    real_db = tmp_path / "colonisation.db"
    _create_db_with_metadata(real_db, version="999")
    fake = _FakeDbFile(real_db, unlink_exc=PermissionError("locked"))
    monkeypatch.setattr(repo_mod, "DB_FILE", fake)

    repo = ColonisationRepository()

    assert repo._get_schema_version() == CURRENT_DB_SCHEMA_VERSION


async def test_mkdir_failure_is_logged_but_connection_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing parent-directory mkdir is logged; sqlite still connects."""
    real_db = tmp_path / "colonisation.db"
    fake = _FakeDbFile(real_db, exploding_parent=True)
    monkeypatch.setattr(repo_mod, "DB_FILE", fake)

    repo = ColonisationRepository()

    site = _make_site()
    await repo.add_construction_site(site)
    assert await repo.get_site_by_market_id(site.market_id) is not None


# ---------------------------------------------------------------------------
# update_commodity and _row_to_site edge cases
# ---------------------------------------------------------------------------


async def test_update_commodity_rejects_empty_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty (post-normalisation) commodity name is refused with a warning."""
    db_file = tmp_path / "colonisation.db"
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()
    site = _make_site()
    await repo.add_construction_site(site)

    await repo.update_commodity(site.market_id, "   ", 12345)

    loaded = await repo.get_site_by_market_id(site.market_id)
    assert loaded is not None
    assert loaded.commodities[0].provided_amount == 10


def test_row_to_site_returns_none_for_falsy_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The row converter guards against falsy rows by returning None."""
    db_file = tmp_path / "colonisation.db"
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()

    assert repo._row_to_site(None) is None
