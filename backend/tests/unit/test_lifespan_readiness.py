from __future__ import annotations

"""Regression guard: server readiness must not block on journal ingestion.

The packaged runtime starts an in-process uvicorn server and only becomes
able to answer /api/health once ASGI lifespan startup completes. If the
initial full-history journal import runs on that path, the startup splash
freezes for minutes on a large journal folder. These tests drive the real
[`lifespan`](backend/src/main.py:1) with a deliberately slow prime and fake
collaborators, asserting that entering the lifespan returns promptly while
the import runs in the background and bumps the change bus.

main.py is excluded from the coverage gate, so this test exists purely as a
behavioural regression guard, not for coverage.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest

import src.main as main
from src.services.change_bus import change_bus

SLOW_PRIME_SECONDS = 0.3
READINESS_BUDGET_SECONDS = 0.1


class _FakeRepo:
    def __init__(self, total_sites: int = 0) -> None:
        self._total_sites = total_sites

    async def get_stats(self) -> dict[str, int]:
        return {"total_sites": self._total_sites}


class _FakeWatcher:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.process_existing_arg: bool | None = None

    def set_update_callback(self, callback: Any) -> None:
        self._callback = callback

    async def start_watching(
        self, directory: Path, process_existing: bool = True
    ) -> None:
        self.process_existing_arg = process_existing

    async def stop_watching(self) -> None:
        return None


def _patch_common(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    repo: _FakeRepo,
) -> dict[str, Any]:
    """Swap heavy collaborators for fakes; keep the real lifespan flow."""
    cfg = main.get_config()
    cfg.journal.directory = str(tmp_path)
    monkeypatch.setattr(main, "get_config", lambda: cfg)
    monkeypatch.setattr(main, "ColonisationRepository", lambda *a, **k: repo)
    monkeypatch.setattr(main, "DataAggregator", lambda *a, **k: object())
    monkeypatch.setattr(main, "SystemTracker", lambda *a, **k: object())
    monkeypatch.setattr(main, "JournalParser", lambda *a, **k: object())
    monkeypatch.setattr(main, "set_dependencies", lambda *a, **k: None)

    captured: dict[str, Any] = {}

    def _make_watcher(*a: Any, **k: Any) -> _FakeWatcher:
        watcher = _FakeWatcher()
        captured["watcher"] = watcher
        return watcher

    monkeypatch.setattr(main, "FileWatcher", _make_watcher)
    return captured


async def test_first_run_prime_does_not_block_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty DB schedules the full prime in the background, not inline."""
    repo = _FakeRepo(total_sites=0)
    captured = _patch_common(monkeypatch, tmp_path, repo)

    prime_done = {"flag": False}

    async def _slow_prime(repository: Any, parser: Any, tracker: Any) -> None:
        await asyncio.sleep(SLOW_PRIME_SECONDS)
        prime_done["flag"] = True

    monkeypatch.setattr(main, "_prime_colonisation_database_if_empty", _slow_prime)

    seq_before = change_bus.seq
    loop = asyncio.get_running_loop()

    start = loop.time()
    async with main.lifespan(main.app):
        elapsed = loop.time() - start

        # Entering the lifespan == server ready. It must not wait for prime.
        assert elapsed < READINESS_BUDGET_SECONDS
        # The watcher was started off the blocking-scan path.
        assert captured["watcher"].process_existing_arg is False
        # The slow prime is still running in the background.
        assert prime_done["flag"] is False

        await asyncio.sleep(SLOW_PRIME_SECONDS + 0.2)
        assert prime_done["flag"] is True

    assert change_bus.seq > seq_before


async def test_repeat_run_uses_bounded_tail_sync_not_full_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-empty DB runs the bounded tail sync, never the full prime."""
    repo = _FakeRepo(total_sites=5)
    _patch_common(monkeypatch, tmp_path, repo)

    calls: list[str] = []

    async def _prime(repository: Any, parser: Any, tracker: Any) -> None:
        calls.append("prime")

    async def _tail_sync(
        parser: Any,
        tracker: Any,
        repository: Any,
        journal_dir: Path,
        loop: Any,
    ) -> None:
        calls.append("tail")

    monkeypatch.setattr(main, "_prime_colonisation_database_if_empty", _prime)
    monkeypatch.setattr(main, "_sync_latest_journals_best_effort", _tail_sync)

    async with main.lifespan(main.app):
        # Let the scheduled background ingestion task run.
        await asyncio.sleep(0.05)

    assert calls == ["tail"]
