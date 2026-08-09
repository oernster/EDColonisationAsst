"""Shared scaffolding for the test_runtime_components modules.

Split out of test_runtime_components.py when that file passed the module cap. Not named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
from typing import Any, List, Optional
import src.runtime.launcher_components as launcher_mod


"""
Additional tests for the runtime stack:

- src.runtime.common
- src.runtime.launcher_components
- src.runtime.tray_components

These tests focus on exercising real logic paths with lightweight fakes and
monkeypatching, without starting real Qt event loops or subprocesses.
"""


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
