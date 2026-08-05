"""Removing the application, its shortcuts and its registration.

Every location is redirected, so nothing here removes a real installation. In
particular the deferred-deletion test injects the running-inside check rather
than pointing the removal at the directory holding the running interpreter.
British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

from fakes import (
    FakeRunner,
    RecordingProgress,
    idle_result,
    running_result,
)

from installer.constants import APP_SHORT_NAME, EXE_NAME
from installer.ops.progress import COMPLETE_PCT, DELETE_END_PCT
from installer.ops.uninstall_ops import (
    DEFERRED_DELETE_ATTEMPTS,
    deferred_delete_script,
    remove_install_dir,
    schedule_delete_after_exit,
    uninstall,
)
from installer.state.registry import (
    RegistryKeys,
    installed_version,
    is_autostart_enabled,
    set_autostart,
    write_uninstall_entry,
)

_VERSION = "2.9.0"


def _installed(root: Path) -> Path:
    """Stage a small installed tree."""
    root.mkdir(parents=True, exist_ok=True)
    (root / EXE_NAME).write_bytes(b"exe")
    nested = root / "backend"
    nested.mkdir()
    (nested / "main.py").write_text("x", encoding="utf-8")
    return root


def test_the_deferred_script_polls_rather_than_waiting_once(tmp_path: Path) -> None:
    script = deferred_delete_script(tmp_path)

    assert str(tmp_path) in script
    assert f"-lt {DEFERRED_DELETE_ATTEMPTS}" in script
    assert "Remove-Item" in script


def test_the_deferred_script_escapes_a_quote_in_the_path() -> None:
    assert "it''s here" in deferred_delete_script(Path("C:/it's here"))


def test_schedule_delete_after_exit_starts_a_hidden_detached_helper(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()

    schedule_delete_after_exit(tmp_path, runner)

    args, _cwd = runner.detached[0]
    assert args[0] == "powershell"
    assert "Hidden" in args


def test_remove_install_dir_does_nothing_when_it_has_already_gone(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()

    remove_install_dir(tmp_path / "absent", runner)

    assert runner.detached == []


def test_remove_install_dir_deletes_a_directory_it_is_not_running_from(
    tmp_path: Path,
) -> None:
    install_dir = _installed(tmp_path / "installed")
    runner = FakeRunner()

    remove_install_dir(install_dir, runner)

    assert not install_dir.exists()
    assert runner.detached == []


def test_remove_install_dir_defers_when_it_holds_the_running_executable(
    tmp_path: Path,
) -> None:
    """The registered uninstaller cannot delete its own running image."""
    install_dir = _installed(tmp_path / "installed")
    runner = FakeRunner()

    remove_install_dir(install_dir, runner, is_running_inside=lambda _path: True)

    assert len(runner.detached) == 1


def test_remove_install_dir_reports_progress_while_it_deletes(
    tmp_path: Path,
) -> None:
    install_dir = _installed(tmp_path / "installed")
    progress = RecordingProgress()

    remove_install_dir(install_dir, FakeRunner(), progress=progress)

    assert progress.percentages[-1] == DELETE_END_PCT


def test_uninstall_removes_shortcuts_registration_and_files(
    scratch_keys: RegistryKeys, isolated_profile: Path, tmp_path: Path
) -> None:
    install_dir = _installed(tmp_path / "installed")
    write_uninstall_entry(
        install_dir, install_dir / "Setup.exe", _VERSION, keys=scratch_keys
    )
    set_autostart(True, install_dir / EXE_NAME, scratch_keys)
    desktop_link = isolated_profile / "Desktop" / f"{APP_SHORT_NAME}.lnk"
    desktop_link.write_bytes(b"lnk")
    progress = RecordingProgress()

    uninstall(
        progress=progress,
        runner=FakeRunner(default=idle_result()),
        keys=scratch_keys,
    )

    assert not desktop_link.exists()
    assert installed_version(scratch_keys) is None
    assert is_autostart_enabled(scratch_keys) is False
    assert not install_dir.exists()
    assert progress.percentages[-1] == COMPLETE_PCT


def test_uninstall_closes_a_running_application_first(
    scratch_keys: RegistryKeys, isolated_profile: Path, tmp_path: Path
) -> None:
    install_dir = _installed(tmp_path / "installed")
    runner = FakeRunner([running_result(), idle_result()], default=idle_result())

    uninstall(runner=runner, keys=scratch_keys, install_dir=install_dir)

    assert any(args[0] == "taskkill" for args in runner.commands)
    assert not install_dir.exists()


def test_uninstall_uses_the_registered_location_when_none_is_given(
    scratch_keys: RegistryKeys, isolated_profile: Path, tmp_path: Path
) -> None:
    install_dir = _installed(tmp_path / "installed")
    write_uninstall_entry(
        install_dir, install_dir / "Setup.exe", _VERSION, keys=scratch_keys
    )

    uninstall(runner=FakeRunner(default=idle_result()), keys=scratch_keys)

    assert not install_dir.exists()


def test_uninstall_falls_back_to_the_default_location(
    scratch_keys: RegistryKeys, isolated_profile: Path
) -> None:
    """With no registration and nothing at the default there is simply nothing to do."""
    uninstall(runner=FakeRunner(default=idle_result()), keys=scratch_keys)

    assert installed_version(scratch_keys) is None
