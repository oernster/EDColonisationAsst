"""Remembering a skipped release; surviving every way that can fail.

The contract under test: nothing in this module raises at its caller. A
missing file, a damaged one and an unwritable directory all cost at most one
extra prompt, which is not worth an error dialog.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services import update_state
from src.services.update_state import (
    load_skipped_version,
    resolve_state_file,
    save_skipped_version,
)


# ------------------------------------------------------------------- location


def test_a_source_checkout_keeps_the_file_beside_the_packages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(update_state, "is_packaged", lambda: False)

    path = resolve_state_file()

    assert path.name == "update-state.json"
    assert path.parent.name == "src"


def test_a_packaged_build_keeps_the_file_under_local_appdata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """It must outlive the install directory, which an upgrade replaces."""
    monkeypatch.setattr(update_state, "is_packaged", lambda: True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    path = resolve_state_file()

    assert path == tmp_path / "EDColonisationAsst" / "update-state.json"


def test_a_packaged_build_uses_the_xdg_data_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Off Windows it follows XDG, so a flatpak records the skip somewhere real."""
    monkeypatch.setattr(update_state, "is_packaged", lambda: True)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    path = resolve_state_file()

    assert path == tmp_path / "EDColonisationAsst" / "update-state.json"


# ------------------------------------------------------------------- reading


def test_nothing_is_skipped_before_anything_is_written(tmp_path: Path) -> None:
    assert load_skipped_version(tmp_path / "absent.json") is None


def test_a_recorded_version_reads_back(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"
    state_file.write_text(json.dumps({"skipped_version": "3.3.0"}), encoding="utf-8")

    assert load_skipped_version(state_file) == "3.3.0"


def test_a_damaged_file_reads_as_nothing_skipped(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"
    state_file.write_text("{ this is not json", encoding="utf-8")

    assert load_skipped_version(state_file) is None


def test_a_file_holding_something_other_than_an_object_reads_as_nothing(
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "update-state.json"
    state_file.write_text(json.dumps(["a list"]), encoding="utf-8")

    assert load_skipped_version(state_file) is None


def test_a_non_string_version_reads_as_nothing_skipped(tmp_path: Path) -> None:
    """A number here would compare against a tag and never match."""
    state_file = tmp_path / "update-state.json"
    state_file.write_text(json.dumps({"skipped_version": 330}), encoding="utf-8")

    assert load_skipped_version(state_file) is None


def test_an_empty_version_reads_as_nothing_skipped(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"
    state_file.write_text(json.dumps({"skipped_version": ""}), encoding="utf-8")

    assert load_skipped_version(state_file) is None


# ------------------------------------------------------------------- writing


def test_a_skip_round_trips(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"

    save_skipped_version("3.3.0", state_file)

    assert load_skipped_version(state_file) == "3.3.0"


def test_the_directory_is_created_when_it_does_not_exist(tmp_path: Path) -> None:
    state_file = tmp_path / "made" / "up" / "update-state.json"

    save_skipped_version("3.3.0", state_file)

    assert load_skipped_version(state_file) == "3.3.0"


def test_a_later_skip_replaces_the_earlier_one(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"

    save_skipped_version("3.3.0", state_file)
    save_skipped_version("3.4.0", state_file)

    assert load_skipped_version(state_file) == "3.4.0"


def test_unrelated_keys_survive_a_skip(tmp_path: Path) -> None:
    """The file is shared state, so a write must not be a replacement."""
    state_file = tmp_path / "update-state.json"
    state_file.write_text(json.dumps({"something_else": 42}), encoding="utf-8")

    save_skipped_version("3.3.0", state_file)

    written = json.loads(state_file.read_text(encoding="utf-8"))
    assert written == {"something_else": 42, "skipped_version": "3.3.0"}


def test_a_damaged_file_is_replaced_rather_than_repaired(tmp_path: Path) -> None:
    state_file = tmp_path / "update-state.json"
    state_file.write_text("{ this is not json", encoding="utf-8")

    save_skipped_version("3.3.0", state_file)

    assert load_skipped_version(state_file) == "3.3.0"


def test_an_unwritable_location_is_silent(tmp_path: Path) -> None:
    """A directory where the file should be: mkdir succeeds, the write does not."""
    state_file = tmp_path / "update-state.json"
    state_file.mkdir()

    save_skipped_version("3.3.0", state_file)

    assert load_skipped_version(state_file) is None
