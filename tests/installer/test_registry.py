"""The HKCU registrations, exercised against scratch keys.

Every write here goes to a unique test key that the fixture removes afterwards,
so the suite never reads or alters a real EDCA installation. British spelling is
used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

from installer.constants import (
    APP_SHORT_NAME,
    NO_BROWSER_FLAG,
    UNINSTALL_FLAG,
)
from installer.state.registry import (
    DEFAULT_KEYS,
    DISPLAY_ICON,
    DISPLAY_VERSION,
    ESTIMATED_SIZE,
    INSTALL_LOCATION,
    MODIFY_PATH,
    UNINSTALL_STRING,
    RegistryKeys,
    autostart_command,
    delete_key,
    delete_uninstall_entry,
    installed_location,
    installed_version,
    is_autostart_enabled,
    read_string,
    set_autostart,
    write_uninstall_entry,
)

# Longer than the 255 characters a registry key name allows, so creating it
# fails and the guard around the write is exercised.
_OVERLONG_KEY = "EDColonisationAsstTests" + ("x" * 300)
_VERSION = "2.9.0"
_ESTIMATED_KB = 2048


def _read_dword(key: str, name: str) -> int:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as handle:
        return int(winreg.QueryValueEx(handle, name)[0])


def test_read_string_returns_none_for_an_absent_key() -> None:
    assert read_string(r"Software\EDColonisationAsstTests\NotThere", "X") is None


def test_write_uninstall_entry_records_the_installation(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    uninstaller = tmp_path / "_uninstall" / "Setup.exe"
    icon = tmp_path / "app.ico"

    write_uninstall_entry(
        tmp_path,
        uninstaller,
        _VERSION,
        display_icon=icon,
        estimated_kb=_ESTIMATED_KB,
        keys=scratch_keys,
    )

    key = scratch_keys.uninstall_key
    assert read_string(key, DISPLAY_VERSION) == _VERSION
    assert read_string(key, INSTALL_LOCATION) == str(tmp_path)
    assert read_string(key, UNINSTALL_STRING) == f'"{uninstaller}" {UNINSTALL_FLAG}'
    assert read_string(key, MODIFY_PATH) == f'"{uninstaller}"'
    assert read_string(key, DISPLAY_ICON) == str(icon)
    assert _read_dword(key, ESTIMATED_SIZE) == _ESTIMATED_KB


def test_write_uninstall_entry_without_an_icon_or_a_size(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    write_uninstall_entry(tmp_path, tmp_path / "Setup.exe", _VERSION, keys=scratch_keys)

    assert read_string(scratch_keys.uninstall_key, DISPLAY_ICON) == str(tmp_path)
    assert read_string(scratch_keys.uninstall_key, ESTIMATED_SIZE) is None


def test_installed_version_and_location_round_trip(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    write_uninstall_entry(tmp_path, tmp_path / "Setup.exe", _VERSION, keys=scratch_keys)

    assert installed_version(scratch_keys) == _VERSION
    assert installed_location(scratch_keys) == tmp_path


def test_installed_version_and_location_are_none_when_nothing_is_recorded(
    scratch_keys: RegistryKeys,
) -> None:
    assert installed_version(scratch_keys) is None
    assert installed_location(scratch_keys) is None


def test_installed_location_rejects_a_relative_recorded_path(
    scratch_keys: RegistryKeys,
) -> None:
    """A relative value would become the current directory, which is dangerous."""
    write_uninstall_entry(
        Path("relative"), Path("Setup.exe"), _VERSION, keys=scratch_keys
    )

    assert installed_location(scratch_keys) is None


def test_delete_uninstall_entry_removes_the_registration(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    write_uninstall_entry(tmp_path, tmp_path / "Setup.exe", _VERSION, keys=scratch_keys)

    delete_uninstall_entry(scratch_keys)

    assert installed_version(scratch_keys) is None


def test_delete_key_is_silent_when_the_key_is_already_gone() -> None:
    delete_key(r"Software\EDColonisationAsstTests\NeverExisted")


def test_the_autostart_command_starts_the_runtime_without_a_browser(
    tmp_path: Path,
) -> None:
    exe = tmp_path / "app.exe"

    assert autostart_command(exe) == f'"{exe}" {NO_BROWSER_FLAG}'


def test_autostart_can_be_enabled_then_disabled(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    exe = tmp_path / "app.exe"

    set_autostart(True, exe, scratch_keys)
    assert is_autostart_enabled(scratch_keys) is True
    assert read_string(scratch_keys.run_subkey, scratch_keys.run_value) == (
        autostart_command(exe)
    )

    set_autostart(False, exe, scratch_keys)
    assert is_autostart_enabled(scratch_keys) is False


def test_disabling_autostart_that_was_never_set_is_silent(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    set_autostart(False, tmp_path / "app.exe", scratch_keys)

    assert is_autostart_enabled(scratch_keys) is False


def test_autostart_is_silent_when_the_key_cannot_be_created(tmp_path: Path) -> None:
    keys = RegistryKeys(run_subkey=_OVERLONG_KEY)

    set_autostart(True, tmp_path / "app.exe", keys)

    assert is_autostart_enabled(keys) is False


def test_the_default_keys_name_the_real_registrations() -> None:
    """The shipped defaults are the real per-user locations, not a test set."""
    assert DEFAULT_KEYS.uninstall_key.endswith(rf"Uninstall\{APP_SHORT_NAME}")
    assert DEFAULT_KEYS.run_value == APP_SHORT_NAME
    assert DEFAULT_KEYS.run_subkey.endswith("CurrentVersion\\Run")
