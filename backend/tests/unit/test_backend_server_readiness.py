"""Tests for the backend readiness probes in src.runtime.backend_server.

Covers the non-blocking single probe used by the startup splash monitor, the
blocking wait_until_ready() wrapper that now delegates to it and the named
startup failures that let the splash say why a backend will never answer
instead of waiting out its readiness budget and calling it slow.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List

import pytest

import src.runtime.backend_server as backend_server_mod
from src.runtime.common import RuntimeMode
from src.runtime.environment import RuntimeEnvironment


def make_controller(tmp_path: Path) -> backend_server_mod.BackendServerController:
    env = RuntimeEnvironment(mode=RuntimeMode.DEV, project_root=tmp_path)
    return backend_server_mod.BackendServerController(env)


class StubServer:
    """A uvicorn.Server stand-in whose run() fails the way the real one does."""

    def __init__(self, error: BaseException) -> None:
        self._error = error

    def run(self) -> None:
        raise self._error


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

    monkeypatch.setattr(backend_server_mod.time, "time", fake_time)
    monkeypatch.setattr(backend_server_mod.time, "sleep", lambda _secs: None)

    assert controller.wait_until_ready(timeout=60.0) is False


# ---------------------------------------------------------------------------
# Named startup failures
# ---------------------------------------------------------------------------


def test_startup_failure_is_none_until_something_fails(tmp_path: Path) -> None:
    assert make_controller(tmp_path).startup_failure() is None


def test_start_reports_port_in_use_and_starts_no_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A taken port is named at once; no uvicorn thread is started.

    This is the second-instance case from the field: the runtime came up, could
    not bind and gave the user three minutes of "Starting the local backend..."
    with no way to tell what was wrong.
    """
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupier:
        occupier.bind((host, 0))
        port = occupier.getsockname()[1]

        env = RuntimeEnvironment(
            mode=RuntimeMode.FROZEN,
            project_root=tmp_path,
            backend_port=port,
        )
        controller = backend_server_mod.BackendServerController(env)
        monkeypatch.setattr(controller, "_resolve_host", lambda: host)

        controller.start()

    reason = controller.startup_failure()
    assert reason is not None
    assert str(port) in reason
    # Nothing was started, so there is nothing to stop or wait on.
    assert controller._server is None
    assert controller._thread is None


def test_start_records_the_port_it_bound_for_the_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A port that worked is written down, so the next run reuses it.

    The port is no longer fixed, so the address has to be recorded somewhere a
    second instance and the next start can both find it.
    """
    host = "127.0.0.1"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        free_port = probe.getsockname()[1]

    env = RuntimeEnvironment(
        mode=RuntimeMode.FROZEN,
        project_root=tmp_path,
        backend_port=free_port,
    )
    controller = backend_server_mod.BackendServerController(env)
    monkeypatch.setattr(controller, "_resolve_host", lambda: host)
    # Stop short of actually serving: the recording happens before the thread.
    monkeypatch.setattr(controller, "_make_runner", lambda server, host: lambda: None)

    controller.start()

    assert env.recorded_port_file.read_text(encoding="utf-8") == str(free_port)
    assert controller.startup_failure() is None


def test_runner_records_a_systemexit_as_a_named_failure(tmp_path: Path) -> None:
    """uvicorn calls sys.exit(1) when it cannot bind.

    SystemExit is a BaseException, so `except Exception` never saw it and
    Python discards it silently on a thread: the server thread vanished with no
    log line at all. It must now leave a named cause behind.
    """
    controller = make_controller(tmp_path)
    runner = controller._make_runner(StubServer(SystemExit(1)), "127.0.0.1")

    runner()

    reason = controller.startup_failure()
    assert reason is not None
    assert backend_server_mod._FAILURE_EXITED in reason
    assert "SystemExit(1)" in reason


def test_runner_records_a_crash_as_a_named_failure(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    runner = controller._make_runner(StubServer(RuntimeError("boom")), "127.0.0.1")

    runner()

    reason = controller.startup_failure()
    assert reason is not None
    assert backend_server_mod._FAILURE_CRASHED in reason
    assert "boom" in reason
