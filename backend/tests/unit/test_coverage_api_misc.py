"""Coverage tests for API routes, settings and changes endpoints.

These tests close the remaining uncovered lines and branches in
src/api/routes.py, src/api/settings.py and src/api/changes.py using
real components, hand-written fakes and monkeypatch (no mock libraries).
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import src.config as config_module
from src.api import changes as changes_api
from src.api import routes as routes_api
from src.api import settings as settings_api
from src.config import AppConfig
from src.models.api_models import AppSettings
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.change_bus import change_bus


@pytest.fixture
def routes_app() -> FastAPI:
    """Build a minimal FastAPI app exposing the colonisation router."""
    app = FastAPI()
    app.include_router(routes_api.router)
    return app


# ---------------------------------------------------------------------------
# /api/watcher/status
# ---------------------------------------------------------------------------


class _FakeHandler:
    """Hand-written stand-in for JournalFileHandler diagnostics."""

    last_watchdog_event_at = "2026-01-01T00:00:00Z"
    last_watchdog_event_type = "modified"
    last_watchdog_event_path = "Journal.log"
    last_processed_at = "2026-01-01T00:00:01Z"
    last_processed_file = "Journal.log"
    last_error = None
    last_events_parsed = 3
    last_updated_systems = ["Test System"]
    last_depot_market_ids = [123456]


class _FakeWatcher:
    """Hand-written stand-in for FileWatcher used by the status endpoint."""

    def __init__(self, directory: str | None, handler: object | None) -> None:
        self._directory = directory
        self._handler = handler

    def is_running(self) -> bool:
        return True

    def watched_directory(self) -> str | None:
        return self._directory

    def watchdog_status(self) -> dict:
        return {"configured": True, "alive": True}

    def poller_status(self) -> dict:
        return {"running": True}


@pytest.mark.asyncio
async def test_watcher_status_without_watcher(
    routes_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no watcher is registered, the status should use safe fallbacks."""
    import src.main as main_mod

    monkeypatch.setattr(main_mod.app.state, "file_watcher", None, raising=False)

    async with httpx.AsyncClient(app=routes_app, base_url="http://test") as client:
        resp = await client.get("/api/watcher/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["watcher_running"] is False
    assert data["watcher_directory"] is None
    assert data["watchdog"] == {"configured": False, "alive": False}
    assert data["poller"] == {"running": False}
    assert data["handler"] is None


@pytest.mark.asyncio
async def test_watcher_status_with_full_watcher(
    routes_app: FastAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A fully featured watcher should surface all diagnostic fields."""
    import src.main as main_mod

    watcher = _FakeWatcher(directory=str(tmp_path), handler=_FakeHandler())
    monkeypatch.setattr(main_mod.app.state, "file_watcher", watcher, raising=False)

    async with httpx.AsyncClient(app=routes_app, base_url="http://test") as client:
        resp = await client.get("/api/watcher/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["watcher_running"] is True
    assert data["watcher_directory"] == str(tmp_path)
    assert data["watchdog"] == {"configured": True, "alive": True}
    assert data["poller"] == {"running": True}
    handler = data["handler"]
    assert handler is not None
    assert handler["last_events_parsed"] == 3
    assert handler["last_updated_systems"] == ["Test System"]
    assert handler["last_depot_market_ids"] == [123456]
    assert handler["last_error"] is None


@pytest.mark.asyncio
async def test_watcher_status_with_bare_watcher_object(
    routes_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A watcher lacking diagnostics should fall back to defaults.

    This exercises the getattr default lambdas plus the empty
    watched-directory path where the reported directory becomes None.
    """
    import src.main as main_mod

    class _Bare:
        """Watcher with none of the optional diagnostic methods."""

    monkeypatch.setattr(main_mod.app.state, "file_watcher", _Bare(), raising=False)

    async with httpx.AsyncClient(app=routes_app, base_url="http://test") as client:
        resp = await client.get("/api/watcher/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["watcher_running"] is False
    assert data["watcher_directory"] is None
    assert data["watchdog"] == {"configured": False, "alive": False}
    assert data["poller"] == {"running": False}
    assert data["handler"] is None


@pytest.mark.asyncio
async def test_watcher_status_survives_main_import_failure(
    routes_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If importing the main app fails, the endpoint should degrade gracefully."""
    # Replace the cached module with a namespace lacking the `app` attribute
    # so that `from ..main import app` raises ImportError inside the endpoint.
    monkeypatch.setitem(sys.modules, "src.main", types.SimpleNamespace())

    async with httpx.AsyncClient(app=routes_app, base_url="http://test") as client:
        resp = await client.get("/api/watcher/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["watcher_running"] is False
    assert data["handler"] is None


# ---------------------------------------------------------------------------
# /api/debug/reload-journals
# ---------------------------------------------------------------------------


class _RaisingBus:
    """Change bus stand-in whose bump always fails."""

    async def bump(self) -> int:
        raise RuntimeError("bus unavailable")


@pytest.mark.asyncio
async def test_reload_journals_skips_files_without_depot_events_and_tolerates_bus_failure(
    repository: ColonisationRepository,
    tmp_path: Path,
    sample_journal_line: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files without depot events are not counted and bump failures are swallowed.

    The first journal file contains only a Location event so the depot-event
    filter is empty for it; the second contains one depot event. The change
    bus is replaced with a failing fake to exercise the except branch.
    """
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    location_line = json.dumps(
        {
            "timestamp": "2025-01-01T00:00:00Z",
            "event": "Location",
            "StarSystem": "Reload System",
            "SystemAddress": 1,
            "StarPos": [0.0, 0.0, 0.0],
            "Docked": False,
        }
    )
    no_depot_file = journal_dir / "Journal.2025-01-01T000000.01.log"
    no_depot_file.write_text(location_line + "\n", encoding="utf-8")

    depot_file = journal_dir / "Journal.2025-01-02T000000.01.log"
    depot_file.write_text(sample_journal_line + "\n", encoding="utf-8")

    # Force a deterministic mtime ordering: no-depot file first, depot file last.
    base_time = no_depot_file.stat().st_mtime
    os.utime(no_depot_file, (base_time, base_time))
    os.utime(depot_file, (base_time + 60, base_time + 60))

    class _Cfg:
        class _Journal:
            directory = str(journal_dir)

        journal = _Journal()

    monkeypatch.setattr(config_module, "get_config", lambda: _Cfg())
    monkeypatch.setattr(routes_api, "_repository", repository)
    monkeypatch.setattr(routes_api, "change_bus", _RaisingBus())

    result = await routes_api.reload_journals()

    assert result["total_events"] == 1
    assert result["processed_files"] == [depot_file.name]
    assert result["journal_directory"] == str(journal_dir)


# ---------------------------------------------------------------------------
# /api/settings POST
# ---------------------------------------------------------------------------


def _settings_payload(journal_dir: str) -> dict:
    """Build a JSON payload for the settings update endpoint."""
    return {
        "journal_directory": journal_dir,
        "inara_api_key": "KEY",
        "inara_commander_name": "CMDR Coverage",
        "prefer_local_for_commander_systems": True,
    }


class _RecordingWatcher:
    """Watcher fake that records restart calls."""

    def __init__(self) -> None:
        self.stop_calls = 0
        self.started_directories: list[Path] = []

    async def stop_watching(self) -> None:
        self.stop_calls += 1

    async def start_watching(self, directory: Path) -> None:
        self.started_directories.append(directory)


class _ExplodingWatcher:
    """Watcher fake whose stop always fails to trigger the except branch."""

    async def stop_watching(self) -> None:
        raise RuntimeError("watcher restart failed")

    async def start_watching(self, directory: Path) -> None:
        raise AssertionError("start_watching should never be reached")


@pytest.mark.asyncio
async def test_update_app_settings_with_no_loaded_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the global config has never been loaded, the in-memory update is skipped."""
    config_path = tmp_path / "config.yaml"
    commander_path = tmp_path / "commander.yaml"
    monkeypatch.setattr(
        settings_api, "get_config_paths", lambda: (config_path, commander_path)
    )
    monkeypatch.setattr(config_module, "_config", None)

    payload = AppSettings(
        journal_directory=str(tmp_path / "journals"),
        inara_api_key=None,
        inara_commander_name=None,
    )
    result = await settings_api.update_app_settings(payload)

    assert result.journal_directory == str(tmp_path / "journals")
    assert config_path.exists()
    assert commander_path.exists()


@pytest.mark.asyncio
async def test_update_app_settings_restarts_watcher_over_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed journal directory should restart the app's file watcher."""
    config_path = tmp_path / "config.yaml"
    commander_path = tmp_path / "commander.yaml"
    monkeypatch.setattr(
        settings_api, "get_config_paths", lambda: (config_path, commander_path)
    )
    # Use a private AppConfig instance so the real global config is untouched.
    monkeypatch.setattr(config_module, "_config", AppConfig())

    app = FastAPI()
    app.include_router(settings_api.router)
    watcher = _RecordingWatcher()
    app.state.file_watcher = watcher

    new_dir = str(tmp_path / "new_journals")
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/api/settings", json=_settings_payload(new_dir))

    assert resp.status_code == 200
    assert watcher.stop_calls == 1
    assert watcher.started_directories == [Path(new_dir)]


@pytest.mark.asyncio
async def test_update_app_settings_swallows_watcher_restart_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Watcher restart failures must never fail the settings save."""
    config_path = tmp_path / "config.yaml"
    commander_path = tmp_path / "commander.yaml"
    monkeypatch.setattr(
        settings_api, "get_config_paths", lambda: (config_path, commander_path)
    )
    monkeypatch.setattr(config_module, "_config", AppConfig())

    app = FastAPI()
    app.include_router(settings_api.router)
    app.state.file_watcher = _ExplodingWatcher()

    new_dir = str(tmp_path / "other_journals")
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/api/settings", json=_settings_payload(new_dir))

    assert resp.status_code == 200
    assert resp.json()["journal_directory"] == new_dir


# ---------------------------------------------------------------------------
# /api/changes/longpoll
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_longpoll_returns_change_snapshot() -> None:
    """The longpoll endpoint should report a change when the sequence advanced."""
    seq = await change_bus.bump()

    result = await changes_api.longpoll(since=seq - 1, timeout_s=1.0)

    assert result["changed"] is True
    assert result["seq"] >= seq
