"""A real watchdog Observer delivers a journal append to the app's handler.

Every other watcher test replaces the Observer with a fake, so a watchdog that
cannot start on the running interpreter went unnoticed: watchdog 3.0.0 raised
TypeError from Observer().start() on Python 3.13, FileWatcher recorded it as a
non-fatal error and the suite still passed. This test starts the production
FileWatcher on a temporary directory with nothing replaced except the polling
gate, which is held shut so the only route from the file to the handler is the
watchdog Observer itself.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import time

import pytest

from src.services import file_watcher_polling
from tests.unit._test_coverage_file_watcher_support import _make_watcher

# Generous on purpose: a slow or busy CI machine must not turn a working
# watcher into a flaky failure. The wait ends as soon as the event lands.
EVENT_TIMEOUT_S = 10.0
POLL_STEP_S = 0.05

JOURNAL_NAME = "Journal.2026-01-01T000000.01.log"
FIRST_LINE = '{"timestamp":"2026-01-01T00:00:00Z","event":"Fileheader"}\n'
APPENDED_LINE = '{"timestamp":"2026-01-01T00:00:01Z","event":"Music"}\n'


async def _wait_until(condition, timeout_s: float) -> bool:
    """Poll condition until it holds or timeout_s passes; answer whether it held."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        await asyncio.sleep(POLL_STEP_S)
    return condition()


async def test_real_observer_delivers_a_journal_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Appending to a journal reaches the handler through watchdog alone."""
    monkeypatch.setattr(file_watcher_polling, "is_packaged", lambda: False)
    journal = tmp_path / JOURNAL_NAME
    journal.write_text(FIRST_LINE, encoding="utf-8")

    watcher = _make_watcher(loop=asyncio.get_running_loop())
    await watcher.start_watching(tmp_path, process_existing=False)
    try:
        assert watcher.poller_running() is False
        assert watcher.is_running(), watcher.watchdog_status()

        with journal.open("a", encoding="utf-8") as stream:
            stream.write(APPENDED_LINE)

        handler = watcher._handler
        assert handler is not None
        seen = await _wait_until(
            lambda: handler.last_processed_file == str(journal), EVENT_TIMEOUT_S
        )
        assert seen, watcher.watchdog_status()
        assert handler.last_watchdog_event_path == str(journal)
    finally:
        await watcher.stop_watching()
