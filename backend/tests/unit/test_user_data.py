"""Tests for the per-user writable directory (src/utils/user_data.py).

Every branch is exercised by setting or clearing the two environment variables
that decide the answer, so no test depends on which platform the suite runs on.
That matters here more than usual: the whole point of the module is that a
Windows machine and a sandboxed Linux one get different answers; a test that
only ever saw one of them would pass on the machine it was written on.
"""

from __future__ import annotations

from pathlib import Path

from src.utils import user_data as user_data_mod


def _clear_location_variables(monkeypatch) -> None:
    """Remove both variables so a branch is chosen by the test, not the host."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)


def test_user_data_dir_prefers_local_appdata(monkeypatch, tmp_path):
    """Windows keeps its existing location, which is what protects a live install."""
    _clear_location_variables(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))

    assert user_data_mod.user_data_dir() == (
        tmp_path / "localappdata" / user_data_mod.APP_DIR_NAME
    )


def test_user_data_dir_prefers_local_appdata_over_xdg(monkeypatch, tmp_path):
    """With both set, LOCALAPPDATA wins.

    A machine can have both: a Windows session with an XDG variable inherited
    from some other tool has to keep the database where Windows already put it.
    """
    _clear_location_variables(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert user_data_mod.user_data_dir() == (
        tmp_path / "localappdata" / user_data_mod.APP_DIR_NAME
    )


def test_user_data_dir_uses_xdg_data_home(monkeypatch, tmp_path):
    """This is the branch a flatpak takes.

    Inside the sandbox XDG_DATA_HOME points at the application's own directory
    under ~/.var/app, which is one of the few places it may write.
    """
    _clear_location_variables(monkeypatch)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert user_data_mod.user_data_dir() == (
        tmp_path / "xdg" / user_data_mod.APP_DIR_NAME
    )


def test_user_data_dir_falls_back_to_the_xdg_default(monkeypatch):
    """With neither variable set, the specification's own default is used."""
    _clear_location_variables(monkeypatch)

    expected = Path.home() / ".local" / "share" / user_data_mod.APP_DIR_NAME
    assert user_data_mod.user_data_dir() == expected


def test_user_data_dir_does_not_create_the_directory(monkeypatch, tmp_path):
    """Reporting a location is not the same as making one.

    The caller that writes there decides whether a failure to create it is
    fatal, so this function stays free of I/O and cannot fail.
    """
    _clear_location_variables(monkeypatch)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    resolved = user_data_mod.user_data_dir()

    assert resolved.exists() is False
