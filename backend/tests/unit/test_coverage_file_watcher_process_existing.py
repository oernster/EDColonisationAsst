from __future__ import annotations

"""Coverage for the process_existing flag on FileWatcher.start_watching.

The packaged runtime starts the watcher with process_existing=False so the
initial full-history journal scan does not block server readiness (the
lifespan performs that catch-up in the background instead). This exercises
that skip path and confirms the default still scans.
"""

from pathlib import Path
from typing import Any

import pytest

import src.services.file_watcher as fw_module
from src.services.file_watcher import FileWatcher


class _HealthyObserver:
    """Fake watchdog Observer that starts cleanly and reports alive."""

    def schedule(self, handler: Any, path: str, recursive: bool) -> None:
        return None

    def start(self) -> None:
        return None

    def is_alive(self) -> bool:
        return True

    def stop(self) -> None:
        return None

    def join(self) -> None:
        return None


class _StubParser:
    pass


class _StubTracker:
    pass


class _StubRepo:
    pass


class _DummyLoop:
    pass


def _make_watcher() -> FileWatcher:
    return FileWatcher(
        parser=_StubParser(),  # type: ignore[arg-type]
        system_tracker=_StubTracker(),  # type: ignore[arg-type]
        repository=_StubRepo(),  # type: ignore[arg-type]
        loop=_DummyLoop(),  # type: ignore[arg-type]
    )


async def test_start_watching_skips_existing_scan_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process_existing=False must not run the full existing-file scan."""
    monkeypatch.setattr(fw_module, "Observer", _HealthyObserver)
    # Polling only starts in the frozen runtime; keep it off so no task leaks.
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

    watcher = _make_watcher()

    processed: list[Path] = []

    async def _record(directory: Path) -> None:
        processed.append(directory)

    monkeypatch.setattr(watcher, "_process_existing_files", _record)

    await watcher.start_watching(tmp_path, process_existing=False)

    assert processed == []
    assert watcher._directory == tmp_path


async def test_start_watching_runs_existing_scan_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default (process_existing=True) still performs the scan."""
    monkeypatch.setattr(fw_module, "Observer", _HealthyObserver)
    monkeypatch.setattr(fw_module, "is_frozen", lambda: False)

    watcher = _make_watcher()

    processed: list[Path] = []

    async def _record(directory: Path) -> None:
        processed.append(directory)

    monkeypatch.setattr(watcher, "_process_existing_files", _record)

    await watcher.start_watching(tmp_path)

    assert processed == [tmp_path]
