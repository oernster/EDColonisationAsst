from __future__ import annotations

"""Tests for the GUI launcher entrypoint.

These tests exercise the top-level [`main()`](backend/src/launcher.py:441)
function in a controlled way, focusing on:

- Single-instance behaviour using [`ApplicationInstanceLock`](backend/src/runtime/app_singleton.py:1).
- Ensuring that a lock acquisition error does not prevent the launcher from starting.
"""

from pathlib import Path
from typing import Dict

import pytest

import src.launcher as launcher
from src.constants import DEFAULT_BACKEND_PORT as BACKEND_PORT


def test_main_exits_early_when_lock_already_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the launcher lock is already held, main() should exit early.

    Expected behaviour:

    - [`ApplicationInstanceLock.acquire()`](backend/src/runtime/app_singleton.py:1)
      returns False.
    - `launcher.main()` opens the existing web UI in a browser.
    - No `QApplication` instance is ever created.
    - The function returns 0.
    """

    opened: Dict[str, str] = {}

    class DummyLock:
        def __init__(self) -> None:  # pragma: no cover - trivial
            pass

        def acquire(self) -> bool:
            # Simulate another launcher instance already holding the lock.
            return False

    def fake_open(url: str) -> bool:
        opened["url"] = url
        return True

    # Use a stable, temporary project root so _detect_project_root() does not
    # depend on the actual filesystem layout.
    monkeypatch.setattr(
        launcher, "_detect_project_root", lambda: Path.cwd(), raising=False
    )

    # Ensure our dummy lock and browser are used.
    monkeypatch.setattr(launcher, "ApplicationInstanceLock", DummyLock)
    monkeypatch.setattr(launcher.webbrowser, "open", fake_open)

    # Guard against accidental QApplication construction: if main() tried to
    # create an app in this scenario, this dummy would be instantiated.
    class SentinelApp:
        def __init__(self, *args, **kwargs) -> None:  # pragma: no cover - defensive
            raise AssertionError(
                "QApplication should not be constructed when lock is held"
            )

    monkeypatch.setattr(launcher, "QApplication", SentinelApp)

    code = launcher.main()

    assert code == 0
    assert opened["url"] == f"http://127.0.0.1:{BACKEND_PORT}/app/"


def test_main_continues_when_lock_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the application lock cannot be created, main() should still start the GUI.

    Scenario:

    - [`ApplicationInstanceLock.acquire()`](backend/src/runtime/app_singleton.py:1)
      raises `ApplicationInstanceLockError`.
    - The exception is caught inside [`launcher.main()`](backend/src/launcher.py:441).
    - A `QApplication` is created and its `exec()` method is invoked.
    - The return code from `exec()` is used as the process exit code.
    """

    class DummyLock:
        def __init__(self) -> None:  # pragma: no cover - trivial
            pass

        def acquire(self) -> bool:
            raise launcher.ApplicationInstanceLockError("simulated failure")

    # Record that the Qt application and window were created, and control exec().
    calls: Dict[str, bool | int] = {}

    class DummyApp:
        def __init__(self, *args, **kwargs) -> None:
            calls["app_created"] = True

        def setWindowIcon(self, *_args, **_kwargs) -> None:  # noqa: N802
            # No-op in tests.
            calls["icon_set"] = True

        def exec(self) -> int:
            calls["exec_called"] = True
            return 17

    class DummyWindow:
        def __init__(self, project_root: Path, parent=None) -> None:
            calls["window_created"] = True
            calls["project_root"] = project_root

        def show(self) -> None:
            calls["window_shown"] = True

        def set_status(self, *_args, **_kwargs) -> None:
            # Part of the LaunchView interface; unused in this test.
            pass

        def show_error(self, *_args, **_kwargs) -> None:
            # Called when Launcher.run() catches an exception during steps.
            calls["show_error_called"] = True

    def fake_single_shot(_delay: int, callback) -> None:
        # Immediately invoke the callback instead of scheduling with the real event loop.
        calls["single_shot_called"] = True
        callback()

    # Use a temporary directory as a fake project root so that icon resolution
    # and log file paths remain inside the test sandbox.
    monkeypatch.setattr(
        launcher, "_detect_project_root", lambda: tmp_path, raising=False
    )

    # Avoid long real-world waits inside Launcher._wait_for_readiness during tests.
    # The readiness logic is exercised separately in test_runtime_components, so
    # here we stub it out to keep the entrypoint test fast and deterministic.
    monkeypatch.setattr(
        launcher.Launcher,
        "_wait_for_readiness",
        lambda self: None,
        raising=False,
    )

    monkeypatch.setattr(launcher, "ApplicationInstanceLock", DummyLock)
    monkeypatch.setattr(launcher, "QApplication", DummyApp)
    monkeypatch.setattr(launcher, "QtLaunchWindow", DummyWindow)
    monkeypatch.setattr(launcher.QTimer, "singleShot", fake_single_shot)

    code = launcher.main()

    assert code == 17
    assert calls["app_created"] is True
    assert calls["window_created"] is True
    assert calls["window_shown"] is True
    assert calls["single_shot_called"] is True
    # Ensure the project root used by the launcher is our temporary directory.
    assert calls["project_root"] == tmp_path
