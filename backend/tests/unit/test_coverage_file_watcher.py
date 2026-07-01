"""Coverage tests for src.services.file_watcher.

These tests target the FileWatcher lifecycle, diagnostics and the polling
fallback without any mocking libraries. All collaborators are hand-written
fakes; watchdog observers are replaced with in-memory stand-ins so no real
observer threads are started; asyncio.sleep is replaced with a scripted
coroutine so the polling loop runs deterministically and fast.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

import pytest

import src.services.file_watcher as fw_module
from src.services.file_watcher import FileWatcher, IFileWatcher

# Fixed epoch base and step used only to give journal files deterministic,
# clearly ordered modification times in tests.
BASE_MTIME = 1_700_000_000.0
MTIME_STEP = 100.0


# ---------------------------------------------------------------------------
# Hand-written fakes
# ---------------------------------------------------------------------------


class _StubParser:
    """Parser stand-in; FileWatcher only stores it in these tests."""

    def parse_file(self, file_path: Path) -> list:
        return []

    def parse_line(self, line: str) -> None:
        return None


class _StubTracker:
    """System tracker stand-in; never consulted by these tests."""


class _StubRepo:
    """Repository stand-in; never consulted by these tests."""


class _DummyLoop:
    """Truthy loop placeholder; FileWatcher only stores and forwards it."""


class _RecordingHandler:
    """Handler fake that records which files the poller asked it to process."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    async def _process_file(self, file_path: Path) -> None:
        self.paths.append(file_path)


class _HealthyObserver:
    """Fake watchdog Observer that starts cleanly and reports alive."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[Any, str, bool]] = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, handler: Any, path: str, recursive: bool) -> None:
        self.scheduled.append((handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return True

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True


class _NotAliveObserver(_HealthyObserver):
    """Observer fake whose thread never comes alive after start()."""

    def is_alive(self) -> bool:
        return False


class _FailingStartObserver(_HealthyObserver):
    """Observer fake whose start() raises."""

    def start(self) -> None:
        raise RuntimeError("cannot start observer thread")


class _AliveProbeErrorObserver(_HealthyObserver):
    """Observer fake whose is_alive() probe raises."""

    def is_alive(self) -> bool:
        raise RuntimeError("probe failed")


class _PendingTask:
    """Task fake representing a still-running poller task."""

    def done(self) -> bool:
        return False


class _CancelledTask:
    """Task fake representing a cancelled poller task."""

    def done(self) -> bool:
        return True

    def exception(self) -> None:
        raise asyncio.CancelledError()


class _FailedTask:
    """Task fake whose exception() reports a stored failure."""

    def done(self) -> bool:
        return True

    def exception(self) -> Exception:
        return ValueError("poller exploded")


class _ExceptionProbeErrorTask:
    """Task fake whose exception() itself raises a non-cancel error."""

    def done(self) -> bool:
        return True

    def exception(self) -> None:
        raise RuntimeError("cannot read exception")


class _FlakyDoneTask:
    """Task fake whose done() raises on the first call then reports done."""

    def __init__(self) -> None:
        self._calls = 0

    def done(self) -> bool:
        self._calls += 1
        if self._calls == 1:
            raise RuntimeError("done probe failed")
        return True

    def exception(self) -> None:
        return None


def _make_watcher(loop: Any = None) -> FileWatcher:
    """Build a FileWatcher wired to inert stub collaborators."""
    return FileWatcher(
        parser=_StubParser(),  # type: ignore[arg-type]
        system_tracker=_StubTracker(),  # type: ignore[arg-type]
        repository=_StubRepo(),  # type: ignore[arg-type]
        loop=loop if loop is not None else _DummyLoop(),  # type: ignore[arg-type]
    )


def _broken_datetime_module() -> SimpleNamespace:
    """Fake datetime module whose datetime.now raises.

    Installing this in sys.modules makes the in-function
    `from datetime import datetime, timezone` succeed while the subsequent
    now() call fails, driving the defensive except branches.
    """

    class _BrokenDateTime:
        @staticmethod
        def now(tz: Any) -> Any:
            raise RuntimeError("clock unavailable")

    return SimpleNamespace(datetime=_BrokenDateTime, timezone=timezone)


def _write_journal(directory: Path, name: str, mtime: float) -> Path:
    """Create a journal file with a deterministic modification time."""
    path = directory / name
    path.write_text("{}", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# IFileWatcher abstract interface
# ---------------------------------------------------------------------------


async def test_interface_abstract_methods_raise_not_implemented() -> None:
    """The ABC method bodies raise NotImplementedError when invoked directly."""
    watcher = _make_watcher()

    with pytest.raises(NotImplementedError):
        await IFileWatcher.start_watching(watcher, Path("."))

    with pytest.raises(NotImplementedError):
        await IFileWatcher.stop_watching(watcher)

    with pytest.raises(NotImplementedError):
        IFileWatcher.set_update_callback(watcher, lambda: None)


# ---------------------------------------------------------------------------
# Diagnostics: is_running, watchdog_status, poller_running, poller_status
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# start_watching lifecycle branches
# ---------------------------------------------------------------------------


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
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

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
        mp.setattr(fw_module, "is_frozen", lambda: False)
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
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

    watcher = _make_watcher()
    await watcher.start_watching(tmp_path)

    assert watcher._watchdog_last_error is not None
    assert "not alive" in watcher._watchdog_last_error


async def test_start_watching_records_error_when_observer_start_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception from Observer.start is captured and the observer cleared."""
    monkeypatch.setattr(fw_module, "Observer", _FailingStartObserver)
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

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
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

    watcher = _make_watcher()

    async def failing_process(directory: Path) -> None:
        raise RuntimeError("cannot enumerate journals")

    monkeypatch.setattr(watcher, "_process_existing_files", failing_process)

    await watcher.start_watching(tmp_path)

    assert isinstance(watcher._observer, _HealthyObserver)
    assert watcher._observer.started is True


# ---------------------------------------------------------------------------
# stop_watching branches
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Polling fallback: _start_polling_if_enabled
# ---------------------------------------------------------------------------


def test_start_polling_disabled_outside_frozen_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polling is a packaged-runtime feature only."""
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)
    watcher = _make_watcher()

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is None


def test_start_polling_skips_when_task_already_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live poller task is never replaced."""
    monkeypatch.setattr(fw_module, "is_frozen", lambda: True)
    watcher = _make_watcher()
    pending = _PendingTask()
    watcher._poll_task = pending  # type: ignore[assignment]

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is pending


async def test_start_polling_creates_task_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In frozen mode a real poller task is created."""
    monkeypatch.setattr(fw_module, "is_frozen", lambda: True)
    watcher = _make_watcher()

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher.poller_running() is True
    task = watcher._poll_task
    assert task is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_start_polling_handles_create_task_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create_task failure is logged and leaves no poller task behind."""
    monkeypatch.setattr(fw_module, "is_frozen", lambda: True)
    watcher = _make_watcher()

    def not_a_coroutine(directory: Path) -> object:
        # Returning a plain object makes asyncio.create_task raise TypeError
        # without leaving an unawaited coroutine behind.
        return object()

    monkeypatch.setattr(watcher, "_poll_for_latest_changes", not_a_coroutine)

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is None


# ---------------------------------------------------------------------------
# Polling fallback: _poll_for_latest_changes
# ---------------------------------------------------------------------------


def _scripted_sleep(script: list[Callable[[], None]]) -> Callable[..., Any]:
    """Build an asyncio.sleep replacement that runs one script step per call.

    Each call executes the next scripted action (mutating the filesystem or
    the watcher between loop iterations). Once the script is exhausted the
    fake raises CancelledError to end the otherwise infinite polling loop.
    """
    state = {"index": 0}

    async def fake_sleep(_delay: float) -> None:
        index = state["index"]
        state["index"] += 1
        if index >= len(script):
            raise asyncio.CancelledError()
        script[index]()

    return fake_sleep


async def test_poll_loop_processes_changes_across_iterations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poll loop detects new files, mtime bumps and unchanged states.

    Iteration plan (one scripted action runs between iterations):
      1. empty directory, nothing to do
      2. J1 appears, processed because no file was seen before
      3. J1 mtime bumped, processed again
      4. last seen mtime cleared, processed again via the None-mtime branch
      5. nothing changed, skipped
      6. newer J2 appears but the handler is gone, change detected yet skipped
    """
    watch_dir = tmp_path / "journals"
    watch_dir.mkdir()

    watcher = _make_watcher()
    handler = _RecordingHandler()
    watcher._handler = handler  # type: ignore[assignment]

    j1 = watch_dir / "Journal.2026-01-01T000000.01.log"
    j2 = watch_dir / "Journal.2026-01-02T000000.01.log"

    def create_j1() -> None:
        _write_journal(watch_dir, j1.name, BASE_MTIME)

    def bump_j1_mtime() -> None:
        os.utime(j1, (BASE_MTIME + MTIME_STEP, BASE_MTIME + MTIME_STEP))

    def clear_last_mtime() -> None:
        watcher._poll_last_mtime = None

    def no_change() -> None:
        return None

    def new_file_and_drop_handler() -> None:
        _write_journal(watch_dir, j2.name, BASE_MTIME + 2 * MTIME_STEP)
        watcher._handler = None

    script = [
        create_j1,
        bump_j1_mtime,
        clear_last_mtime,
        no_change,
        new_file_and_drop_handler,
    ]

    with monkeypatch.context() as mp:
        mp.setattr(asyncio, "sleep", _scripted_sleep(script))
        with pytest.raises(asyncio.CancelledError):
            await watcher._poll_for_latest_changes(watch_dir)

    # Iterations 2, 3 and 4 each processed J1; iteration 6 saw a change on J2
    # but could not process it because the handler was gone.
    assert handler.paths == [j1, j1, j1]
    assert watcher._poll_last_path == j1
    assert watcher._poll_last_checked_at is not None


async def test_poll_loop_reraises_cancellation_from_handler(tmp_path: Path) -> None:
    """CancelledError raised while processing propagates out of the loop."""
    watch_dir = tmp_path / "journals"
    watch_dir.mkdir()
    _write_journal(watch_dir, "Journal.2026-01-01T000000.01.log", BASE_MTIME)

    class _CancellingHandler:
        async def _process_file(self, file_path: Path) -> None:
            raise asyncio.CancelledError()

    watcher = _make_watcher()
    watcher._handler = _CancellingHandler()  # type: ignore[assignment]

    with pytest.raises(asyncio.CancelledError):
        await watcher._poll_for_latest_changes(watch_dir)


async def test_poll_loop_records_generic_errors_and_clock_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Handler failures are logged and recorded; clock failures are ignored."""
    watch_dir = tmp_path / "journals"
    watch_dir.mkdir()
    _write_journal(watch_dir, "Journal.2026-01-01T000000.01.log", BASE_MTIME)

    class _FailingHandler:
        async def _process_file(self, file_path: Path) -> None:
            raise ValueError("parse exploded")

    watcher = _make_watcher()
    watcher._handler = _FailingHandler()  # type: ignore[assignment]

    with monkeypatch.context() as mp:
        mp.setitem(sys.modules, "datetime", _broken_datetime_module())
        mp.setattr(asyncio, "sleep", _scripted_sleep([]))
        with pytest.raises(asyncio.CancelledError):
            await watcher._poll_for_latest_changes(watch_dir)

    assert watcher._poll_last_error == (
        "Polling fallback encountered an error; see logs"
    )
    # The broken clock means the diagnostic timestamp was never recorded.
    assert watcher._poll_last_checked_at is None


class _ExplodingErrorFieldWatcher(FileWatcher):
    """FileWatcher variant whose _poll_last_error assignment can be armed to fail.

    This exercises the innermost defensive except in the polling loop where
    even recording the error message fails.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._arm_explosion = False
        super().__init__(*args, **kwargs)

    @property
    def _poll_last_error(self) -> Optional[str]:
        return self.__dict__.get("_poll_last_error_value")

    @_poll_last_error.setter
    def _poll_last_error(self, value: Optional[str]) -> None:
        if self._arm_explosion:
            raise RuntimeError("diagnostics store unavailable")
        self.__dict__["_poll_last_error_value"] = value


async def test_poll_loop_swallows_error_recording_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a failing error-field assignment must not break the poll loop."""
    watch_dir = tmp_path / "journals"
    watch_dir.mkdir()
    _write_journal(watch_dir, "Journal.2026-01-01T000000.01.log", BASE_MTIME)

    watcher = _ExplodingErrorFieldWatcher(
        parser=_StubParser(),  # type: ignore[arg-type]
        system_tracker=_StubTracker(),  # type: ignore[arg-type]
        repository=_StubRepo(),  # type: ignore[arg-type]
        loop=_DummyLoop(),  # type: ignore[arg-type]
    )
    handler = _RecordingHandler()
    watcher._handler = handler  # type: ignore[assignment]
    watcher._arm_explosion = True

    with monkeypatch.context() as mp:
        mp.setattr(asyncio, "sleep", _scripted_sleep([]))
        with pytest.raises(asyncio.CancelledError):
            await watcher._poll_for_latest_changes(watch_dir)

    # The change-branch reset of _poll_last_error raised before processing,
    # so the handler was never invoked and no error message was stored.
    assert handler.paths == []
    assert watcher._poll_last_error is None


# ---------------------------------------------------------------------------
# _process_existing_files
# ---------------------------------------------------------------------------


async def test_process_existing_files_skips_when_handler_missing(
    tmp_path: Path,
) -> None:
    """Existing journals are ignored when no handler has been created yet."""
    watch_dir = tmp_path / "journals"
    watch_dir.mkdir()
    _write_journal(watch_dir, "Journal.2026-01-01T000000.01.log", BASE_MTIME)

    watcher = _make_watcher()
    assert watcher._handler is None

    # Must complete without error despite the missing handler.
    await watcher._process_existing_files(watch_dir)
