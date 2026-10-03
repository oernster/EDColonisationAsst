"""The configured journal folder is the one every view reads.

The Settings page saves a journal folder and the colonisation watcher follows
it. The commander header and every carrier view used to re-detect the folder
from Saved Games instead, so a Proton, Wine or moved Saved Games user saw
sites from one folder and the header, carriers, hold and orders from another
or from nothing. These tests put a different commander in each folder and
assert that the configured one wins everywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

import src.config as config_mod
from src.api.carriers import router as carriers_router
from src.api.journal import router as journal_router
from src.config import AppConfig, JournalConfig
from src.utils import journal as journal_utils

_CONFIGURED_CMDR = "ConfiguredCmdr"
_DETECTED_CMDR = "DetectedCmdr"
_CONFIGURED_CARRIER_ID = 3700000001
_DETECTED_CARRIER_ID = 3700000002


def _write_journal(folder: Path, commander: str, carrier_id: int, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "timestamp": "2025-01-01T00:00:00Z",
            "event": "Commander",
            "Name": commander,
            "FID": f"F-{commander}",
        },
        {
            "timestamp": "2025-01-01T00:00:01Z",
            "event": "CarrierStats",
            "CarrierID": carrier_id,
            "Callsign": f"{name[:3].upper()}-001",
            "Name": name,
        },
    ]
    path = folder / "Journal.2025-01-01T000000.01.log"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


@pytest.fixture
def two_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A configured folder and a different detected one, each with a commander."""
    configured = tmp_path / "configured"
    detected = tmp_path / "detected"
    _write_journal(configured, _CONFIGURED_CMDR, _CONFIGURED_CARRIER_ID, "Configured")
    _write_journal(detected, _DETECTED_CMDR, _DETECTED_CARRIER_ID, "Detected")

    monkeypatch.setattr(journal_utils, "find_journal_directory", lambda: detected)
    monkeypatch.setattr(
        config_mod,
        "_config",
        AppConfig(journal=JournalConfig(directory=str(configured))),
    )
    return configured


def test_the_resolver_answers_the_configured_folder(two_folders: Path) -> None:
    assert journal_utils.get_journal_directory() == two_folders


def test_a_configured_folder_that_is_missing_is_reported_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing configured folder is an answer, never a silent swap."""
    detected = tmp_path / "detected"
    detected.mkdir()
    missing = tmp_path / "gone"
    monkeypatch.setattr(journal_utils, "find_journal_directory", lambda: detected)
    monkeypatch.setattr(
        config_mod, "_config", AppConfig(journal=JournalConfig(directory=str(missing)))
    )

    with pytest.raises(FileNotFoundError, match="gone"):
        journal_utils.get_journal_directory()


def _client(*routers) -> httpx.AsyncClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
    )


@pytest.mark.asyncio
async def test_the_commander_header_reads_the_configured_folder(
    two_folders: Path,
) -> None:
    async with _client(journal_router) as client:
        response = await client.get("/api/journal/status")

    assert response.status_code == 200
    assert response.json()["commander_name"] == _CONFIGURED_CMDR


@pytest.mark.asyncio
async def test_the_carrier_list_reads_the_configured_folder(two_folders: Path) -> None:
    async with _client(carriers_router) as client:
        response = await client.get("/api/carriers/mine")

    assert response.status_code == 200
    ids = [entry["carrier_id"] for entry in response.json()["own_carriers"]]
    assert ids == [_CONFIGURED_CARRIER_ID]
