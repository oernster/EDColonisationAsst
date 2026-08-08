from __future__ import annotations

"""Tests for the packaged runtime entrypoint.

These tests focus on the top-level `main()` function in
[`runtime_entry`](backend/src/runtime_entry.py:580), specifically its
single-instance locking behaviour. They avoid starting any real Qt event
loop or uvicorn server by substituting lightweight fakes.
"""

from typing import Dict

import pytest

import src.runtime_entry as runtime_entry


def test_main_exits_early_when_lock_already_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the application lock is already held, main() should exit early.

    In this case we expect:

    - No RuntimeApplication to be constructed.
    - The function to attempt to open the existing web UI in the browser, at
      the address the detected environment reports rather than a hardcoded
      port that a configured one would silently invalidate.
    - main() to return 0.
    """

    opened: Dict[str, str] = {}

    class DummyLock:
        def __init__(self) -> None:  # pragma: no cover - trivial
            pass

        def acquire(self) -> bool:
            # Simulate another instance already holding the lock.
            return False

    def fake_open(url: str) -> bool:
        opened["url"] = url
        return True

    class DummyEnvironment:
        """Stands in for the detected environment with a known address.

        Pinned rather than compared against a second detect() call: the port is
        resolved against the machine now, so two calls can legitimately answer
        differently and the test would be asserting nothing.
        """

        frontend_url = "http://127.0.0.1:9057/app/"

        @classmethod
        def detect(cls) -> "DummyEnvironment":
            return cls()

    # Ensure our dummy lock, environment and browser are used.
    monkeypatch.setattr(runtime_entry, "ApplicationInstanceLock", DummyLock)
    monkeypatch.setattr(runtime_entry, "RuntimeEnvironment", DummyEnvironment)
    monkeypatch.setattr(runtime_entry.webbrowser, "open", fake_open)

    # Also silence any debug logging to avoid filesystem writes during tests.
    monkeypatch.setattr(runtime_entry, "_debug_log", lambda msg: None)

    code = runtime_entry.main()

    assert code == 0
    assert opened["url"] == DummyEnvironment.frontend_url


def test_main_continues_when_lock_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If acquiring the application lock raises, main() should continue.

    When `ApplicationInstanceLock.acquire()` raises
    [`ApplicationInstanceLockError`](backend/src/runtime/app_singleton.py:1),
    `main()` should:

    - Log the error (silenced here for tests).
    - Proceed to create a [`RuntimeApplication`](backend/src/runtime_entry.py:479).
    - Return whatever exit code `RuntimeApplication.run()` yields.
    """

    calls: Dict[str, bool] = {}

    class DummyLock:
        def __init__(self) -> None:  # pragma: no cover - trivial
            pass

        def acquire(self) -> bool:
            # Simulate an underlying OS or filesystem error in the lock layer.
            raise runtime_entry.ApplicationInstanceLockError("boom")

    class DummyRuntimeApplication:
        def __init__(self) -> None:
            calls["created"] = True
            # Provide the minimal `_env` attribute expected by runtime_entry.main()
            self._env = type("Env", (), {"mode": "DEV"})()

        def run(self) -> int:
            calls["ran"] = True
            return 42

    monkeypatch.setattr(runtime_entry, "ApplicationInstanceLock", DummyLock)
    monkeypatch.setattr(runtime_entry, "RuntimeApplication", DummyRuntimeApplication)
    monkeypatch.setattr(runtime_entry, "_debug_log", lambda msg: None)

    code = runtime_entry.main()

    assert code == 42
    assert calls == {"created": True, "ran": True}
