"""The command seam, the progress reporting, the command line and the crash log.

The runner tests use real commands that do nothing (``cmd /c``), which exercises
the production subprocess path without any mocking library. British spelling is
used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import RecordingProgress

from installer.cli import Options, build_parser, parse_args
from installer.constants import INSTALLER_LOG_NAME, UNINSTALL_FLAG
from installer.ops.commands import (
    FAILED_RETURNCODE,
    CommandResult,
    SubprocessRunner,
    default_runner,
    powershell_command,
)
from installer.ops.progress import (
    COMPLETE_PCT,
    COPY_END_PCT,
    COPY_START_PCT,
    MINIMUM_PCT,
    report,
    scaled,
)
from installer.shared.logging_setup import (
    install_crash_logging,
    installer_log_path,
    write_crash,
)
from installer.shared.resource_path import (
    installer_root,
    launcher_dir,
    program_root,
)

_MISSING_COMMAND = ["edca-no-such-command-exists"]
_TIMEOUT_S = 10.0
_HALF = 50
_WHOLE = 100


def test_report_does_nothing_without_a_reporter() -> None:
    report(None, COMPLETE_PCT, "Done.")


def test_report_forwards_one_update() -> None:
    progress = RecordingProgress()

    report(progress, COPY_START_PCT, "Copying files...")

    assert progress.updates == [(COPY_START_PCT, "Copying files...")]


def test_scaled_maps_progress_into_the_phase_span() -> None:
    assert scaled(MINIMUM_PCT, _WHOLE, COPY_START_PCT, COPY_END_PCT) == COPY_START_PCT
    assert scaled(_WHOLE, _WHOLE, COPY_START_PCT, COPY_END_PCT) == COPY_END_PCT
    assert scaled(_HALF, _WHOLE, COPY_START_PCT, COPY_END_PCT) > COPY_START_PCT


def test_scaled_reports_the_end_of_a_phase_with_nothing_to_do() -> None:
    assert scaled(MINIMUM_PCT, MINIMUM_PCT, COPY_START_PCT, COPY_END_PCT) == (
        COPY_END_PCT
    )


def test_a_result_knows_whether_it_succeeded() -> None:
    assert CommandResult(0, "").ok is True
    assert CommandResult(1, "").ok is False


def test_default_runner_is_the_subprocess_runner() -> None:
    assert isinstance(default_runner(), SubprocessRunner)


def test_powershell_command_runs_a_script_non_interactively() -> None:
    args = powershell_command("$x = 1")

    assert args[0] == "powershell"
    assert "-NoProfile" in args
    assert "-NonInteractive" in args
    assert args[-2:] == ["-Command", "$x = 1"]


def test_powershell_command_can_hide_its_window() -> None:
    args = powershell_command("$x = 1", hidden=True)

    assert "-WindowStyle" in args
    assert "Hidden" in args


def test_the_runner_captures_output_from_a_real_command() -> None:
    result = SubprocessRunner().run(["cmd", "/c", "echo", "hello"], timeout=_TIMEOUT_S)

    assert result.ok is True
    assert "hello" in result.stdout


def test_the_runner_reports_a_command_that_cannot_start() -> None:
    result = SubprocessRunner().run(_MISSING_COMMAND, timeout=_TIMEOUT_S)

    assert result.returncode == FAILED_RETURNCODE
    assert result.ok is False


def test_the_runner_starts_a_detached_command() -> None:
    SubprocessRunner().start_detached(["cmd", "/c", "exit"])


def test_the_runner_is_silent_when_a_detached_command_cannot_start() -> None:
    SubprocessRunner().start_detached(_MISSING_COMMAND)


def test_the_command_line_defaults_to_showing_the_window() -> None:
    assert parse_args([]) == Options(uninstall=False, quiet=False)


def test_the_command_line_reads_the_uninstall_and_quiet_flags() -> None:
    parsed = parse_args([UNINSTALL_FLAG, "--quiet"])

    assert parsed.uninstall is True
    assert parsed.quiet is True


def test_the_parser_offers_help() -> None:
    assert "--uninstall" in build_parser().format_help()


def test_the_crash_log_sits_under_the_temporary_directory() -> None:
    assert installer_log_path().name == INSTALLER_LOG_NAME


def test_write_crash_appends_a_traceback(tmp_path: Path) -> None:
    log_path = tmp_path / "crash.log"
    error = ValueError("broken")

    write_crash(log_path, ValueError, error, None)

    assert "broken" in log_path.read_text(encoding="utf-8")


def test_write_crash_is_silent_when_the_log_cannot_be_opened(tmp_path: Path) -> None:
    """A crash log that cannot be written must not become a second crash."""
    blocked = tmp_path / "a-directory"
    blocked.mkdir()

    write_crash(blocked, ValueError, ValueError("broken"), None)


def test_install_crash_logging_hooks_and_writes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys

    log_path = tmp_path / "crash.log"
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)

    assert install_crash_logging(log_path) == log_path
    sys.excepthook(ValueError, ValueError("broken"), None)

    assert "broken" in log_path.read_text(encoding="utf-8")


def test_install_crash_logging_defaults_to_the_temporary_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)

    assert install_crash_logging() == installer_log_path()


def test_the_package_is_the_anchor_for_bundled_data() -> None:
    assert installer_root().name == "installer"
    assert program_root() == installer_root().parent


def test_the_launcher_directory_is_read_from_the_argument_vector(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sys

    launcher = tmp_path / "Setup.exe"
    monkeypatch.setattr(sys, "argv", [str(launcher)])

    assert launcher_dir() == tmp_path.resolve()


def test_the_launcher_directory_is_none_without_an_argument_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", [])

    assert launcher_dir() is None
