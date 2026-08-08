"""Coverage tests for the colonisation repository and its mapping helpers.

The paths not reached by the behavioural suite: the abstract interface
bodies, the commodity-key edge cases and the row converter's guard. The
database file location and schema-reset logic live in
test_coverage_repository_db.py; the scaffolding in
_test_coverage_repository_support.py.

All database work uses real SQLite files under pytest tmp_path; no mock
libraries are used anywhere (hand-written fakes plus monkeypatch only).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import src.repositories.colonisation_repository as repo_mod
from src.repositories.colonisation_mapping import normalise_commodity_key, row_to_site
from src.repositories.colonisation_repository import (
    ColonisationRepository,
    IColonisationRepository,
)

from tests.unit._test_coverage_repository_support import make_site


# ---------------------------------------------------------------------------
# normalise_commodity_key
# ---------------------------------------------------------------------------


def test_normalise_commodity_key_empty_inputs() -> None:
    """Empty or whitespace-only names normalise to the empty string."""
    assert normalise_commodity_key("") == ""
    assert normalise_commodity_key("   ") == ""


def test_normalise_commodity_key_journal_wrapper() -> None:
    """Journal-style wrappers and suffixes are stripped to a canonical key."""
    assert normalise_commodity_key("$Aluminium_Name;") == "aluminium"
    assert normalise_commodity_key("  Steel ") == "steel"


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
    site = make_site()

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
# update_commodity and row_to_site edge cases
# ---------------------------------------------------------------------------


async def test_update_commodity_rejects_empty_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty (post-normalisation) commodity name is refused with a warning."""
    db_file = tmp_path / "colonisation.db"
    monkeypatch.setattr(repo_mod, "DB_FILE", db_file)

    repo = ColonisationRepository()
    site = make_site()
    await repo.add_construction_site(site)

    await repo.update_commodity(site.market_id, "   ", 12345)

    loaded = await repo.get_site_by_market_id(site.market_id)
    assert loaded is not None
    assert loaded.commodities[0].provided_amount == 10


def test_row_to_site_returns_none_for_falsy_row() -> None:
    """The row converter guards against falsy rows by returning None."""
    assert row_to_site(None) is None
