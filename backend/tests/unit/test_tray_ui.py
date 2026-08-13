from __future__ import annotations

"""Tests for the frozen runtime's choice of visible surface.

A packaged install has no window of its own, so the tray icon is the whole of
it: how the user reaches the interface and how they quit. On a desktop with no
tray that arrangement leaves the application running with nothing on screen and
no way out. These tests cover the decision that prevents it.

No Qt widgets are constructed. The suite has no event loop and no offscreen
platform, so the module's Qt names are substituted with fakes, which is the
same approach test_help_menu.py takes. The one Qt-derived method that matters,
the window's closeEvent, is driven as an unbound function over a stub.
"""

from pathlib import Path
from typing import Any, List

import src.runtime.tray_fallback as tray_fallback_mod
import src.runtime.tray_ui as tray_ui_mod
from src.runtime.environment import RuntimeEnvironment
from src.utils.runtime import RuntimeMode


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class DummySignal:
    def __init__(self) -> None:
        self._callbacks: List[Any] = []

    def connect(self, cb: Any) -> None:
        self._callbacks.append(cb)


class FakeTray:
    """Stands in for QSystemTrayIcon; availability is set per test."""

    available = True
    instances: List["FakeTray"] = []

    class ActivationReason:
        Trigger = "trigger"
        DoubleClick = "double-click"

    def __init__(self) -> None:
        self.activated = DummySignal()
        self.visible: bool | None = None
        self.shown = False
        self.tooltip: str | None = None
        self.context_menu: Any = None
        FakeTray.instances.append(self)

    @staticmethod
    def isSystemTrayAvailable() -> bool:
        return FakeTray.available

    def setIcon(self, icon: Any) -> None:
        self.icon = icon

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setVisible(self, visible: bool) -> None:
        self.visible = visible

    def setContextMenu(self, menu: Any) -> None:
        self.context_menu = menu

    def show(self) -> None:
        self.shown = True


class FakeWindow:
    """Stands in for TrayFallbackWindow, recording how it was wired."""

    instances: List["FakeWindow"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.shown = False
        FakeWindow.instances.append(self)

    def show(self) -> None:
        self.shown = True


class FakeApp:
    def __init__(self) -> None:
        self.quit_calls = 0

    def quit(self) -> None:
        self.quit_calls += 1


class FakeBackend:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class FakeUpdates:
    def check_manually(self) -> None:
        """The Help menu's manual check; never run in these tests."""


class FakeMenu:
    def __init__(self) -> None:
        self.actions: List[Any] = []

    def addAction(self, text: str) -> Any:
        action = type("A", (), {"triggered": DummySignal()})()
        self.actions.append(text)
        return action

    def addSeparator(self) -> None:
        self.actions.append("---")

    def addMenu(self, title: str) -> "FakeMenu":
        return FakeMenu()


def _install_fakes(monkeypatch, available: bool) -> None:
    FakeTray.available = available
    FakeTray.instances = []
    FakeWindow.instances = []
    monkeypatch.setattr(tray_ui_mod, "QSystemTrayIcon", FakeTray)
    monkeypatch.setattr(tray_ui_mod, "TrayFallbackWindow", FakeWindow)
    monkeypatch.setattr(tray_ui_mod, "QMenu", FakeMenu)
    monkeypatch.setattr(tray_ui_mod, "QIcon", lambda *a, **k: object())
    monkeypatch.setattr(
        tray_ui_mod, "default_update_check", lambda **kwargs: FakeUpdates()
    )
    monkeypatch.setattr(tray_ui_mod, "add_help_menu", lambda *a, **k: FakeMenu())
    monkeypatch.setattr(tray_ui_mod, "resolve_about_icon", lambda root: None)


def _build(monkeypatch, tmp_path: Path, available: bool):
    _install_fakes(monkeypatch, available)
    env = RuntimeEnvironment(
        mode=RuntimeMode.FROZEN, project_root=tmp_path, backend_port=47021
    )
    app = FakeApp()
    backend = FakeBackend()
    controller = tray_ui_mod.TrayUIController(app, env, backend)
    return controller, app, backend


# ---------------------------------------------------------------------------
# Which surface gets built
# ---------------------------------------------------------------------------


def test_a_desktop_with_a_tray_gets_the_tray(monkeypatch, tmp_path: Path) -> None:
    controller, _app, _backend = _build(monkeypatch, tmp_path, available=True)

    assert len(FakeTray.instances) == 1
    assert FakeWindow.instances == []
    assert FakeTray.instances[0].tooltip == tray_ui_mod._TRAY_TOOLTIP


def test_a_desktop_without_a_tray_gets_the_window(monkeypatch, tmp_path: Path) -> None:
    """The case the feature exists for.

    Without this the application starts, serves the interface and shows
    nothing at all and cannot be quit except by killing the process.
    """
    controller, _app, _backend = _build(monkeypatch, tmp_path, available=False)

    assert FakeTray.instances == []
    assert len(FakeWindow.instances) == 1


def test_the_window_is_wired_to_the_same_actions_as_the_tray(
    monkeypatch, tmp_path: Path
) -> None:
    """Losing the tray must not quietly lose what its menu offered."""
    controller, _app, _backend = _build(monkeypatch, tmp_path, available=False)

    wiring = FakeWindow.instances[0].kwargs
    assert wiring["on_open_web_ui"] == controller._on_open_web_ui
    assert wiring["on_exit"] == controller._on_exit
    assert wiring["on_check_updates"] is not None


def test_show_shows_the_tray_when_there_is_one(monkeypatch, tmp_path: Path) -> None:
    controller, _app, _backend = _build(monkeypatch, tmp_path, available=True)

    controller.show()

    assert FakeTray.instances[0].shown is True


def test_show_shows_the_window_when_there_is_no_tray(
    monkeypatch, tmp_path: Path
) -> None:
    controller, _app, _backend = _build(monkeypatch, tmp_path, available=False)

    controller.show()

    assert FakeWindow.instances[0].shown is True


# ---------------------------------------------------------------------------
# Exit
# ---------------------------------------------------------------------------


def test_a_confirmed_exit_stops_the_backend_and_quits(
    monkeypatch, tmp_path: Path
) -> None:
    controller, app, backend = _build(monkeypatch, tmp_path, available=True)
    monkeypatch.setattr(tray_ui_mod, "ask_yes_no", lambda *a, **k: True)

    assert controller._on_exit() is True
    assert backend.stop_calls == 1
    assert app.quit_calls == 1
    assert FakeTray.instances[0].visible is False


def test_a_cancelled_exit_changes_nothing(monkeypatch, tmp_path: Path) -> None:
    controller, app, backend = _build(monkeypatch, tmp_path, available=True)
    monkeypatch.setattr(tray_ui_mod, "ask_yes_no", lambda *a, **k: False)

    assert controller._on_exit() is False
    assert backend.stop_calls == 0
    assert app.quit_calls == 0


def test_exit_without_a_tray_does_not_reach_for_one(
    monkeypatch, tmp_path: Path
) -> None:
    """The tray is None on a desktop that had none; exiting must not assume it."""
    controller, app, backend = _build(monkeypatch, tmp_path, available=False)
    monkeypatch.setattr(tray_ui_mod, "ask_yes_no", lambda *a, **k: True)

    assert controller._on_exit() is True
    assert backend.stop_calls == 1
    assert app.quit_calls == 1


# ---------------------------------------------------------------------------
# The window's close button is the same request as Exit
# ---------------------------------------------------------------------------


class FakeCloseEvent:
    def __init__(self) -> None:
        self.accepted = False
        self.ignored = False

    def accept(self) -> None:
        self.accepted = True

    def ignore(self) -> None:
        self.ignored = True


class StubWindow:
    """Just enough of the window for closeEvent, which touches only this."""

    def __init__(self, exiting: bool) -> None:
        self._on_exit = lambda: exiting


def test_closing_the_window_when_the_exit_is_confirmed_closes_it() -> None:
    event = FakeCloseEvent()

    tray_fallback_mod.TrayFallbackWindow.closeEvent(StubWindow(True), event)

    assert event.accepted is True
    assert event.ignored is False


def test_closing_the_window_when_the_exit_is_cancelled_keeps_it() -> None:
    """A cancelled confirmation must not hide the only surface there is.

    The application sets quitOnLastWindowClosed to False, so a window that
    closed itself here would leave the process running with nothing on screen
    to reach it by, which is the state this whole module exists to prevent.
    """
    event = FakeCloseEvent()

    tray_fallback_mod.TrayFallbackWindow.closeEvent(StubWindow(False), event)

    assert event.accepted is False
    assert event.ignored is True
