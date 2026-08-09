"""Tests for journal and settings API routes (no mocking frameworks, real FS with
backup).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from src.api import journal as journal_api
from src.api import settings as settings_api
from src.models.api_models import AppSettings


# -----------------------
# /api/journal/status
# -----------------------


@pytest.mark.asyncio
async def test_get_journal_status_with_latest_file(tmp_path: Path):
    """Journal status should return the system from the latest relevant event."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    latest_file = journal_dir / "Journal.2025-01-01T000000.01.log"

    # Commander and LoadGame events open every session's journal; a Location
    # event is enough to determine the current system and docked context.
    events = [
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "Commander",
                "Name": "Jameson",
                "FID": "F123456",
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "LoadGame",
                "Commander": "Jameson",
                "Credits": 1234567890,
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "Location",
                "StarSystem": "Test System",
                "SystemAddress": 123456,
                "StarPos": [0.0, 0.0, 0.0],
                "Docked": True,
                "StationName": "Test Station",
                "StationType": "Coriolis",
                "MarketID": 42,
            }
        ),
    ]
    latest_file.write_text("\n".join(events), encoding="utf-8")

    # Patch get_journal_directory to point at our temp dir
    orig_get_dir = journal_api.get_journal_directory
    try:
        journal_api.get_journal_directory = (
            lambda: journal_dir  # type: ignore[assignment]
        )

        result = await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]

    assert result["current_system"] == "Test System"
    assert result["commander_name"] == "Jameson"
    assert result["credits_balance"] == 1234567890
    assert result["is_docked"] is True
    assert result["station_name"] == "Test Station"
    assert result["station_type"] == "Coriolis"


@pytest.mark.asyncio
async def test_get_journal_status_no_files(tmp_path: Path):
    """When no journal files exist, status should report that fact."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    orig_get_dir = journal_api.get_journal_directory
    try:
        journal_api.get_journal_directory = (
            lambda: journal_dir  # type: ignore[assignment]
        )
        result = await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]

    assert result["current_system"] is None
    assert result["commander_name"] is None
    assert result["credits_balance"] is None
    assert result["is_docked"] is None
    assert "No journal files found" in result["message"]


@pytest.mark.asyncio
async def test_get_journal_status_docked_then_undocked(tmp_path: Path):
    """The newest docking-relevant event settles the docked context.

    Walking backwards, the Undocked event settles is_docked as False; the
    Docked event before it must not overwrite that, though it still names the
    current system.
    """
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    latest_file = journal_dir / "Journal.2025-01-01T000000.01.log"
    events = [
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "Docked",
                "StationName": "Test Carrier",
                "StationType": "FleetCarrier",
                "StarSystem": "Test System",
                "SystemAddress": 123456,
                "MarketID": 42,
                "StationFaction": {"Name": "Test Faction"},
                "StationGovernment": "Democracy",
                "StationEconomy": "Industrial",
                "StationEconomies": [],
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-01-01T00:05:00Z",
                "event": "Undocked",
                "StationName": "Test Carrier",
                "StationType": "FleetCarrier",
                "MarketID": 42,
            }
        ),
    ]
    latest_file.write_text("\n".join(events), encoding="utf-8")

    orig_get_dir = journal_api.get_journal_directory
    try:
        journal_api.get_journal_directory = (
            lambda: journal_dir  # type: ignore[assignment]
        )
        result = await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]

    assert result["current_system"] == "Test System"
    assert result["is_docked"] is False
    assert result["station_name"] is None


@pytest.mark.asyncio
async def test_get_journal_status_location_not_docked(tmp_path: Path):
    """A Location event with Docked false settles the context as in flight."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()
    latest_file = journal_dir / "Journal.2025-01-01T000000.01.log"
    events = [
        json.dumps(
            {
                "timestamp": "2025-01-01T00:00:00Z",
                "event": "Location",
                "StarSystem": "Free System",
                "SystemAddress": 654321,
                "StarPos": [0.0, 0.0, 0.0],
                "Docked": False,
            }
        ),
        json.dumps(
            {
                "timestamp": "2025-01-01T00:10:00Z",
                "event": "FSDJump",
                "StarSystem": "Next System",
                "SystemAddress": 654322,
                "StarPos": [1.0, 0.0, 0.0],
                "JumpDist": 10.0,
            }
        ),
    ]
    latest_file.write_text("\n".join(events), encoding="utf-8")

    orig_get_dir = journal_api.get_journal_directory
    try:
        journal_api.get_journal_directory = (
            lambda: journal_dir  # type: ignore[assignment]
        )
        result = await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]

    # The FSDJump is newest, so it settles both the system and the context;
    # the earlier Location must not reopen the docked question.
    assert result["current_system"] == "Next System"
    assert result["is_docked"] is False
    assert result["station_name"] is None


def test_derive_status_location_docked_false_branch():
    """A Location event that is itself the newest settles an undocked context."""
    from datetime import UTC, datetime

    from src.services.commander_event_parser import parse_location

    event = parse_location(
        {
            "event": "Location",
            "StarSystem": "Solo System",
            "SystemAddress": 1,
            "Docked": False,
        },
        datetime.now(UTC),
    )

    result = journal_api._derive_status([event])

    assert result["current_system"] == "Solo System"
    assert result["is_docked"] is False
    assert result["station_name"] is None


def test_derive_status_docked_event_settles_station():
    """A Docked event as the newest reading names the station and its type."""
    from datetime import UTC, datetime

    from src.services.commander_event_parser import parse_docked

    event = parse_docked(
        {
            "event": "Docked",
            "StationName": "Surface Base",
            "StationType": "CraterOutpost",
            "StarSystem": "Ground System",
            "SystemAddress": 2,
            "MarketID": 7,
            "StationFaction": {"Name": "Ground Faction"},
            "StationGovernment": "Corporate",
            "StationEconomy": "Extraction",
            "StationEconomies": [],
        },
        datetime.now(UTC),
    )

    result = journal_api._derive_status([event])

    assert result["current_system"] == "Ground System"
    assert result["is_docked"] is True
    assert result["station_name"] == "Surface Base"
    assert result["station_type"] == "CraterOutpost"


@pytest.mark.asyncio
async def test_get_journal_status_handles_errors():
    """Errors from underlying utilities should surface as HTTP 500."""

    def _boom():
        raise FileNotFoundError("no saved games")

    orig_get_dir = journal_api.get_journal_directory
    try:
        journal_api.get_journal_directory = _boom  # type: ignore[assignment]
        with pytest.raises(HTTPException) as exc:
            await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_journal_status_propagates_http_exception():
    """HTTPException raised by helpers should be propagated unchanged."""

    def _boom_latest_file(*args, **kwargs):
        raise HTTPException(status_code=418, detail="teapot")

    orig_get_dir = journal_api.get_journal_directory
    orig_get_latest = journal_api.get_latest_journal_file
    try:
        tmp_dir = Path.cwd()
        journal_api.get_journal_directory = lambda: tmp_dir  # type: ignore[assignment]
        journal_api.get_latest_journal_file = (
            _boom_latest_file  # type: ignore[assignment]
        )
        with pytest.raises(HTTPException) as exc:
            await journal_api.get_journal_status()
    finally:
        journal_api.get_journal_directory = orig_get_dir  # type: ignore[assignment]
        journal_api.get_latest_journal_file = (
            orig_get_latest  # type: ignore[assignment]
        )

    assert exc.value.status_code == 418


# -----------------------
# /api/settings
# -----------------------


@pytest.mark.asyncio
async def test_get_app_settings_round_trip():
    """get_app_settings should return an AppSettings model with expected fields."""
    settings = await settings_api.get_app_settings()
    assert isinstance(settings, AppSettings)
    # The journal directory is the one user-editable setting.
    assert hasattr(settings, "journal_directory")
    # The commander's name is journal-derived and the Inara configuration is
    # yaml/env-only, so none of these are settings any more.
    assert not hasattr(settings, "inara_commander_name")
    assert not hasattr(settings, "inara_api_key")
    assert not hasattr(settings, "prefer_local_for_commander_systems")


@pytest.mark.asyncio
async def test_update_app_settings_writes_config_and_leaves_commander_alone(
    tmp_path: Path,
):
    """update_app_settings should write config.yaml and never touch commander.yaml.

    To avoid polluting the real config, this test backs up config.yaml before
    running and restores it afterwards. It exercises both the 'file does not
    exist' and 'missing section' branches in the implementation.
    """
    # Determine actual paths used by the settings module
    settings_root = Path(settings_api.__file__).resolve().parent.parent.parent
    config_path = settings_root / "config.yaml"
    commander_path = settings_root / "commander.yaml"

    # Backup existing files (if any)
    orig_config = (
        config_path.read_text(encoding="utf-8") if config_path.exists() else None
    )
    commander_existed_before = commander_path.exists()

    try:
        new_journal_dir = str(tmp_path / "journals")
        app_settings = AppSettings(journal_directory=new_journal_dir)

        # ----------------------
        # 1) No existing file: exercise the creation branch.
        # ----------------------
        if config_path.exists():
            config_path.unlink()

        result = await settings_api.update_app_settings(app_settings)

        # Response should echo back the updated settings
        assert isinstance(result, AppSettings)
        assert result.journal_directory == new_journal_dir

        # Verify config.yaml contents
        assert config_path.exists()
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        assert cfg.get("journal", {}).get("directory") == new_journal_dir

        # Saving settings must not create or modify commander.yaml: the
        # dormant Inara configuration is hand-edited, never written here.
        assert commander_path.exists() == commander_existed_before

        # ----------------------
        # 2) File exists but the journal section is missing: exercise the
        #    insertion branch.
        # ----------------------
        config_path.write_text("{}", encoding="utf-8")

        await settings_api.update_app_settings(app_settings)

        cfg2 = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        assert "journal" in cfg2
    finally:
        # Restore original config.yaml
        if orig_config is None:
            if config_path.exists():
                config_path.unlink()
        else:
            config_path.write_text(orig_config, encoding="utf-8")
