"""Launcher run, process groups and the tray.

Split out of test_runtime_components.py; the scaffolding lives in _test_runtime_components_support.py.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
import src.runtime.launcher_components as launcher_mod
import src.runtime.tray_components as tray_mod
from src.constants import DEFAULT_BACKEND_PORT as BACKEND_PORT

from tests.unit._test_runtime_components_support import (
    DummyAction,
    DummyApp,
    DummyMenu,
    DummyPopen,
    DummyTrayIcon,
    DummyView,
)


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
    assert view.frontend_urls == [f"http://127.0.0.1:{BACKEND_PORT}/app/"]


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
