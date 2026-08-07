"""Polling fallback.

Split out of test_coverage_file_watcher.py; the scaffolding lives in _test_coverage_file_watcher_support.py.
"""

import asyncio
import os
import sys
from pathlib import Path
import pytest
import src.services.file_watcher_polling as polling_module

from tests.unit._test_coverage_file_watcher_support import (
    BASE_MTIME,
    MTIME_STEP,
    _DummyLoop,
    _ExplodingErrorFieldWatcher,
    _PendingTask,
    _RecordingHandler,
    _StubParser,
    _StubRepo,
    _StubTracker,
    _broken_datetime_module,
    _make_watcher,
    _scripted_sleep,
    _write_journal,
)


def test_start_polling_disabled_outside_frozen_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Polling is a packaged-runtime feature only."""
    monkeypatch.setattr(polling_module, "is_frozen", lambda: False)
    watcher = _make_watcher()

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is None


def test_start_polling_skips_when_task_already_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live poller task is never replaced."""
    monkeypatch.setattr(polling_module, "is_frozen", lambda: True)
    watcher = _make_watcher()
    pending = _PendingTask()
    watcher._poll_task = pending  # type: ignore[assignment]

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is pending


async def test_start_polling_creates_task_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In frozen mode a real poller task is created."""
    monkeypatch.setattr(polling_module, "is_frozen", lambda: True)
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
    monkeypatch.setattr(polling_module, "is_frozen", lambda: True)
    watcher = _make_watcher()

    def not_a_coroutine(directory: Path) -> object:
        # Returning a plain object makes asyncio.create_task raise TypeError
        # without leaving an unawaited coroutine behind.
        return object()

    monkeypatch.setattr(watcher, "_poll_for_latest_changes", not_a_coroutine)

    watcher._start_polling_if_enabled(tmp_path)

    assert watcher._poll_task is None


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
