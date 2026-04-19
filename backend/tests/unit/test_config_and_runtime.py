"""Tests for configuration and runtime detection utilities (no external mocking frameworks)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import src.config as config_mod
from src.utils import runtime as runtime_mod
import src as backend_pkg


# ---------------------------------------------------------------------------
# Runtime detection tests (src/utils/runtime.py)
# ---------------------------------------------------------------------------


def test_runtime_is_frozen_false_by_default():
    """Default environment (no sys.frozen, python.exe argv[0]) should be treated as DEV."""
    orig_frozen = getattr(sys, "frozen", None)
    orig_argv0 = sys.argv[0]
    try:
        # Ensure sys.frozen is absent/false
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")
        # Simulate normal interpreter invocation
        sys.argv[0] = str(Path(sys.executable))

        assert runtime_mod.is_frozen() is False
        assert runtime_mod.get_runtime_mode() == runtime_mod.RuntimeMode.DEV
    finally:
        sys.argv[0] = orig_argv0
        if orig_frozen is not None:
            setattr(sys, "frozen", orig_frozen)
        elif hasattr(sys, "frozen"):
            delattr(sys, "frozen")


def test_runtime_is_frozen_when_sys_frozen_flag():
    """When sys.frozen is truthy, is_frozen and get_runtime_mode should report FROZEN."""
    orig_frozen = getattr(sys, "frozen", None)
    try:
        sys.frozen = True  # type: ignore[attr-defined]
        assert runtime_mod.is_frozen() is True
        assert runtime_mod.get_runtime_mode() == runtime_mod.RuntimeMode.FROZEN
    finally:
        if orig_frozen is not None:
            sys.frozen = orig_frozen  # type: ignore[attr-defined]
        elif hasattr(sys, "frozen"):
            delattr(sys, "frozen")


def test_runtime_is_frozen_for_non_python_exe_path():
    """A non-Python .exe in argv[0] should also be treated as frozen."""
    orig_frozen = getattr(sys, "frozen", None)
    orig_argv0 = sys.argv[0]
    try:
        # Ensure primary frozen flag is not set so we exercise the fallback branch
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")

        sys.argv[0] = str(Path("C:/Games/EDColonisationAsst.exe"))
        assert runtime_mod.is_frozen() is True
    finally:
        sys.argv[0] = orig_argv0
        if orig_frozen is not None:
            setattr(sys, "frozen", orig_frozen)
        elif hasattr(sys, "frozen"):
            delattr(sys, "frozen")


# ---------------------------------------------------------------------------
# Config path and loading tests (src/config.py)
# ---------------------------------------------------------------------------


def test_get_config_paths_dev_uses_backend_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In non-frozen mode, get_config_paths should resolve backend/config.yaml layout."""
    monkeypatch.setattr(config_mod, "_is_frozen", lambda: False)

    config_path, commander_path = config_mod.get_config_paths()

    base_dir = Path(config_mod.__file__).parent.parent  # backend/
    assert config_path == base_dir / "config.yaml"
    assert commander_path == base_dir / "commander.yaml"


def test_get_config_paths_frozen_uses_exe_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In frozen mode, get_config_paths should place config next to the executable."""
    exe = tmp_path / "EDColonisationAsst.exe"
    exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(config_mod, "_is_frozen", lambda: True)
    orig_argv0 = sys.argv[0]
    sys.argv[0] = str(exe)
    try:
        config_path, commander_path = config_mod.get_config_paths()
    finally:
        sys.argv[0] = orig_argv0

    assert config_path.parent == exe.parent
    assert commander_path.parent == exe.parent
    assert config_path.name == "config.yaml"
    assert commander_path.name == "commander.yaml"


def test_get_config_loads_yaml_and_commander_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    get_config should load config.yaml and commander.yaml once and cache the result.

    Subsequent calls must return the same AppConfig instance without re-reading files.
    """
    config_file = tmp_path / "config.yaml"
    commander_file = tmp_path / "commander.yaml"

    config_file.write_text(
        (
            "journal:\n"
            "  directory: /tmp/journals\n"
            "server:\n"
            "  host: 127.0.0.1\n"
            "  port: 1234\n"
            "websocket:\n"
            "  ping_interval: 10\n"
            "logging:\n"
            "  level: DEBUG\n"
        ),
        encoding="utf-8",
    )

    commander_file.write_text(
        (
            "inara:\n"
            "  api_key: KEY\n"
            "  commander_name: CMDR Test\n"
            "  app_name: EDCA Test\n"
            "  prefer_local_for_commander_systems: false\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        config_mod,
        "get_config_paths",
        lambda: (config_file, commander_file),
    )

    orig_config = config_mod._config
    try:
        config_mod._config = None

        cfg1 = config_mod.get_config()
        assert cfg1.journal.directory == os.path.expandvars("/tmp/journals")
        assert cfg1.server.host == "127.0.0.1"
        assert cfg1.server.port == 1234
        assert cfg1.websocket.ping_interval == 10
        assert cfg1.logging.level == "DEBUG"

        assert cfg1.inara.api_key == "KEY"
        assert cfg1.inara.commander_name == "CMDR Test"
        assert cfg1.inara.app_name == "EDCA Test"
        assert cfg1.inara.prefer_local_for_commander_systems is False

        # Second call should return the same object instance (cached)
        cfg2 = config_mod.get_config()
        assert cfg2 is cfg1
    finally:
        config_mod._config = orig_config


def test_get_config_linux_autodetect_overrides_windows_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    On non-Windows platforms, a Windows-style default journal path should be
    replaced by find_journal_directory() when the path does not exist.

    This behaviour is Linux-specific; on Windows the journal directory is
    resolved via utils.windows instead, so this test is skipped there.
    """
    config_file = tmp_path / "config.yaml"
    commander_file = tmp_path / "commander.yaml"

    # Use a Windows-style default path that is guaranteed to be missing on the
    # current machine.
    #
    # Important: write YAML using forward slashes + single quotes so the YAML
    # is valid on all platforms. Double-quoted Windows paths with backslashes
    # can be invalid YAML (e.g. "\U" unicode escapes), and config.get_config()
    # intentionally falls back to defaults on YAML parse errors.
    win_default = (
        "C:/Users/%USERNAME%/Saved Games/Frontier Developments/Elite Dangerous/__edca_test_missing__"
    )
    config_file.write_text(
        f"journal:\n  directory: '{win_default}'\n",
        encoding="utf-8",
    )
    commander_file.write_text("", encoding="utf-8")

    detected_dir = tmp_path / "journals"
    detected_dir.mkdir()

    # Make get_config_paths point at our temp files.
    monkeypatch.setattr(
        config_mod,
        "get_config_paths",
        lambda: (config_file, commander_file),
    )
    # Pretend we're on a non-Windows platform inside this test.
    monkeypatch.setattr(config_mod.os, "name", "posix", raising=False)

    # Ensure the internal auto-detection helper used by config.get_config()
    # returns our detected_dir. The helper lives in src.utils.journal.
    import src.utils.journal as journal_mod  # local import to patch the correct module

    monkeypatch.setattr(
        journal_mod,
        "find_journal_directory",
        lambda: detected_dir,
    )

    orig_config = config_mod._config
    try:
        config_mod._config = None
        cfg = config_mod.get_config()
        assert cfg.journal.directory == str(detected_dir)
    finally:
        config_mod._config = orig_config


def test_set_config_overrides_global_and_get_config_returns_it() -> None:
    """set_config should replace the global AppConfig instance used by get_config."""
    orig_config = config_mod._config
    try:
        new_cfg = config_mod.AppConfig()
        config_mod.set_config(new_cfg)
        assert config_mod.get_config() is new_cfg
    finally:
        config_mod._config = orig_config


# ---------------------------------------------------------------------------
# Package version loading (src/__init__.py)
# ---------------------------------------------------------------------------


def test_package_version_is_non_empty_and_matches_loaded_version() -> None:
    """
    The backend package should expose a non-empty __version__ string
    obtained via _load_version().
    """
    # Accessing the private helper ensures we execute the version resolution
    # logic at least once under tests.
    version_from_helper = backend_pkg._load_version()  # type: ignore[attr-defined]
    assert isinstance(version_from_helper, str)
    assert version_from_helper != ""

    assert isinstance(backend_pkg.__version__, str)
    assert backend_pkg.__version__ == version_from_helper
