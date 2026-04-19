"""Unit tests for SystemTracker and utility modules (no mocking)."""

from datetime import datetime, UTC
from pathlib import Path
import logging
import os
import types

import pytest

from src.models.journal_events import LocationEvent, FSDJumpEvent, DockedEvent
from src.services.system_tracker import SystemTracker
from src.utils.journal import get_latest_journal_file, get_journal_directory
from src.utils.logger import setup_logging, get_logger
from src.utils.windows import get_saved_games_path


# -----------------------
# SystemTracker tests
# -----------------------


def _make_location_event(
    star_system: str,
    docked: bool,
    station_name: str | None = None,
    station_type: str | None = None,
) -> LocationEvent:
    return LocationEvent(
        timestamp=datetime.now(UTC),
        event="Location",
        star_system=star_system,
        system_address=123456,
        star_pos=[0.0, 0.0, 0.0],
        station_name=station_name,
        station_type=station_type,
        market_id=42 if docked else None,
        docked=docked,
        raw_data={},
    )


def _make_fsd_jump_event(star_system: str) -> FSDJumpEvent:
    return FSDJumpEvent(
        timestamp=datetime.now(UTC),
        event="FSDJump",
        star_system=star_system,
        system_address=654321,
        star_pos=[1.0, 2.0, 3.0],
        jump_dist=10.5,
        fuel_used=3.0,
        fuel_level=5.0,
        raw_data={},
    )


def _make_docked_event(star_system: str, station_name: str) -> DockedEvent:
    return DockedEvent(
        timestamp=datetime.now(UTC),
        event="Docked",
        station_name=station_name,
        station_type="Outpost",
        star_system=star_system,
        system_address=777,
        market_id=999,
        station_faction={"Name": "Test Faction"},
        station_government="Democracy",
        station_economy="Industrial",
        station_economies=[],
        raw_data={},
    )


def test_system_tracker_initial_state():
    tracker = SystemTracker()
    assert tracker.get_current_system() is None
    assert tracker.get_current_station() is None
    assert tracker.is_docked() is False


def test_system_tracker_update_from_location_docked():
    tracker = SystemTracker()
    event = _make_location_event(
        "Test System", docked=True, station_name="Test Station", station_type="Coriolis"
    )

    tracker.update_from_location(event)

    assert tracker.get_current_system() == "Test System"
    assert tracker.get_current_station() == "Test Station"
    assert tracker.is_docked() is True


def test_system_tracker_update_from_location_undocked():
    tracker = SystemTracker()
    event = _make_location_event("Deep Space", docked=False)

    tracker.update_from_location(event)

    assert tracker.get_current_system() == "Deep Space"
    assert tracker.get_current_station() is None
    assert tracker.is_docked() is False


def test_system_tracker_update_from_jump_clears_dock():
    tracker = SystemTracker()
    # Start docked
    dock_event = _make_docked_event("Origin System", "Origin Station")
    tracker.update_from_docked(dock_event)
    assert tracker.is_docked() is True

    # Jump away
    jump_event = _make_fsd_jump_event("Destination System")
    tracker.update_from_jump(jump_event)

    assert tracker.get_current_system() == "Destination System"
    assert tracker.get_current_station() is None
    assert tracker.is_docked() is False


def test_system_tracker_update_from_docked_sets_state():
    tracker = SystemTracker()
    event = _make_docked_event("Dock System", "Dock Station")

    tracker.update_from_docked(event)

    assert tracker.get_current_system() == "Dock System"
    assert tracker.get_current_station() == "Dock Station"
    assert tracker.is_docked() is True


# -----------------------
# Utils: journal
# -----------------------


def test_get_latest_journal_file_returns_latest(tmp_path: Path):
    """Ensure get_latest_journal_file picks the newest Journal.*.log by mtime."""
    journal_dir = tmp_path
    older = journal_dir / "Journal.2025-01-01T000000.01.log"
    newer = journal_dir / "Journal.2025-01-02T000000.01.log"

    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")

    # Explicitly control modification times to avoid filesystem resolution issues
    older_time = 1_700_000_000  # arbitrary but stable epoch times
    newer_time = older_time + 100

    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))

    latest = get_latest_journal_file(journal_dir)
    assert latest is not None
    assert latest.name == newer.name


def test_get_latest_journal_file_empty_dir(tmp_path: Path):
    """Empty directory should yield None."""
    latest = get_latest_journal_file(tmp_path)
    assert latest is None


# -----------------------
# Utils: windows + logger
# -----------------------


def test_get_saved_games_path_does_not_crash():
    """get_saved_games_path should never raise; it may legitimately return None."""
    path = get_saved_games_path()
    assert path is None or isinstance(path, Path)


def test_get_saved_games_path_uses_shgetknownfolderpath(monkeypatch, tmp_path: Path):
    """Happy path: SHGetKnownFolderPath provides a Saved Games path."""
    import src.utils.windows as windows_mod  # local import so we patch the right module

    target_dir = tmp_path / "Saved Games"
    target_dir.mkdir()

    class DummyShell32:
        def SHGetKnownFolderPath(self, folder_id, flags, token, out_path):
            # Simulate the Windows API writing a path string to the out parameter.
            out_path._obj.value = str(target_dir)

    class DummyOle32:
        def CoTaskMemFree(self, ptr):
            # No-op for tests
            pass

    class DummyWindll:
        def __init__(self):
            self.shell32 = DummyShell32()
            self.ole32 = DummyOle32()

    # Ensure we exercise the SHGetKnownFolderPath branch rather than the USERPROFILE fallback
    monkeypatch.setattr(windows_mod.ctypes, "windll", DummyWindll(), raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)

    path = windows_mod.get_saved_games_path()
    assert isinstance(path, Path)
    assert path == target_dir


def test_get_saved_games_path_returns_none_when_no_api_and_no_env(monkeypatch):
    """If both SHGetKnownFolderPath and USERPROFILE are unavailable, function should return None."""
    import src.utils.windows as windows_mod  # local import so we patch the right module

    class FailingWindll:
        def __getattr__(self, name):
            # Any attempt to access shell32/ole32 will raise
            raise OSError("No shell32/ole32 available")

    monkeypatch.setattr(windows_mod.ctypes, "windll", FailingWindll(), raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)

    path = windows_mod.get_saved_games_path()
    assert path is None


def test_setup_logging_and_get_logger():
    """setup_logging and get_logger should be callable without errors."""
    setup_logging(level="DEBUG", format_str="%(levelname)s:%(name)s:%(message)s")
    logger = get_logger("test_logger_system")
    assert isinstance(logger, logging.Logger)
    logger.debug("This is a debug message from test_setup_logging_and_get_logger")


def test_get_journal_directory_raises_when_saved_games_missing():
    """Windows-only: get_journal_directory should raise when Saved Games path cannot be determined."""
    import src.utils.journal as journal_mod  # local import to patch safely
    import src.utils.windows as windows_mod  # patch underlying Windows helper actually used

    # Make this test deterministic cross-platform by forcing the Windows branch.
    # (On Linux/macOS, get_journal_directory() would otherwise use Proton/Wine
    # auto-detection and never consult windows_mod.)
    orig_os_name = getattr(journal_mod.os, "name", None)
    try:
        setattr(journal_mod.os, "name", "nt")

        orig_get_saved_games = windows_mod.get_saved_games_path
        try:
            windows_mod.get_saved_games_path = lambda: None  # type: ignore[assignment]
            with pytest.raises(FileNotFoundError):
                journal_mod.get_journal_directory()
        finally:
            windows_mod.get_saved_games_path = orig_get_saved_games  # type: ignore[assignment]
    finally:
        if orig_os_name is not None:
            setattr(journal_mod.os, "name", orig_os_name)


def test_get_journal_directory_raises_when_journal_folder_missing(tmp_path: Path):
    """Windows-only: get_journal_directory should raise when the Frontier/Elite Dangerous folder is missing."""
    import src.utils.journal as journal_mod  # local import to patch safely
    import src.utils.windows as windows_mod  # patch underlying Windows helper actually used

    # Force the Windows branch so this test can run on any OS.
    orig_os_name = getattr(journal_mod.os, "name", None)
    try:
        setattr(journal_mod.os, "name", "nt")

        # Simulate a Saved Games folder without the expected subdirectory
        saved_games = tmp_path / "Saved Games"
        saved_games.mkdir()

        orig_get_saved_games = windows_mod.get_saved_games_path
        try:
            windows_mod.get_saved_games_path = lambda: saved_games  # type: ignore[assignment]
            with pytest.raises(FileNotFoundError):
                journal_mod.get_journal_directory()
        finally:
            windows_mod.get_saved_games_path = orig_get_saved_games  # type: ignore[assignment]
    finally:
        if orig_os_name is not None:
            setattr(journal_mod.os, "name", orig_os_name)


def test_find_journal_directory_uses_linux_steam_compat(monkeypatch, tmp_path: Path):
    """Linux path: find_journal_directory should detect Proton compatdata journals when present."""
    import src.utils.journal as journal_mod  # local import to patch safely

    compat_dir = tmp_path / "compatdata"
    journal_dir = (
        compat_dir
        / "pfx"
        / "drive_c"
        / "users"
        / "steamuser"
        / "Saved Games"
        / "Frontier Developments"
        / "Elite Dangerous"
    )
    journal_dir.mkdir(parents=True)

    fake_os = types.SimpleNamespace(
        name="posix",
        environ={
            "STEAM_COMPAT_DATA_PATH": str(compat_dir),
            "USER": "steamuser",
        },
    )

    # Replace the os module used inside src.utils.journal with a minimal POSIX-like stub.
    monkeypatch.setattr(journal_mod, "os", fake_os, raising=False)

    detected = journal_mod.find_journal_directory()
    assert detected == journal_dir


def test_get_journal_directory_linux_error_message_lists_candidates(monkeypatch):
    """Linux path: get_journal_directory should raise with a helpful error message when no dirs exist."""
    import src.utils.journal as journal_mod  # local import to patch safely

    fake_os = types.SimpleNamespace(
        name="posix",
        environ={"USER": "steamuser"},
    )

    monkeypatch.setattr(journal_mod, "os", fake_os, raising=False)

    with pytest.raises(FileNotFoundError) as excinfo:
        journal_mod.get_journal_directory()

    message = str(excinfo.value)
    assert (
        "Could not auto-detect the Elite Dangerous journal directory on Linux."
        in message
    )
    assert "Tried the following locations:" in message
