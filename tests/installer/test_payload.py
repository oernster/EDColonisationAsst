"""Finding the bundled payload, and reading what travels with it.

The payload anchors are redirected at a temporary tree, so these tests stage a
tiny bundle rather than touching the one the build stages. British spelling is
used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from installer.constants import (
    BUILD_DIR_NAME,
    EXE_NAME,
    ICON_FILE_NAME,
    LICENSE_FILE_NAME,
    PAYLOAD_DIR_NAME,
    PNG_FILE_NAME,
    RUNTIME_DIR_NAME,
    VERSION_FILE_NAME,
)
from installer.ops import payload as payload_module
from installer.ops.errors import PayloadError
from installer.ops.payload import (
    LICENCE_FALLBACK,
    LICENCE_HEADER,
    app_version,
    bundled_runtime_exe,
    find_payload_root,
    icon_file,
    installed_icon,
    payload_candidates,
    payload_root,
    png_file,
    reflow_licence,
    runtime_exe_candidates,
)

_BUNDLED_VERSION = "2.9.0"


def _populate(directory: Path) -> Path:
    """Put one file in a directory so it counts as a real payload."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "marker.txt").write_text("x", encoding="utf-8")
    return directory


def test_the_package_anchor_is_the_first_payload_candidate(
    staged_payload: Path,
) -> None:
    assert payload_candidates()[0] == staged_payload / PAYLOAD_DIR_NAME


def test_the_source_staging_directory_is_a_candidate(staged_payload: Path) -> None:
    expected = staged_payload.parent / BUILD_DIR_NAME / PAYLOAD_DIR_NAME
    assert expected in payload_candidates()


def test_the_launcher_directory_is_a_candidate_when_it_resolves(
    monkeypatch: pytest.MonkeyPatch, staged_payload: Path, tmp_path: Path
) -> None:
    launcher = tmp_path / "downloads"
    monkeypatch.setattr(payload_module, "launcher_dir", lambda: launcher)

    assert launcher / PAYLOAD_DIR_NAME in payload_candidates()


def test_find_payload_root_returns_the_populated_stage(payload_dir: Path) -> None:
    _populate(payload_dir)

    assert find_payload_root() == payload_dir


def test_find_payload_root_ignores_an_empty_stage(payload_dir: Path) -> None:
    """An empty stage would deploy an empty install and report success."""
    assert find_payload_root() is None


def test_find_payload_root_falls_through_to_the_source_staging_directory(
    staged_payload: Path,
) -> None:
    fallback = _populate(staged_payload.parent / BUILD_DIR_NAME / PAYLOAD_DIR_NAME)

    assert find_payload_root() == fallback


def test_payload_root_fails_loudly_when_there_is_nothing_to_install(
    staged_payload: Path,
) -> None:
    """The old fallback to the project root would have installed the sources."""
    with pytest.raises(PayloadError):
        payload_root()


def test_payload_root_returns_the_stage_when_there_is_one(payload_dir: Path) -> None:
    _populate(payload_dir)

    assert payload_root() == payload_dir


def test_the_runtime_is_looked_for_under_the_package_first(
    staged_payload: Path,
) -> None:
    assert runtime_exe_candidates()[0] == (staged_payload / RUNTIME_DIR_NAME / EXE_NAME)


def test_the_payload_itself_is_the_last_runtime_candidate(payload_dir: Path) -> None:
    _populate(payload_dir)

    assert runtime_exe_candidates()[-1] == payload_dir / EXE_NAME


def test_bundled_runtime_exe_finds_the_embedded_copy(staged_payload: Path) -> None:
    runtime = staged_payload / RUNTIME_DIR_NAME
    runtime.mkdir()
    exe = runtime / EXE_NAME
    exe.write_bytes(b"exe")

    assert bundled_runtime_exe() == exe


def test_bundled_runtime_exe_is_none_when_nothing_carries_it(
    staged_payload: Path,
) -> None:
    assert bundled_runtime_exe() is None


def test_app_version_reads_the_bundled_version(payload_dir: Path) -> None:
    (payload_dir / VERSION_FILE_NAME).write_text(
        f"{_BUNDLED_VERSION}\n", encoding="utf-8"
    )

    assert app_version() == _BUNDLED_VERSION


def test_app_version_skips_an_empty_version_file(
    staged_payload: Path, payload_dir: Path
) -> None:
    _populate(payload_dir)
    (payload_dir / VERSION_FILE_NAME).write_text("  \n", encoding="utf-8")
    (staged_payload / VERSION_FILE_NAME).write_text(_BUNDLED_VERSION, encoding="utf-8")

    assert app_version() == _BUNDLED_VERSION


def test_app_version_is_empty_when_nothing_is_bundled(staged_payload: Path) -> None:
    assert app_version() == ""


def test_licence_text_reads_and_rewraps_the_bundled_licence(
    staged_payload: Path,
) -> None:
    (staged_payload / LICENSE_FILE_NAME).write_text("one\ntwo", encoding="utf-8")

    text = payload_module.licence_text()

    assert text.startswith(LICENCE_HEADER)
    assert "one two" in text


def test_licence_text_falls_back_when_nothing_is_bundled(
    staged_payload: Path,
) -> None:
    assert payload_module.licence_text() == LICENCE_HEADER + LICENCE_FALLBACK


def test_licence_text_skips_a_licence_that_cannot_be_read(
    staged_payload: Path,
) -> None:
    """A directory where the file should be is passed over, not fatal."""
    (staged_payload / LICENSE_FILE_NAME).mkdir()

    assert payload_module.licence_text() == LICENCE_HEADER + LICENCE_FALLBACK


def test_reflow_joins_a_paragraph_and_keeps_the_blank_lines() -> None:
    reflowed = reflow_licence("one\ntwo\n\n\n\nthree", width=40)

    assert reflowed == "one two\n\n\n\nthree"


def test_reflow_leaves_an_indented_block_alone() -> None:
    block = "    def thing():\n        return 1"

    assert reflow_licence(block) == block


def test_icon_and_png_are_found_when_bundled(payload_dir: Path) -> None:
    ico = payload_dir / ICON_FILE_NAME
    ico.write_bytes(b"ico")
    png = payload_dir / PNG_FILE_NAME
    png.write_bytes(b"png")

    assert icon_file() == ico
    assert png_file() == png


def test_icon_and_png_are_none_when_absent(staged_payload: Path) -> None:
    assert icon_file() is None
    assert png_file() is None


def test_installed_icon_is_found_in_an_install(tmp_path: Path) -> None:
    icon = tmp_path / ICON_FILE_NAME
    icon.write_bytes(b"ico")

    assert installed_icon(tmp_path) == icon


def test_installed_icon_is_none_when_absent(tmp_path: Path) -> None:
    assert installed_icon(tmp_path) is None
