"""Coverage tests for src.utils.journal, src.services.inara_service and src.api.journal.

Uses pytest monkeypatch, tiny hand-written stubs and real journal files
under tmp_path. No mock libraries are used.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.api import journal as journal_api
from src.config import InaraConfig
from src.services.inara_service import InaraService
from src.utils import journal as journal_utils


# ------------------------------------------------------------------ _get_home_dir


class _RaisingEnviron:
    """Environ stub whose get always raises, for the defensive except path."""

    def get(self, key: str, default: object = None) -> object:
        raise RuntimeError("environment unavailable")


def test_get_home_dir_environ_failure_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When environment access fails on a stub os, a sentinel path is used."""
    stub = SimpleNamespace(__name__="stub_os", environ=_RaisingEnviron(), name="posix")
    monkeypatch.setattr(journal_utils, "os", stub)

    assert journal_utils._get_home_dir() == Path("/nonexistent")


def test_get_home_dir_prefers_home_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A HOME environment variable wins over any other resolution."""
    monkeypatch.setenv("HOME", str(tmp_path))

    assert journal_utils._get_home_dir() == tmp_path


def test_get_home_dir_real_os_without_env_uses_path_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no HOME or USERPROFILE and a real-named os, Path.home() is used."""
    stub = SimpleNamespace(__name__="os", environ={}, name="posix")
    monkeypatch.setattr(journal_utils, "os", stub)

    assert journal_utils._get_home_dir() == Path.home()


# ------------------------------------------------------------------ Linux candidates


def test_linux_candidates_include_compat_and_wineprefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """STEAM_COMPAT_DATA_PATH and WINEPREFIX both contribute candidates."""
    compat = tmp_path / "compat"
    wine = tmp_path / "wineprefix"
    monkeypatch.setenv("STEAM_COMPAT_DATA_PATH", str(compat))
    monkeypatch.setenv("WINEPREFIX", str(wine))
    monkeypatch.setenv("USER", "tester")

    candidates = list(journal_utils._iter_linux_journal_candidates())

    subpath = journal_utils._JOURNAL_SUBPATH
    assert compat / "pfx" / "drive_c" / "users" / "steamuser" / subpath in candidates
    assert compat / "pfx" / "drive_c" / "users" / "tester" / subpath in candidates
    assert wine / "drive_c" / "users" / "tester" / subpath in candidates
    assert wine / "drive_c" / "users" / "steamuser" / subpath in candidates


# ------------------------------------------------------------------ get_journal_directory


def test_get_journal_directory_returns_detected_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A detected existing directory is returned as-is."""
    monkeypatch.setattr(journal_utils, "find_journal_directory", lambda: tmp_path)

    assert journal_utils.get_journal_directory() == tmp_path


# ------------------------------------------------------------------ InaraService


async def test_inara_colonisation_data_is_always_empty() -> None:
    """The Inara colonisation lookup is intentionally a no-op returning []."""
    service = InaraService(inara_config=InaraConfig())

    result = await service.get_system_colonisation_data("Sol")

    assert result == []


# ------------------------------------------------------------------ /api/journal/status


async def test_journal_status_with_no_location_style_events(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Relevant but non-location events leave the current system unknown."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    latest = journal_dir / "Journal.2026-01-01T000000.01.log"
    commander_line = json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "event": "Commander",
            "Name": "CMDR Coverage",
            "FID": "F123",
        }
    )
    latest.write_text(commander_line + "\n", encoding="utf-8")

    monkeypatch.setattr(journal_api, "get_journal_directory", lambda: journal_dir)

    result = await journal_api.get_journal_status()

    assert result == {"current_system": None}
