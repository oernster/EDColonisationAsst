"""Debug logging and the launcher's preparation steps.

Split out of test_runtime_components.py; the scaffolding lives in _test_runtime_components_support.py.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
import src.runtime.common as runtime_common
import src.runtime.launcher_components as launcher_mod

from tests.unit._test_runtime_components_support import (
    DummyCompletedProcess,
    DummyView,
)


def test_debug_log_creates_log_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    _debug_log should append a line to EDColonisationAsst-runtime.log next to argv[0].
    """
    exe = tmp_path / "EDColonisationAsst.exe"
    exe.write_text("", encoding="utf-8")

    orig_argv0 = sys.argv[0]
    try:
        sys.argv[0] = str(exe)
        runtime_common._debug_log("hello runtime")  # type: ignore[attr-defined]
    finally:
        sys.argv[0] = orig_argv0

    log_path = tmp_path / "EDColonisationAsst-runtime.log"
    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8")
    assert "hello runtime" in contents


def test_debug_log_ignores_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Any exception raised while writing the debug log must be swallowed.
    """

    def failing_open(*args: Any, **kwargs: Any):
        raise OSError("cannot open log")

    # Force Path.open used inside runtime_common to fail.
    monkeypatch.setattr(runtime_common.Path, "open", failing_open)
    # Also ensure argv[0] points somewhere Path can resolve.
    monkeypatch.setattr(sys, "argv", ["dummy-exe"])

    # Should not raise despite our failing Path.open override.
    runtime_common._debug_log("this will not be written")  # type: ignore[attr-defined]


def test_launcher_check_python_logs_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    _check_python should run 'python --version' and append the output to the log.
    """
    project_root = tmp_path
    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)

    called: Dict[str, bool | str] = {}

    def fake_run(cmd: List[str], stdout, stderr, text, check):  # type: ignore[no-untyped-def]
        called["cmd"] = " ".join(cmd)
        return DummyCompletedProcess(stdout="Python 3.13.11")

    monkeypatch.setattr(launcher_mod.subprocess, "run", fake_run)

    launcher._check_python()  # type: ignore[attr-defined]

    assert called["cmd"] == "python --version"
    # Log file should contain our version string.
    log_path = project_root / "run-edca.log"
    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8")
    assert "Python 3.13.11" in contents


def test_launcher_install_backend_deps_missing_venv_is_fatal(
    tmp_path: Path,
) -> None:
    """
    If venv python is missing, _install_backend_deps should raise a RuntimeError.
    """
    project_root = tmp_path
    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)

    # Ensure venv python path does not exist and requirements.txt location will be used.
    assert not launcher._venv_python.exists()  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        launcher._install_backend_deps()  # type: ignore[attr-defined]


def test_launcher_install_backend_deps_missing_requirements_is_non_fatal(
    tmp_path: Path,
) -> None:
    """
    If backend/requirements.txt is missing, _install_backend_deps should log and return.
    """
    project_root = tmp_path
    backend_dir = project_root / "backend"
    backend_dir.mkdir()
    # Create a fake venv python so that we do not hit the "missing venv" branch.
    venv_dir = backend_dir / "venv" / "Scripts"
    venv_dir.mkdir(parents=True)
    venv_python = venv_dir / "python.exe"
    venv_python.write_text("", encoding="utf-8")

    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)

    # Point the launcher's paths at our fake locations.
    launcher._backend_dir = backend_dir  # type: ignore[attr-defined]
    launcher._venv_python = venv_python  # type: ignore[attr-defined]

    launcher._install_backend_deps()  # type: ignore[attr-defined]
    # No exception should be raised and log file should note the missing requirements.
    log_path = project_root / "run-edca.log"
    contents = log_path.read_text(encoding="utf-8")
    assert "backend/requirements.txt not found" in contents


def test_launcher_install_backend_deps_logs_warning_on_pip_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    If pip install fails, _install_backend_deps should log a warning and continue.
    """
    project_root = tmp_path
    backend_dir = project_root / "backend"
    backend_dir.mkdir()
    venv_dir = backend_dir / "venv" / "Scripts"
    venv_dir.mkdir(parents=True)
    venv_python = venv_dir / "python.exe"
    venv_python.write_text("", encoding="utf-8")
    requirements = backend_dir / "requirements.txt"
    requirements.write_text("pytest\n", encoding="utf-8")

    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)
    launcher._backend_dir = backend_dir  # type: ignore[attr-defined]
    launcher._venv_python = venv_python  # type: ignore[attr-defined]

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("pip exploded")

    monkeypatch.setattr(launcher, "_run_subprocess", boom, raising=True)  # type: ignore[attr-defined]

    launcher._install_backend_deps()  # type: ignore[attr-defined]

    log_path = project_root / "run-edca.log"
    contents = log_path.read_text(encoding="utf-8")
    assert "WARNING: Backend dependency installation failed" in contents


def test_launcher_wait_for_readiness_times_out_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    _wait_for_readiness should time out and log a message when endpoints never respond.

    We simulate time advancing past the deadline and stub out sleep() so the test
    completes quickly without real-world delays.
    """
    project_root = tmp_path
    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)

    # Simulate time advancing beyond the 60s deadline used in _wait_for_readiness.
    start = 1000.0
    # Values: first few iterations below deadline, then one above to force exit.
    time_values = iter([start, start + 10.0, start + 30.0, start + 61.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:
            # Once exhausted, keep returning a value beyond the deadline.
            return start + 61.0

    monkeypatch.setattr(launcher_mod.time, "time", fake_time)
    # Avoid real sleeping in the loop.
    monkeypatch.setattr(launcher_mod.time, "sleep", lambda _secs: None)

    # Ensure _probe always fails by patching urllib.request.urlopen to raise.
    import urllib.error as url_error
    import urllib.request as url_req

    def failing_urlopen(*_args: Any, **_kwargs: Any):
        raise url_error.URLError("nope")

    monkeypatch.setattr(url_req, "urlopen", failing_urlopen)

    launcher._wait_for_readiness()  # type: ignore[attr-defined]

    # The timeout log entry should be present.
    log_path = project_root / "run-edca.log"
    contents = log_path.read_text(encoding="utf-8")
    assert "Timeout waiting for backend/frontend readiness" in contents
