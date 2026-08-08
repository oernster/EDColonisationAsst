"""Coverage tests for src/repositories/colonisation_db.py.

Where the database file goes; what happens to one this build cannot read.
Split out of test_coverage_repository.py; the scaffolding lives in
_test_coverage_repository_support.py.

Most of these drive ColonisationDatabase directly, since resolving a path and
stamping a schema version needs no repository. The two that also assert a
round-trip through the repository redirect DB_FILE instead, which is the seam
production uses.

All database work uses real SQLite files under pytest tmp_path; no mock
libraries are used anywhere (hand-written fakes plus monkeypatch only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.repositories.colonisation_db as db_mod
import src.repositories.colonisation_repository as repo_mod
from src.repositories.colonisation_db import (
    CURRENT_DB_SCHEMA_VERSION,
    ColonisationDatabase,
    resolve_db_file,
)
from src.repositories.colonisation_repository import ColonisationRepository

from tests.unit._test_coverage_repository_support import (
    FakeDbFile,
    UnreadableUntilResetDbFile,
    create_db_with_metadata,
    make_site,
)


# ---------------------------------------------------------------------------
# resolve_db_file: dev and frozen resolution
# ---------------------------------------------------------------------------


def test_resolve_db_file_dev_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """In dev mode the DB lives inside the source tree, beside the packages."""
    monkeypatch.setattr(db_mod, "is_frozen", lambda: False)

    expected = Path(db_mod.__file__).parent.parent / "colonisation.db"
    assert resolve_db_file() == expected


def test_resolve_db_file_frozen_with_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In frozen mode the DB lives under LOCALAPPDATA when it is set."""
    monkeypatch.setattr(db_mod, "is_frozen", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    expected = tmp_path / "EDColonisationAsst" / "colonisation.db"
    assert resolve_db_file() == expected


def test_resolve_db_file_frozen_without_localappdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without LOCALAPPDATA the frozen DB falls back to the home directory."""
    monkeypatch.setattr(db_mod, "is_frozen", lambda: True)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    expected = Path.home() / ".edcolonisationasst" / "colonisation.db"
    assert resolve_db_file() == expected


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
    assert ColonisationDatabase(db_file).read_schema_version() == (
        CURRENT_DB_SCHEMA_VERSION
    )

    site = make_site()
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
    site = make_site()
    await repo1.add_construction_site(site)

    repo2 = ColonisationRepository()
    assert ColonisationDatabase(db_file).read_schema_version() == (
        CURRENT_DB_SCHEMA_VERSION
    )
    loaded = await repo2.get_site_by_market_id(site.market_id)
    assert loaded is not None


def test_database_without_version_row_is_reset(tmp_path: Path) -> None:
    """A DB whose metadata table has no version row is deleted and rebuilt."""
    db_file = tmp_path / "colonisation.db"
    create_db_with_metadata(db_file, version=None)

    database = ColonisationDatabase(db_file)
    database.initialise()

    assert database.read_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_database_with_outdated_version_is_reset(tmp_path: Path) -> None:
    """A DB stamped with a different schema version is deleted and rebuilt."""
    db_file = tmp_path / "colonisation.db"
    create_db_with_metadata(db_file, version="999")

    database = ColonisationDatabase(db_file)
    database.initialise()

    assert database.read_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_unreadable_database_file_is_reset(tmp_path: Path) -> None:
    """An unreadable DB triggers the version-read warning path and a reset."""
    unreadable = tmp_path / "actually-a-directory"
    unreadable.mkdir()
    fake = UnreadableUntilResetDbFile(unreadable, tmp_path / "colonisation.db")

    database = ColonisationDatabase(fake)
    database.initialise()

    assert database.read_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_reset_tolerates_unlink_file_not_found(tmp_path: Path) -> None:
    """A FileNotFoundError during the reset unlink is silently ignored."""
    real_db = tmp_path / "colonisation.db"
    create_db_with_metadata(real_db, version="999")
    fake = FakeDbFile(real_db, unlink_exc=FileNotFoundError("already gone"))

    database = ColonisationDatabase(fake)
    database.initialise()

    assert database.read_schema_version() == CURRENT_DB_SCHEMA_VERSION


def test_reset_tolerates_generic_unlink_failure(tmp_path: Path) -> None:
    """Any other unlink failure is logged and the schema is still rebuilt."""
    real_db = tmp_path / "colonisation.db"
    create_db_with_metadata(real_db, version="999")
    fake = FakeDbFile(real_db, unlink_exc=PermissionError("locked"))

    database = ColonisationDatabase(fake)
    database.initialise()

    assert database.read_schema_version() == CURRENT_DB_SCHEMA_VERSION


async def test_mkdir_failure_is_logged_but_connection_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing parent-directory mkdir is logged; sqlite still connects."""
    real_db = tmp_path / "colonisation.db"
    fake = FakeDbFile(real_db, exploding_parent=True)
    monkeypatch.setattr(repo_mod, "DB_FILE", fake)

    repo = ColonisationRepository()

    site = make_site()
    await repo.add_construction_site(site)
    assert await repo.get_site_by_market_id(site.market_id) is not None
