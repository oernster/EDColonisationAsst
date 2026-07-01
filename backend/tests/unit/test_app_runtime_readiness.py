from __future__ import annotations

"""Tests for the backend readiness probes in src.runtime.app_runtime.

Covers the non-blocking single probe used by the startup splash monitor and
the blocking wait_until_ready() wrapper that now delegates to it.
"""

import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List

import pytest

import src.runtime.app_runtime as app_runtime_mod
from src.runtime.common import RuntimeMode
from src.runtime.environment import RuntimeEnvironment


def make_controller(tmp_path: Path) -> app_runtime_mod.BackendServerController:
    env = RuntimeEnvironment(mode=RuntimeMode.DEV, project_root=tmp_path)
    return app_runtime_mod.BackendServerController(env)


class DummyResponse:
    """Minimal urlopen() context manager returning a fixed status code."""

    def __init__(self, code: int) -> None:
        self._code = code

    def getcode(self) -> int:
        return self._code

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def test_probe_ready_reports_both_down_when_connections_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_urlopen(*_args: Any, **_kwargs: Any):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)

    controller = make_controller(tmp_path)
    assert controller.probe_ready() == (False, False)


def test_probe_ready_reports_ready_when_endpoints_respond(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: List[str] = []

    def ok_urlopen(url: str, timeout: float = 0.0):
        requested.append(url)
        return DummyResponse(200)

    monkeypatch.setattr(urllib.request, "urlopen", ok_urlopen)

    controller = make_controller(tmp_path)
    assert controller.probe_ready() == (True, True)

    # Both the health endpoint and the web UI must be probed.
    assert any("/api/health" in url for url in requested)
    assert any("/app/" in url for url in requested)


def test_wait_until_ready_returns_true_when_probe_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = make_controller(tmp_path)
    monkeypatch.setattr(controller, "probe_ready", lambda: (True, True))

    assert controller.wait_until_ready(timeout=5.0) is True


def test_wait_until_ready_times_out_when_probe_never_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = make_controller(tmp_path)
    monkeypatch.setattr(controller, "probe_ready", lambda: (False, False))

    # Simulate time advancing past the deadline without real sleeping.
    start = 1000.0
    time_values = iter([start, start + 1.0, start + 61.0])

    def fake_time() -> float:
        try:
            return next(time_values)
        except StopIteration:
            return start + 61.0

    monkeypatch.setattr(app_runtime_mod.time, "time", fake_time)
    monkeypatch.setattr(app_runtime_mod.time, "sleep", lambda _secs: None)

    assert controller.wait_until_ready(timeout=60.0) is False
