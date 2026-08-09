"""Status reporting, lifecycle and stop behaviour.

Split out of test_coverage_file_watcher.py; the scaffolding lives in
_test_coverage_file_watcher_support.py.
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
import src.services.file_watcher as fw_module
import src.services.file_watcher_polling as polling_module
from src.services.file_watcher import IFileWatcher

from tests.unit._test_coverage_file_watcher_support import (
    BASE_MTIME,
    _AliveProbeErrorObserver,
    _CancelledTask,
    _ExceptionProbeErrorTask,
    _FailedTask,
    _FailingStartObserver,
    _FlakyDoneTask,
    _HealthyObserver,
    _NotAliveObserver,
    _PendingTask,
    _broken_datetime_module,
    _make_watcher,
)


async def test_interface_abstract_methods_raise_not_implemented() -> None:
    """The ABC method bodies raise NotImplementedError when invoked directly."""
    watcher = _make_watcher()

    with pytest.raises(NotImplementedError):
        await IFileWatcher.start_watching(watcher, Path("."))

    with pytest.raises(NotImplementedError):
        await IFileWatcher.stop_watching(watcher)

    with pytest.raises(NotImplementedError):
        IFileWatcher.set_update_callback(watcher, lambda: None)


def test_is_running_variants() -> None:
    """is_running covers no observer, healthy observer and failing probe."""
    watcher = _make_watcher()
    assert watcher.is_running() is False

    watcher._observer = _HealthyObserver()  # type: ignore[assignment]
    assert watcher.is_running() is True

    watcher._observer = _AliveProbeErrorObserver()  # type: ignore[assignment]
    assert watcher.is_running() is True


def test_watchdog_status_variants() -> None:
    """watchdog_status reports configured/alive across observer states."""
    watcher = _make_watcher()

    status = watcher.watchdog_status()
    assert status["configured"] is False
    assert status["alive"] is False

    watcher._observer = _HealthyObserver()  # type: ignore[assignment]
    status = watcher.watchdog_status()
    assert status["configured"] is True
    assert status["alive"] is True

    watcher._observer = _AliveProbeErrorObserver()  # type: ignore[assignment]
    status = watcher.watchdog_status()
    assert status["configured"] is True
    assert status["alive"] is None


def test_poller_running_and_status_variants() -> None:
    """poller_running and poller_status cover every task-state branch."""
    watcher = _make_watcher()

    # No task at all.
    assert watcher.poller_running() is False
    status = watcher.poller_status()
    assert status["running"] is False
    assert status["task_done"] is None
    assert status["task_exception"] is None

    # Pending task: running, not done, no exception.
    watcher._poll_task = _PendingTask()  # type: ignore[assignment]
    assert watcher.poller_running() is True
    status = watcher.poller_status()
    assert status["running"] is True
    assert status["task_done"] is False
    assert status["task_exception"] is None

    # Cancelled task: done with no reportable exception.
    watcher._poll_task = _CancelledTask()  # type: ignore[assignment]
    status = watcher.poller_status()
    assert status["running"] is False
    assert status["task_done"] is True
    assert status["task_exception"] is None

    # Failed task: exception is formatted into the status payload.
    watcher._poll_task = _FailedTask()  # type: ignore[assignment]
    status = watcher.poller_status()
    assert status["task_done"] is True
    assert status["task_exception"] == "ValueError: poller exploded"

    # exception() probe itself failing is reported as the exception.
    watcher._poll_task = _ExceptionProbeErrorTask()  # type: ignore[assignment]
    status = watcher.poller_status()
    assert status["task_exception"] == "RuntimeError: cannot read exception"

    # done() probe failing inside the try leaves task_done as None.
    watcher._poll_task = _FlakyDoneTask()  # type: ignore[assignment]
    status = watcher.poller_status()
    assert status["task_done"] is None
    assert status["task_exception"] is None

    # Populate the last-seen fields so the truthy formatting branch runs.
    watcher._poll_last_path = Path("Journal.2026-01-01T000000.01.log")
    watcher._poll_task = None
    status = watcher.poller_status()
    assert status["last_seen_file"] == str(Path("Journal.2026-01-01T000000.01.log"))


def test_watched_directory_and_set_update_callback() -> None:
    """watched_directory reflects state; callbacks propagate to the handler."""
    watcher = _make_watcher()
    assert watcher.watched_directory() is None

    watcher._directory = Path("somewhere")
    assert watcher.watched_directory() == Path("somewhere")

    async def _callback(system_name: str) -> None:
        return None

    # Without a handler only the stored callback changes.
    watcher.set_update_callback(_callback)
    assert watcher._update_callback is _callback

    # With a handler present the callback is forwarded onto it.
    handler = SimpleNamespace(update_callback=None)
    watcher._handler = handler  # type: ignore[assignment]
    watcher.set_update_callback(_callback)
    assert handler.update_callback is _callback


async def test_start_watching_returns_when_observer_alive(tmp_path: Path) -> None:
    """A second start with a live observer is a no-op warning."""
    watcher = _make_watcher()
    existing = _HealthyObserver()
    watcher._observer = existing  # type: ignore[assignment]

    await watcher.start_watching(tmp_path)

    assert watcher._observer is existing
    assert watcher._directory is None


async def test_start_watching_treats_alive_probe_error_as_alive(
    tmp_path: Path,
) -> None:
    """If the liveness probe raises the observer is assumed alive."""
    watcher = _make_watcher()
    existing = _AliveProbeErrorObserver()
    watcher._observer = existing  # type: ignore[assignment]

    await watcher.start_watching(tmp_path)

    assert watcher._observer is existing


async def test_start_watching_restarts_dead_observer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead observer triggers stop_watching then a fresh start."""
    monkeypatch.setattr(fw_module, "Observer", _HealthyObserver)
    monkeypatch.setattr(polling_module, "is_frozen", lambda: False)

    watcher = _make_watcher()
    dead = _NotAliveObserver()
    watcher._observer = dead  # type: ignore[assignment]

    await watcher.start_watching(tmp_path)

    assert dead.stopped is True
    assert dead.joined is True
    new_observer = watcher._observer
    assert isinstance(new_observer, _HealthyObserver)
    assert new_observer.started is True
    assert watcher._directory == tmp_path


async def test_start_watching_survives_clock_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing datetime.now leaves started_at as None without raising."""
    with monkeypatch.context() as mp:
        mp.setattr(fw_module, "Observer", _HealthyObserver)
        mp.setattr(polling_module, "is_frozen", lambda: False)
        mp.setitem(sys.modules, "datetime", _broken_datetime_module())

        watcher = _make_watcher()
        await watcher.start_watching(tmp_path)

    assert watcher._watchdog_started_at is None
    assert isinstance(watcher._observer, _HealthyObserver)


async def test_start_watching_records_error_when_observer_not_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An observer that never comes alive is recorded as a watchdog error."""
    monkeypatch.setattr(fw_module, "Observer", _NotAliveObserver)
    monkeypatch.setattr(polling_module, "is_frozen", lambda: False)

    watcher = _make_watcher()
    await watcher.start_watching(tmp_path)

    assert watcher._watchdog_last_error is not None
    assert "not alive" in watcher._watchdog_last_error


async def test_start_watching_records_error_when_observer_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception from Observer.start is captured and the observer cleared."""
    monkeypatch.setattr(fw_module, "Observer", _FailingStartObserver)
    monkeypatch.setattr(polling_module, "is_frozen", lambda: False)

    watcher = _make_watcher()
    await watcher.start_watching(tmp_path)

    assert watcher._observer is None
    assert watcher._watchdog_last_error is not None
    assert "RuntimeError" in watcher._watchdog_last_error


async def test_start_watching_logs_existing_file_processing_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failures while processing existing journals must not abort startup."""
    monkeypatch.setattr(fw_module, "Observer", _HealthyObserver)
    monkeypatch.setattr(polling_module, "is_frozen", lambda: False)

    watcher = _make_watcher()

    async def failing_process(directory: Path) -> None:
        raise RuntimeError("cannot enumerate journals")

    monkeypatch.setattr(watcher, "_process_existing_files", failing_process)

    await watcher.start_watching(tmp_path)

    assert isinstance(watcher._observer, _HealthyObserver)
    assert watcher._observer.started is True


async def test_stop_watching_cancels_active_poll_task() -> None:
    """An active poller task is cancelled and the state fields reset."""
    watcher = _make_watcher()
    watcher._poll_task = asyncio.create_task(asyncio.sleep(60))
    watcher._poll_last_path = Path("Journal.old.log")
    watcher._poll_last_mtime = BASE_MTIME

    await watcher.stop_watching()

    assert watcher._poll_task is None
    assert watcher._poll_last_path is None
    assert watcher._poll_last_mtime is None
    # No observer was configured so stop_watching returns early afterwards.
    assert watcher._observer is None


async def test_stop_watching_logs_failed_poll_task() -> None:
    """A poller task that already failed is awaited and its error swallowed."""
    watcher = _make_watcher()

    async def boom() -> None:
        raise RuntimeError("poller crashed")

    task = asyncio.create_task(boom())
    await asyncio.wait({task})
    watcher._poll_task = task

    await watcher.stop_watching()

    assert watcher._poll_task is None
