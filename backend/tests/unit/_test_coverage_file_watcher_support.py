"""Shared scaffolding for the test_coverage_file_watcher modules.

Split out of test_coverage_file_watcher.py when that file passed the module cap. Not
named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
import asyncio
import os
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from src.services.file_watcher import FileWatcher


BASE_MTIME = 1_700_000_000.0


MTIME_STEP = 100.0


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
