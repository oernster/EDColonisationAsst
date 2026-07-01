"""Coverage tests for src/__init__.py, src/utils/runtime.py and windows.py.

The package __init__ resolves VERSION and BUILD_ID from the source tree
first and then from the directory next to the running executable. The
source tree always contains both files, so the fallback paths never run
under the behavioural suite. These tests substitute the module-level Path
name with hand-written fakes to force each resolution branch, using real
files in tmp_path for the executable-adjacent lookups.

Also covered: the runtime.is_frozen defensive except path and the Windows
Saved Games fallback taken when the wide-char pointer is never allocated.
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Callable

import pytest

import src as backend_pkg
from src.utils import runtime as runtime_mod
from src.utils import windows as windows_mod


class _AlwaysRaisingPath:
    """Path stand-in whose construction always fails.

    Substituting this for the module-level Path name forces both the
    source-tree and the executable-adjacent lookups into their except
    handlers so the final hardcoded fallbacks are returned.
    """

    def __init__(self, *args: object) -> None:
        raise RuntimeError("forced Path construction failure for test")


def _redirecting_path(module_file: str, replacement: Path) -> Callable[[object], Path]:
    """Build a Path factory that redirects the package __file__ elsewhere.

    Any other argument is passed through to a real Path so that the
    executable-adjacent lookup still works against tmp_path files.
    """

    def _factory(arg: object) -> Path:
        if str(arg) == module_file:
            return replacement
        return Path(str(arg))

    return _factory


def _fake_source_init(tmp_path: Path) -> Path:
    """Return a fake src/__init__.py path whose project root is empty.

    parents[2] of this path is tmp_path/"root", which contains neither a
    VERSION nor a BUILD_ID file, so the source-tree lookup misses cleanly.
    """
    return tmp_path / "root" / "backend" / "src" / "__init__.py"


# ---------------------------------------------------------------------------
# _load_version
# ---------------------------------------------------------------------------


def test_load_version_falls_back_to_default_when_paths_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both lookups raising yields the hardcoded 0.0.0 default."""
    monkeypatch.setattr(backend_pkg, "Path", _AlwaysRaisingPath)

    assert backend_pkg._load_version() == "0.0.0"


def test_load_version_reads_file_next_to_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no source-tree VERSION, the file next to argv[0] is used."""
    exe_dir = tmp_path / "install"
    exe_dir.mkdir()
    (exe_dir / "VERSION").write_text("9.9.9\n", encoding="utf-8")

    monkeypatch.setattr(
        backend_pkg,
        "Path",
        _redirecting_path(backend_pkg.__file__, _fake_source_init(tmp_path)),
    )
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [str(exe_dir / "EDColonisationAsst.exe")])

    assert backend_pkg._load_version() == "9.9.9"


def test_load_version_frozen_uses_sys_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When sys.frozen is set, the VERSION next to sys.executable wins."""
    exe_dir = tmp_path / "frozen-install"
    exe_dir.mkdir()
    (exe_dir / "VERSION").write_text("7.7.7", encoding="utf-8")

    monkeypatch.setattr(
        backend_pkg,
        "Path",
        _redirecting_path(backend_pkg.__file__, _fake_source_init(tmp_path)),
    )
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "frozen.exe"))

    assert backend_pkg._load_version() == "7.7.7"


def test_load_version_default_when_no_version_files_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing VERSION in both locations yields the 0.0.0 default."""
    exe_dir = tmp_path / "empty-install"
    exe_dir.mkdir()

    monkeypatch.setattr(
        backend_pkg,
        "Path",
        _redirecting_path(backend_pkg.__file__, _fake_source_init(tmp_path)),
    )
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [str(exe_dir / "EDColonisationAsst.exe")])

    assert backend_pkg._load_version() == "0.0.0"


# ---------------------------------------------------------------------------
# _load_build_id
# ---------------------------------------------------------------------------


def test_load_build_id_falls_back_to_empty_when_paths_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both lookups raising yields the empty-string default."""
    monkeypatch.setattr(backend_pkg, "Path", _AlwaysRaisingPath)

    assert backend_pkg._load_build_id() == ""


def test_load_build_id_reads_file_next_to_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no source-tree BUILD_ID, the file next to argv[0] is used."""
    exe_dir = tmp_path / "install"
    exe_dir.mkdir()
    (exe_dir / "BUILD_ID").write_text("build-abc123\n", encoding="utf-8")

    monkeypatch.setattr(
        backend_pkg,
        "Path",
        _redirecting_path(backend_pkg.__file__, _fake_source_init(tmp_path)),
    )
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [str(exe_dir / "EDColonisationAsst.exe")])

    assert backend_pkg._load_build_id() == "build-abc123"


def test_load_build_id_empty_when_no_files_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing BUILD_ID in both locations yields the empty default."""
    exe_dir = tmp_path / "empty-install"
    exe_dir.mkdir()

    monkeypatch.setattr(
        backend_pkg,
        "Path",
        _redirecting_path(backend_pkg.__file__, _fake_source_init(tmp_path)),
    )
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [str(exe_dir / "EDColonisationAsst.exe")])

    assert backend_pkg._load_build_id() == ""


# ---------------------------------------------------------------------------
# runtime.is_frozen defensive path
# ---------------------------------------------------------------------------


def test_runtime_is_frozen_false_when_argv_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An argv[0] that cannot become a Path yields the safe False fallback."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [None])

    assert runtime_mod.is_frozen() is False


# ---------------------------------------------------------------------------
# windows.get_saved_games_path pointer-never-allocated branch
# ---------------------------------------------------------------------------


def test_saved_games_skips_free_when_pointer_never_allocated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If c_wchar_p allocation fails, no free is attempted; fallback is used.

    Forcing ctypes.c_wchar_p to raise leaves the local ptr as None, so the
    finally block must skip CoTaskMemFree and the function must fall back
    to the USERPROFILE-based Saved Games path.
    """

    def _allocation_fails() -> ctypes.c_wchar_p:
        raise RuntimeError("simulated c_wchar_p allocation failure")

    monkeypatch.setattr(windows_mod.ctypes, "c_wchar_p", _allocation_fails)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    result = windows_mod.get_saved_games_path()

    assert result == tmp_path / "Saved Games"


def test_saved_games_userprofile_fallback_without_windll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ctypes.windll the WinAPI block is skipped entirely.

    This is the non-Windows shape of ctypes; the function must go straight
    to the USERPROFILE fallback.
    """
    monkeypatch.delattr(windows_mod.ctypes, "windll", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    result = windows_mod.get_saved_games_path()

    assert result == tmp_path / "Saved Games"
