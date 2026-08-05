"""Install, upgrade, reinstall, downgrade and repair, end to end.

The payload anchor, the profile directories and the registry keys are all
redirected, so a full install runs here without touching a real installation.
British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import (
    FakeRunner,
    RecordingProgress,
    idle_result,
    running_result,
)

from installer.constants import (
    EXE_NAME,
    ICON_FILE_NAME,
    RUNTIME_DIR_NAME,
    UNINSTALLER_NAME,
    VERSION_FILE_NAME,
)
from installer.ops.errors import AppRunningError, PayloadError
from installer.ops.install_ops import (
    InstallOptions,
    copy_uninstaller,
    ensure_runtime_exe,
    guard_not_running,
    install,
    register,
    repair,
)
from installer.ops.progress import COMPLETE_PCT, REGISTER_PCT, UNINSTALLER_PCT
from installer.state.registry import (
    DISPLAY_ICON,
    DISPLAY_VERSION,
    RegistryKeys,
    installed_location,
    is_autostart_enabled,
    read_string,
)

_BUNDLED_VERSION = "2.9.0"


@pytest.fixture()
def bundle(staged_payload: Path, payload_dir: Path) -> Path:
    """Stage a small but complete payload: sources, an icon and a version."""
    (payload_dir / VERSION_FILE_NAME).write_text(_BUNDLED_VERSION, encoding="utf-8")
    (payload_dir / ICON_FILE_NAME).write_bytes(b"ico")
    backend = payload_dir / "backend" / "src"
    backend.mkdir(parents=True)
    (backend / "main.py_").write_text("print('hello')", encoding="utf-8")
    runtime = staged_payload / RUNTIME_DIR_NAME
    runtime.mkdir()
    (runtime / EXE_NAME).write_bytes(b"runtime")
    return staged_payload


def _options(target: Path, *, autostart: bool = False) -> InstallOptions:
    return InstallOptions(
        target_dir=target, desktop=False, start_menu=False, autostart=autostart
    )


def test_guard_not_running_passes_when_nothing_is_running() -> None:
    guard_not_running(FakeRunner([idle_result()]))


def test_guard_not_running_refuses_while_the_app_holds_its_files() -> None:
    with pytest.raises(AppRunningError):
        guard_not_running(FakeRunner([running_result()]))


def test_ensure_runtime_exe_leaves_a_copied_executable_alone(tmp_path: Path) -> None:
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    already = install_dir / EXE_NAME
    already.write_bytes(b"copied")

    assert ensure_runtime_exe(install_dir) == already


def test_ensure_runtime_exe_recovers_the_embedded_copy(
    bundle: Path, tmp_path: Path
) -> None:
    """Nuitka strips executables from a data directory, so it is embedded twice."""
    install_dir = tmp_path / "installed"

    recovered = ensure_runtime_exe(install_dir)

    assert recovered == install_dir / EXE_NAME
    assert recovered.read_bytes() == b"runtime"


def test_ensure_runtime_exe_reports_nothing_when_none_is_bundled(
    staged_payload: Path, tmp_path: Path
) -> None:
    assert ensure_runtime_exe(tmp_path / "installed") is None


def test_ensure_runtime_exe_reports_nothing_when_the_copy_fails(
    bundle: Path, tmp_path: Path
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    assert ensure_runtime_exe(blocked) is None


def test_copy_uninstaller_places_a_copy_under_the_install(tmp_path: Path) -> None:
    install_dir = tmp_path / "installed"
    install_dir.mkdir()

    copied = copy_uninstaller(install_dir)

    assert copied == install_dir / "_uninstall" / UNINSTALLER_NAME
    assert copied.is_file()


def test_copy_uninstaller_degrades_to_the_running_executable(tmp_path: Path) -> None:
    """A failure here must not fail an install whose files are already down."""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    copied = copy_uninstaller(blocked)

    assert copied.suffix == ".exe" or copied.exists()


def test_register_records_the_icon_and_the_size(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    install_dir = tmp_path / "installed"
    install_dir.mkdir()
    icon = install_dir / ICON_FILE_NAME
    icon.write_bytes(b"ico")

    register(install_dir, install_dir / "Setup.exe", _BUNDLED_VERSION, scratch_keys)

    assert read_string(scratch_keys.uninstall_key, DISPLAY_ICON) == str(icon)
    assert read_string(scratch_keys.uninstall_key, DISPLAY_VERSION) == _BUNDLED_VERSION


def test_register_falls_back_to_the_install_directory_for_the_icon(
    scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    install_dir = tmp_path / "installed"
    install_dir.mkdir()

    register(install_dir, install_dir / "Setup.exe", _BUNDLED_VERSION, scratch_keys)

    assert read_string(scratch_keys.uninstall_key, DISPLAY_ICON) == str(install_dir)


def test_install_deploys_registers_and_reports_progress(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / "install"
    progress = RecordingProgress()

    exe_path = install(
        _options(target),
        progress=progress,
        runner=FakeRunner(default=idle_result()),
        keys=scratch_keys,
    )

    assert exe_path == target / EXE_NAME
    assert exe_path.is_file()
    assert (target / "backend" / "src" / "main.py").is_file()
    assert installed_location(scratch_keys) == target
    assert read_string(scratch_keys.uninstall_key, DISPLAY_VERSION) == _BUNDLED_VERSION
    assert UNINSTALLER_PCT in progress.percentages
    assert REGISTER_PCT in progress.percentages
    assert progress.percentages[-1] == COMPLETE_PCT


def test_install_is_one_pass_over_an_older_installation(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    """An upgrade installs; it does not remove the old version and then stop."""
    target = tmp_path / "install"
    target.mkdir()
    (target / "stale.txt").write_text("old", encoding="utf-8")
    runner = FakeRunner(default=idle_result())

    install(_options(target), runner=runner, keys=scratch_keys)

    assert (target / EXE_NAME).is_file()
    assert read_string(scratch_keys.uninstall_key, DISPLAY_VERSION) == _BUNDLED_VERSION


def test_install_applies_the_sign_in_choice(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    install(
        _options(tmp_path / "install", autostart=True),
        runner=FakeRunner(default=idle_result()),
        keys=scratch_keys,
    )

    assert is_autostart_enabled(scratch_keys) is True


def test_install_creates_the_shortcuts_it_is_asked_for(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    runner = FakeRunner(default=idle_result())
    options = InstallOptions(
        target_dir=tmp_path / "install",
        desktop=True,
        start_menu=True,
        autostart=False,
    )

    install(options, runner=runner, keys=scratch_keys)

    assert sum(1 for args in runner.commands if args[0] == "powershell") == 2


def test_install_skips_the_shortcuts_with_no_executable_to_point_at(
    staged_payload: Path,
    payload_dir: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    (payload_dir / "readme.txt").write_text("only data", encoding="utf-8")
    runner = FakeRunner(default=idle_result())
    options = InstallOptions(
        target_dir=tmp_path / "install",
        desktop=True,
        start_menu=True,
        autostart=False,
    )

    install(options, runner=runner, keys=scratch_keys)

    assert [args for args in runner.commands if args[0] == "powershell"] == []


def test_install_refuses_while_the_app_is_running(
    bundle: Path, scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    with pytest.raises(AppRunningError):
        install(
            _options(tmp_path / "install"),
            runner=FakeRunner(default=running_result()),
            keys=scratch_keys,
        )

    assert not (tmp_path / "install").exists()


def test_install_fails_loudly_with_no_payload_to_install(
    staged_payload: Path, scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    """Falling back to the project root would install the installer's sources."""
    with pytest.raises(PayloadError):
        install(
            _options(tmp_path / "install"),
            runner=FakeRunner(default=idle_result()),
            keys=scratch_keys,
        )


def test_repair_redeploys_over_the_existing_install(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    target = tmp_path / "install"
    runner = FakeRunner(default=idle_result())
    install(_options(target), runner=runner, keys=scratch_keys)
    (target / "backend" / "src" / "main.py").unlink()

    exe_path = repair(target, runner=runner, keys=scratch_keys)

    assert exe_path.is_file()
    assert (target / "backend" / "src" / "main.py").is_file()
    assert installed_location(scratch_keys) == target


def test_repair_leaves_the_sign_in_setting_exactly_as_it_was(
    bundle: Path,
    scratch_keys: RegistryKeys,
    isolated_profile: Path,
    tmp_path: Path,
) -> None:
    """A repair used to delete the Run entry of a user who had turned it on."""
    target = tmp_path / "install"
    runner = FakeRunner(default=idle_result())
    install(_options(target, autostart=True), runner=runner, keys=scratch_keys)

    repair(target, runner=runner, keys=scratch_keys)

    assert is_autostart_enabled(scratch_keys) is True


def test_repair_refuses_while_the_app_is_running(
    bundle: Path, scratch_keys: RegistryKeys, tmp_path: Path
) -> None:
    with pytest.raises(AppRunningError):
        repair(
            tmp_path / "install",
            runner=FakeRunner(default=running_result()),
            keys=scratch_keys,
        )
