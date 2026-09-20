"""Unpacking the runtime archive into an install directory.

EDCA no longer ships a compiled binary: the interpreter, its dependencies, the
sources and the built front end travel as one archive and are extracted into
the install. That makes extraction the only path that delivers the application,
so its failures matter more than the file copy beside it. These tests stage a
handful of named entries in place of the real 95 MB archive. British spelling
is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import RecordingProgress, stage_runtime_archive

from installer.constants import (
    EXE_NAME,
    LAUNCH_SCRIPT_NAME,
    RUNTIME_ARCHIVE_NAME,
    RUNTIME_DIR_NAME,
)
from installer.ops.errors import RuntimeExeError, UnsafePayloadEntryError
from installer.ops.install_ops import extract_runtime
from installer.ops.progress import RUNTIME_END_PCT, RUNTIME_MESSAGE, RUNTIME_START_PCT

ESCAPING_ENTRY = "../escaped.txt"


def test_extract_runtime_unpacks_the_whole_tree(bundle: Path, tmp_path: Path) -> None:
    install_dir = tmp_path / "installed"

    extracted = extract_runtime(install_dir)

    assert extracted == install_dir / EXE_NAME
    assert extracted.read_bytes() == b"runtime"
    assert (install_dir / LAUNCH_SCRIPT_NAME).read_bytes() == b"launch"
    assert (install_dir / "backend" / "src" / "main.py").is_file()


def test_extract_runtime_replaces_the_previous_installs_files(
    bundle: Path, tmp_path: Path
) -> None:
    """A reinstall must overwrite what is already there.

    Everything in the archive belongs to the PREVIOUS install once one exists.
    Skipping because the target existed is the defect that once left a 3.0.0
    install whose splash reported 2.9.0.
    """
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    stale = install_dir / EXE_NAME
    stale.write_bytes(b"the previous version")

    replaced = extract_runtime(install_dir)

    assert replaced == stale
    assert stale.read_bytes() == b"runtime"


def test_extract_runtime_reports_nothing_when_no_archive_is_bundled(
    staged_payload: Path, tmp_path: Path
) -> None:
    assert extract_runtime(tmp_path / "installed") is None


def test_extract_runtime_keeps_an_install_when_no_archive_is_bundled(
    staged_payload: Path, tmp_path: Path
) -> None:
    """With nothing to extract, leave a working install alone rather than break it."""
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    existing = install_dir / EXE_NAME
    existing.write_bytes(b"already installed")

    assert extract_runtime(install_dir) == existing
    assert existing.read_bytes() == b"already installed"


def test_extract_runtime_reports_nothing_when_the_archive_carries_no_executable(
    staged_payload: Path, tmp_path: Path
) -> None:
    """An archive without the launcher deploys, yet there is nothing to point at."""
    stage_runtime_archive(staged_payload, {"backend/src/main.py": b"x"})
    install_dir = tmp_path / "installed"

    assert extract_runtime(install_dir) is None
    assert (install_dir / "backend" / "src" / "main.py").is_file()


def test_extract_runtime_fails_loudly_when_the_install_cannot_be_written(
    bundle: Path, tmp_path: Path
) -> None:
    """A failure to unpack must stop the install, not be swallowed.

    Returning None here let the install carry on and report success while the
    previous version's files stayed on disk, which is indistinguishable to the
    user from an install that worked.
    """
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RuntimeExeError):
        extract_runtime(blocked)


def test_extract_runtime_fails_loudly_on_an_archive_it_cannot_read(
    staged_payload: Path, tmp_path: Path
) -> None:
    runtime = staged_payload / RUNTIME_DIR_NAME
    runtime.mkdir()
    (runtime / RUNTIME_ARCHIVE_NAME).write_bytes(b"not a zip file")

    with pytest.raises(RuntimeExeError):
        extract_runtime(tmp_path / "installed")


def test_extract_runtime_refuses_an_entry_that_climbs_out_of_the_install(
    staged_payload: Path, tmp_path: Path
) -> None:
    """The archive is built by this project's own tooling, so this never fires.

    It is the guard that makes that a guarantee rather than an assumption,
    since the extraction runs with the user's full privileges.
    """
    stage_runtime_archive(staged_payload, {ESCAPING_ENTRY: b"payload"})
    install_dir = tmp_path / "installed"

    with pytest.raises(UnsafePayloadEntryError):
        extract_runtime(install_dir)

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_runtime_reports_across_its_own_span(
    bundle: Path, tmp_path: Path
) -> None:
    progress = RecordingProgress()

    extract_runtime(tmp_path / "installed", progress=progress)

    percentages = progress.percentages
    assert percentages[-1] == RUNTIME_END_PCT
    assert all(RUNTIME_START_PCT <= pct <= RUNTIME_END_PCT for pct in percentages)
    assert percentages == sorted(percentages)
    assert {message for _, message in progress.updates} == {RUNTIME_MESSAGE}
