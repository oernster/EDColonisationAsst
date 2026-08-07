"""Shared scaffolding for the test_file_watcher modules.

Split out of test_file_watcher.py when that file passed the module cap. Not named
test_* on purpose: pytest collects only the modules that use it.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, UTC
from pathlib import Path
import pytest
import src.services.file_watcher as fw_module
from src.models.colonisation import ConstructionSite, Commodity
from src.models.journal_events import (
    ColonisationConstructionDepotEvent,
    ColonisationContributionEvent,
    DockedEvent,
)
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.file_watcher import FileWatcher, JournalFileHandler
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker


class _DummyParser:
    """Minimal parser implementation for JournalFileHandler tests."""

    def parse_file(self, file_path: Path):
        return []

    def parse_line(self, line: str):
        return None


class _DummyObserver:
    """Lightweight stand-in for watchdog.observers.Observer used in FileWatcher tests."""

    def __init__(self) -> None:
        self.scheduled: list[tuple[object, str, bool]] = []
        self.started = False
        self.stopped = False
        self.joined = False

    def schedule(self, handler, path: str, recursive: bool) -> None:
        self.scheduled.append((handler, path, recursive))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True
