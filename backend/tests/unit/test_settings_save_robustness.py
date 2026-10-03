"""Saving settings over a damaged or interrupted config.yaml.

A damaged config.yaml made every Settings save fail with a 500, so the one
place the user can fix the journal folder was the one place that could not.
The write was also a truncate-then-write in place, so an interruption left a
half-written file. A damaged file is now kept aside (never destroying a copy
kept aside earlier) and the save goes ahead from a clean start; the write goes
to a temporary file that replaces the real one only once complete. A file
that cannot be READ at all is not treated as empty and saved over.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import src.config as config_mod
from src.api import settings as settings_api
from src.config import AppConfig, JournalConfig
from src.models.api_models import AppSettings

_NEW_FOLDER = "D:/Journals"


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.yaml"
    monkeypatch.setattr(
        settings_api, "get_config_paths", lambda: (path, tmp_path / "commander.yaml")
    )
    monkeypatch.setattr(
        config_mod, "_config", AppConfig(journal=JournalConfig(directory="C:/old"))
    )
    return path


async def _save() -> AppSettings:
    return await settings_api.update_app_settings(
        AppSettings(journal_directory=_NEW_FOLDER)
    )


def _saved_folder(path: Path) -> str:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["journal"]["directory"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        "journal: [unclosed\n",
        "- a list\n- not a mapping\n",
        "journal: just a string\n",
    ],
)
async def test_a_damaged_file_is_kept_aside_and_the_save_succeeds(
    config_file: Path, damage: str
) -> None:
    config_file.write_text(damage, encoding="utf-8")

    await _save()

    assert _saved_folder(config_file) == _NEW_FOLDER
    kept = config_file.with_name("config.yaml.damaged")
    assert kept.read_text(encoding="utf-8") == damage


@pytest.mark.asyncio
async def test_an_earlier_kept_aside_copy_is_never_destroyed(
    config_file: Path,
) -> None:
    earlier = config_file.with_name("config.yaml.damaged")
    earlier.write_text("the first damage\n", encoding="utf-8")
    config_file.write_bytes(b"\xff\xfe not utf-8\n")

    await _save()

    assert earlier.read_text(encoding="utf-8") == "the first damage\n"
    second = config_file.with_name("config.yaml.damaged.1")
    assert second.read_bytes() == b"\xff\xfe not utf-8\n"
    assert _saved_folder(config_file) == _NEW_FOLDER


@pytest.mark.asyncio
async def test_an_interrupted_write_leaves_the_previous_file_intact(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = "journal:\n  directory: C:/old\nserver:\n  host: 127.0.0.1\n"
    config_file.write_text(original, encoding="utf-8")

    def interrupted_dump(data, stream, **kwargs) -> None:
        stream.write("journal:\n")
        raise OSError("disk full")

    monkeypatch.setattr(settings_api.yaml, "dump", interrupted_dump)

    with pytest.raises(OSError):
        await _save()

    assert config_file.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_other_settings_survive_a_save(config_file: Path) -> None:
    config_file.write_text("server:\n  host: 127.0.0.1\n", encoding="utf-8")

    await _save()

    saved = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert saved["server"]["host"] == "127.0.0.1"
    assert saved["journal"]["directory"] == _NEW_FOLDER


@pytest.mark.asyncio
async def test_a_first_save_creates_the_folder_and_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A packaged runtime's per-user configuration folder may not exist yet."""
    path = tmp_path / "EDColonisationAsst" / "config.yaml"
    monkeypatch.setattr(
        settings_api, "get_config_paths", lambda: (path, path.with_name("c.yaml"))
    )
    monkeypatch.setattr(
        config_mod, "_config", AppConfig(journal=JournalConfig(directory="C:/old"))
    )

    await _save()

    assert _saved_folder(path) == _NEW_FOLDER


@pytest.mark.asyncio
async def test_a_file_that_cannot_be_read_is_not_saved_over(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file.write_text("server:\n  port: 1\n", encoding="utf-8")
    real_open = open

    def refusing_open(file, mode="r", *args, **kwargs):
        if Path(file) == config_file and "r" in mode:
            raise PermissionError("locked")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", refusing_open)

    with pytest.raises(PermissionError):
        await _save()

    monkeypatch.undo()
    assert config_file.read_text(encoding="utf-8") == "server:\n  port: 1\n"
