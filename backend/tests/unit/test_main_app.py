"""Tests for the main FastAPI application wiring and lifespan (no external mocking frameworks)."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.main as main_mod
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.data_aggregator import DataAggregator
from src.services.system_tracker import SystemTracker


@pytest.mark.asyncio
async def test_main_lifespan_wires_dependencies_and_stops_watcher():
    """lifespan should construct core services, wire dependencies, and stop the watcher on shutdown."""
    created: dict[str, object] = {}

    class DummyFileWatcher:
        """In-memory replacement for FileWatcher used to observe lifecycle calls."""

        def __init__(self, parser, system_tracker, repository) -> None:  # type: ignore[override]
            self.parser = parser
            self.system_tracker = system_tracker
            self.repository = repository
            self.update_callback = None
            self.start_calls: list[Path] = []
            self.stop_calls = 0
            created["instance"] = self

        def set_update_callback(self, callback) -> None:
            self.update_callback = callback

        async def start_watching(self, directory: Path) -> None:
            self.start_calls.append(directory)

        async def stop_watching(self) -> None:
            self.stop_calls += 1

    # Patch FileWatcher in the main module so the lifespan uses our dummy implementation.
    orig_file_watcher_cls = main_mod.FileWatcher
    try:
        main_mod.FileWatcher = DummyFileWatcher  # type: ignore[assignment]

        # Enter and exit the lifespan context manually to avoid starting a real watchdog observer.
        async with main_mod.lifespan(main_mod.app):
            # During the lifespan body, core components should be initialised on app.state.
            repo = getattr(main_mod.app.state, "repository", None)
            agg = getattr(main_mod.app.state, "aggregator", None)
            tracker = getattr(main_mod.app.state, "system_tracker", None)
            watcher = getattr(main_mod.app.state, "file_watcher", None)

            assert isinstance(repo, ColonisationRepository)
            assert isinstance(agg, DataAggregator)
            assert isinstance(tracker, SystemTracker)
            assert isinstance(watcher, DummyFileWatcher)

            # File watcher should have been wired with an async update callback.
            # (Implementation may wrap notify_system_update to also trigger
            # a global refresh hint.)
            assert callable(watcher.update_callback)

            # Root endpoint should return basic app metadata
            root_resp = await main_mod.root()
            assert root_resp["name"]
            assert root_resp["status"] == "running"
            assert "version" in root_resp
            assert root_resp["docs"] == "/docs"

        # After exiting the lifespan context, the dummy watcher should have been stopped once.
        watcher = created.get("instance")
        assert isinstance(watcher, DummyFileWatcher)
        assert watcher.stop_calls == 1
        # start_watching should have been invoked at least once with some directory
        assert watcher.start_calls
    finally:
        main_mod.FileWatcher = orig_file_watcher_cls  # type: ignore[assignment]
