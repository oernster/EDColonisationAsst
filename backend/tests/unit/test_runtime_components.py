from __future__ import annotations

"""
Additional tests for the runtime stack:

- src.runtime.common
- src.runtime.launcher_components
- src.runtime.tray_components

These tests focus on exercising real logic paths with lightweight fakes and
monkeypatching, without starting real Qt event loops or subprocesses.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

import src.runtime.common as runtime_common
import src.runtime.launcher_components as launcher_mod
import src.runtime.tray_components as tray_mod


# ---------------------------------------------------------------------------
# Tests for src.runtime.common
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests for src.runtime.launcher_components.Launcher
# ---------------------------------------------------------------------------


class DummyView(launcher_mod.LaunchView):
    """Simple in-memory LaunchView implementation for testing Launcher."""

    def __init__(self) -> None:
        self.status_updates: List[tuple[str, int]] = []
        self.errors: List[str] = []
        self.frontend_urls: List[str] = []
        self.process_events_calls = 0

    def set_status(self, message: str, progress: int) -> None:
        self.status_updates.append((message, progress))

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def allow_open_frontend(self, url: str) -> None:
        self.frontend_urls.append(url)

    def process_events(self) -> None:
        self.process_events_calls += 1


class DummyCompletedProcess:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout


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


def test_launcher_run_happy_path_uses_view_and_allows_open_frontend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Full Launcher.run happy path with heavy lifting methods stubbed out.
    """
    project_root = tmp_path
    view = DummyView()
    launcher = launcher_mod.Launcher(project_root, view)

    # Stub out the heavy operations; we just want to see that they are invoked
    # in order and that the final URL is exposed via the view.
    calls: List[str] = []

    def make_step(name: str):
        def _fn() -> None:
            calls.append(name)

        return _fn

    monkeypatch.setattr(launcher, "_check_python", make_step("check_python"))  # type: ignore[attr-defined]
    monkeypatch.setattr(launcher, "_ensure_venv", make_step("ensure_venv"))  # type: ignore[attr-defined]
    monkeypatch.setattr(
        launcher, "_install_backend_deps", make_step("install_deps")  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(launcher, "_start_services", make_step("start_services"))  # type: ignore[attr-defined]
    monkeypatch.setattr(
        launcher, "_wait_for_readiness", make_step("wait_for_readiness")  # type: ignore[attr-defined]
    )

    launcher.run()

    assert calls == [
        "check_python",
        "ensure_venv",
        "install_deps",
        "start_services",
        "wait_for_readiness",
    ]
    # The view should ultimately be told to allow opening the /app/ URL.
    assert view.frontend_urls == ["http://127.0.0.1:8000/app/"]


# ---------------------------------------------------------------------------
# Tests for src.runtime.tray_components
# ---------------------------------------------------------------------------


class DummyPopen:
    def __init__(self, exit_code: int = 0, fail_terminate: bool = False) -> None:
        self._exit_code = exit_code
        self._poll_result: Optional[int] = None
        self._wait_timeout: Optional[float] = None
        self._terminated = False
        self._killed = False
        self._fail_terminate = fail_terminate

    def poll(self) -> Optional[int]:
        return self._poll_result

    def terminate(self) -> None:
        if self._fail_terminate:
            raise RuntimeError("terminate not supported")
        self._terminated = True
        self._poll_result = self._exit_code

    def kill(self) -> None:
        self._killed = True
        self._poll_result = self._exit_code

    def wait(self, timeout: Optional[float] = None) -> int:
        self._wait_timeout = timeout
        if self._poll_result is None:
            # Simulate no exit yet.
            raise RuntimeError("still running")
        return self._exit_code


def test_process_group_terminate_variants() -> None:
    """
    ProcessGroup.terminate should handle normal terminate, terminate failure,
    and wait timeout by falling back to kill().
    """
    # Already-dead process: terminate is a no-op.
    pg_dead = tray_mod.ProcessGroup(DummyPopen())
    pg_dead._popen._poll_result = 0  # type: ignore[attr-defined]
    pg_dead.terminate()
    assert pg_dead._popen._killed is False  # type: ignore[attr-defined]

    # Normal terminate path: terminate(), then wait(), no kill().
    popen_ok = DummyPopen(exit_code=0)
    pg_ok = tray_mod.ProcessGroup(popen_ok)
    pg_ok.terminate()
    assert popen_ok._terminated is True

    # If wait raises, kill() should be attempted. We use a specialised dummy
    # that always raises from wait() to force the error-handling branch.
    class DummyPopenWaitFail(DummyPopen):
        def wait(self, timeout: Optional[float] = None) -> int:  # type: ignore[override]
            self._wait_timeout = timeout
            raise RuntimeError("still running")

    popen_wait_fail = DummyPopenWaitFail(exit_code=0)
    pg_wait_fail = tray_mod.ProcessGroup(popen_wait_fail)
    pg_wait_fail.terminate()
    assert popen_wait_fail._killed is True

    # terminate itself failing should fall back to kill().
    popen_term_fail = DummyPopen(exit_code=0, fail_terminate=True)
    pg_term_fail = tray_mod.ProcessGroup(popen_term_fail)
    pg_term_fail.terminate()
    assert popen_term_fail._killed is True


class DummySignal:
    def __init__(self) -> None:
        self._callbacks: List[Any] = []

    def connect(self, cb: Any) -> None:
        self._callbacks.append(cb)

    def emit(self) -> None:
        for cb in list(self._callbacks):
            cb()


class DummyAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.triggered = DummySignal()


class DummyMenu:
    def __init__(self) -> None:
        self.actions: List[DummyAction | str] = []
        self.submenus: List[tuple[str, "DummyMenu"]] = []

    def addAction(self, text: str) -> DummyAction:  # noqa: N802
        act = DummyAction(text)
        self.actions.append(act)
        return act

    def addSeparator(self) -> None:
        self.actions.append("---")

    def addMenu(self, title: str) -> "DummyMenu":  # noqa: N802
        submenu = DummyMenu()
        self.submenus.append((title, submenu))
        return submenu


class DummyTrayIcon:
    def __init__(self) -> None:
        self.icon = None
        self.tooltip: Optional[str] = None
        self.menu: Optional[DummyMenu] = None
        self.visible = False
        self._activated = DummySignal()

    def setIcon(self, icon: Any) -> None:
        self.icon = icon

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setContextMenu(self, menu: DummyMenu) -> None:
        self.menu = menu

    def setVisible(self, visible: bool) -> None:
        self.visible = visible

    def activated(self) -> DummySignal:  # pragma: no cover - not called directly
        return self._activated


class DummyApp:
    def __init__(self) -> None:
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


def test_tray_controller_configures_tray_and_start_services_stubbed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    TrayController.__init__ should configure the tray icon and start services.
    """
    # Use dummy Qt classes so we do not require a real Qt environment.
    monkeypatch.setattr(tray_mod, "QSystemTrayIcon", DummyTrayIcon)
    monkeypatch.setattr(tray_mod, "QMenu", DummyMenu)

    calls: Dict[str, bool] = {}

    def fake_start_services(self: Any) -> None:
        calls["start_services_called"] = True

    monkeypatch.setattr(tray_mod.TrayController, "_start_services", fake_start_services)

    app = DummyApp()
    controller = tray_mod.TrayController(app)

    assert isinstance(controller._tray, DummyTrayIcon)  # type: ignore[attr-defined]
    assert controller._tray.visible is True  # type: ignore[attr-defined]
    assert controller._tray.tooltip == tray_mod.APP_NAME  # type: ignore[attr-defined]
    assert calls["start_services_called"] is True

    # The context menu should carry a Help submenu with About and
    # Check for Updates entries ahead of the Exit action.
    menu = controller._tray.menu  # type: ignore[attr-defined]
    assert menu is not None
    submenu_titles = [title for title, _submenu in menu.submenus]
    assert submenu_titles == ["Help"]
    _title, help_submenu = menu.submenus[0]
    help_action_texts = [
        act.text for act in help_submenu.actions if isinstance(act, DummyAction)
    ]
    assert help_action_texts == ["About", "Check for Updates"]
    exit_texts = [act.text for act in menu.actions if isinstance(act, DummyAction)]
    assert "Exit" in exit_texts


def test_spawn_process_handles_failure_and_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    _spawn_process should log failures to start child processes and return None.
    """
    messages: List[str] = []

    def fake_log(msg: str) -> None:
        messages.append(msg)

    monkeypatch.setattr(tray_mod, "QSystemTrayIcon", DummyTrayIcon)
    monkeypatch.setattr(tray_mod, "QMenu", DummyMenu)

    app = DummyApp()
    controller = tray_mod.TrayController(app)

    monkeypatch.setattr(controller, "_log_message", fake_log, raising=True)  # type: ignore[attr-defined]

    def boom(*_args: Any, **_kwargs: Any):
        raise OSError("no binary")

    monkeypatch.setattr(tray_mod.subprocess, "Popen", boom)

    result = controller._spawn_process(["missing-binary"], cwd=Path("."), name="backend")  # type: ignore[attr-defined]

    assert result is None
    assert any("Failed to start backend process" in m for m in messages)


def test_on_exit_triggered_terminates_processes_and_quits_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    _on_exit_triggered should terminate backend and frontend processes, hide tray and quit the app.
    """
    monkeypatch.setattr(tray_mod, "QSystemTrayIcon", DummyTrayIcon)
    monkeypatch.setattr(tray_mod, "QMenu", DummyMenu)

    app = DummyApp()
    controller = tray_mod.TrayController(app)

    # Attach fake ProcessGroups that record terminate() calls.
    class PG:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    backend_pg = PG()
    frontend_pg = PG()
    controller._backend = backend_pg  # type: ignore[attr-defined]
    controller._frontend = frontend_pg  # type: ignore[attr-defined]

    controller._on_exit_triggered()  # type: ignore[attr-defined]

    assert frontend_pg.terminated is True
    assert backend_pg.terminated is True
    assert controller._tray.visible is False  # type: ignore[attr-defined]
    assert app.quit_called is True
