"""Coverage tests for src/config.py.

These tests target the code paths the behavioural suite does not reach:
frozen-runtime detection edge cases, the per-user config directory helper
on every platform combination, the argv fallback in get_config_paths and
the defensive YAML plus journal auto-detection branches in get_config.

Only pytest monkeypatch, real tmp_path files and hand-written values are
used; no mock libraries.

Platform note: on Python 3.13 the pathlib.Path constructor dispatches on
os.name at call time, so tests that patch os.name also patch the Path
name inside src.config with the concrete class for the real platform.
That keeps path arithmetic working while the os.name branches under test
still take the patched direction. src.utils.journal is imported at module
scope so its module-level Path arithmetic runs before any os.name patch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import src.config as config_mod
import src.utils.journal as journal_mod

# The concrete Path class for the machine actually running the tests.
# Substituting this for src.config.Path lets path arithmetic succeed even
# while os.name is patched to the other platform's value.
_ConcretePath = type(Path())


def _pin_concrete_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin src.config's Path name to the real platform's concrete class."""
    monkeypatch.setattr(config_mod, "Path", _ConcretePath)


# ---------------------------------------------------------------------------
# _is_frozen
# ---------------------------------------------------------------------------


def test_is_frozen_true_when_sys_frozen_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truthy sys.frozen flag marks the process as frozen."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert config_mod._is_frozen() is True


def test_is_frozen_true_for_non_python_exe_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-Python .exe in argv[0] marks the process as frozen."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["C:/apps/EDColonisationAsst.exe"])

    assert config_mod._is_frozen() is True


def test_is_frozen_false_for_python_exe_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """python.exe in argv[0] is treated as a normal interpreter run."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", ["C:/venv/Scripts/python.exe"])

    assert config_mod._is_frozen() is False


def test_is_frozen_false_when_argv_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An argv[0] that cannot become a Path yields the safe False fallback."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [None])

    assert config_mod._is_frozen() is False


# ---------------------------------------------------------------------------
# _get_user_config_dir
# ---------------------------------------------------------------------------


def test_user_config_dir_windows_with_appdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On Windows the config dir lives under APPDATA when it is set."""
    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "nt", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert config_mod._get_user_config_dir() == tmp_path / "EDColonisationAsst"


def test_user_config_dir_windows_without_appdata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without APPDATA the Windows config dir falls back to Roaming."""
    # Compute the expectation before patching os.name; pathlib dispatches
    # on os.name at call time on Python 3.13.
    expected = Path.home() / "AppData" / "Roaming" / "EDColonisationAsst"

    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "nt", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    assert config_mod._get_user_config_dir() == expected


def test_user_config_dir_posix_with_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On POSIX the config dir honours XDG_CONFIG_HOME when it is set."""
    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert config_mod._get_user_config_dir() == tmp_path / "EDColonisationAsst"


def test_user_config_dir_posix_without_xdg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without XDG_CONFIG_HOME the POSIX config dir falls back to ~/.config."""
    # Compute the expectation before patching os.name; pathlib dispatches
    # on os.name at call time on Python 3.13.
    expected = Path.home() / ".config" / "EDColonisationAsst"

    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert config_mod._get_user_config_dir() == expected


# ---------------------------------------------------------------------------
# get_config_paths fallback
# ---------------------------------------------------------------------------


def test_get_config_paths_frozen_argv_error_falls_back_to_source_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When frozen but argv[0] is unusable, the source layout is used."""
    monkeypatch.setattr(config_mod, "_is_frozen", lambda: True)
    monkeypatch.setattr(sys, "argv", [None])

    config_path, commander_path = config_mod.get_config_paths()

    expected_base = Path(config_mod.__file__).resolve().parents[2]
    assert config_path == expected_base / "config.yaml"
    assert commander_path == expected_base / "commander.yaml"


# ---------------------------------------------------------------------------
# get_config defensive branches
# ---------------------------------------------------------------------------


def _point_config_at(
    monkeypatch: pytest.MonkeyPatch, config_file: Path, commander_file: Path
) -> None:
    """Route get_config at specific files and clear the cached instance."""
    monkeypatch.setattr(
        config_mod, "get_config_paths", lambda: (config_file, commander_file)
    )
    monkeypatch.setattr(config_mod, "_config", None)


def test_get_config_missing_files_uses_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nonexistent config and commander files produce a default AppConfig."""
    _point_config_at(
        monkeypatch, tmp_path / "no-config.yaml", tmp_path / "no-commander.yaml"
    )

    cfg = config_mod.get_config()

    assert cfg.server.port == 8000
    assert cfg.websocket.ping_interval == 30
    assert cfg.logging.level == "INFO"


def test_get_config_invalid_yaml_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unparseable YAML in either file must not crash config loading."""
    config_file = tmp_path / "config.yaml"
    commander_file = tmp_path / "commander.yaml"
    # An unterminated flow mapping is guaranteed-invalid YAML.
    config_file.write_text("{\n", encoding="utf-8")
    commander_file.write_text("{\n", encoding="utf-8")
    _point_config_at(monkeypatch, config_file, commander_file)

    cfg = config_mod.get_config()

    assert cfg.server.port == 8000
    assert cfg.logging.level == "INFO"


def _write_windows_default_config(tmp_path: Path) -> tuple[Path, Path]:
    """Write a config whose journal dir looks like the Windows default."""
    config_file = tmp_path / "config.yaml"
    commander_file = tmp_path / "commander.yaml"
    config_file.write_text(
        "journal:\n  directory: 'C:/EDCA-Coverage-Missing/Journals'\n",
        encoding="utf-8",
    )
    commander_file.write_text("", encoding="utf-8")
    return config_file, commander_file


def test_get_config_posix_autodetect_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When detection finds nothing, the configured directory is kept."""
    config_file, commander_file = _write_windows_default_config(tmp_path)
    _point_config_at(monkeypatch, config_file, commander_file)
    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)
    monkeypatch.setattr(journal_mod, "find_journal_directory", lambda: None)

    cfg = config_mod.get_config()

    assert cfg.journal.directory == "C:/EDCA-Coverage-Missing/Journals"


def test_get_config_posix_autodetect_exception_is_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A crashing detector never blocks startup; the config value survives."""
    config_file, commander_file = _write_windows_default_config(tmp_path)
    _point_config_at(monkeypatch, config_file, commander_file)
    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)

    def _boom() -> Path:
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(journal_mod, "find_journal_directory", _boom)

    cfg = config_mod.get_config()

    assert cfg.journal.directory == "C:/EDCA-Coverage-Missing/Journals"


def test_get_config_posix_custom_path_is_not_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit POSIX-style path skips auto-detection even if missing."""
    config_file = tmp_path / "config.yaml"
    commander_file = tmp_path / "commander.yaml"
    config_file.write_text(
        "journal:\n  directory: '/definitely/missing/posix/journals'\n",
        encoding="utf-8",
    )
    commander_file.write_text("", encoding="utf-8")
    _point_config_at(monkeypatch, config_file, commander_file)
    _pin_concrete_path(monkeypatch)
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)

    detected = tmp_path / "should-not-be-used"
    detected.mkdir()
    monkeypatch.setattr(journal_mod, "find_journal_directory", lambda: detected)

    cfg = config_mod.get_config()

    assert cfg.journal.directory == "/definitely/missing/posix/journals"
