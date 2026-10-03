"""Where a packaged runtime keeps config.yaml.

The installed Windows runtime is a plain interpreter over plain sources, so it
is neither frozen nor a flatpak; it used to read and write
`<install>\\backend\\config.yaml`. The runtime archive ships that same file and
the setup program overwrites every member on an upgrade, reinstall or repair,
so every one of those lost the saved journal folder and any host, port or CORS
edit; a user who had closed LAN access was put back on 0.0.0.0. A packaged
runtime of any kind now keeps its configuration in the per-user configuration
folder, which no installer writes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import src.config as config_mod

_APP_DIR = "EDColonisationAsst"
_INSTALL_TREE = Path(config_mod.__file__).resolve().parents[1]


@pytest.fixture
def user_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point both per-user configuration bases at a temporary directory."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.delenv("EDCA_PACKAGED", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    return tmp_path / _APP_DIR


def test_an_installed_deployment_keeps_config_outside_the_install(
    user_config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EDCA_PACKAGED", "1")

    config_path, commander_path = config_mod.get_config_paths()

    assert config_path == user_config_home / "config.yaml"
    assert commander_path == user_config_home / "commander.yaml"
    assert _INSTALL_TREE not in config_path.parents


def test_a_frozen_runtime_keeps_config_outside_the_install(
    user_config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    config_path, _commander_path = config_mod.get_config_paths()

    assert config_path == user_config_home / "config.yaml"


def test_a_source_checkout_keeps_its_own_backend_config(
    user_config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["pytest"])

    config_path, _commander_path = config_mod.get_config_paths()

    assert config_path == _INSTALL_TREE / "config.yaml"
