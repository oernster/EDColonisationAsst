"""File watcher service for monitoring journal files."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional

from watchdog.observers import Observer

from .journal_parser import IJournalParser
from .system_tracker import ISystemTracker
from .journal_ingestion import JournalFileHandler
from ..repositories.colonisation_repository import IColonisationRepository
from ..utils.logger import get_logger
from ..utils.runtime import is_frozen

logger = get_logger(__name__)


class IFileWatcher(ABC):
    """Interface for file watching."""

    @abstractmethod
    async def start_watching(self, directory: Path) -> None:
        """Start watching directory for changes."""
        raise NotImplementedError

    @abstractmethod
    async def stop_watching(self) -> None:
        """Stop watching directory."""
        raise NotImplementedError

    @abstractmethod
    def set_update_callback(self, callback: Callable) -> None:
        """Set callback for when data is updated."""
        raise NotImplementedError


class FileWatcher(IFileWatcher):
    """
    Watches the Elite: Dangerous journal directory for changes.

    Responsibilities:
    - Owns a watchdog Observer that tracks filesystem changes.
    - Creates and wires a JournalFileHandler instance to process journal
      files via the injected parser, system tracker and repository.
    - Optionally invokes an async update callback for each affected system.
    """

    def __init__(
        self,
        parser: IJournalParser,
        system_tracker: ISystemTracker,
        repository: IColonisationRepository,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.parser = parser
        self.system_tracker = system_tracker
        self.repository = repository
        self._observer: Optional[Observer] = None
        self._handler: Optional[JournalFileHandler] = None
        self._update_callback: Optional[Callable] = None
        self._directory: Optional[Path] = None
        # Event loop used to schedule async processing from watchdog threads.
        self._loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

        # Fallback polling for environments where watchdog events are unreliable
        # (observed in some packaged/installed contexts).
        self._poll_task: Optional[asyncio.Task[None]] = None
        self._poll_interval_s: float = 1.0
        self._poll_last_path: Optional[Path] = None
        self._poll_last_mtime: float | None = None

    def is_running(self) -> bool:
        """Return True if the watchdog observer is active."""
        if self._observer is None:
            return False
        # watchdog Observer exposes is_alive() on its thread-like object.
        try:
            return bool(getattr(self._observer, "is_alive")())
        except Exception:
            # Best-effort fallback.
            return True

    def poller_running(self) -> bool:
        """Return True if the polling fallback task is active."""
        return self._poll_task is not None and not self._poll_task.done()

    def watched_directory(self) -> Optional[Path]:
        """Return the current watched directory, if any."""
        return self._directory

    def set_update_callback(self, callback: Callable) -> None:
        """
        Set callback for when data is updated.

        Args:
            callback: async function to call with system_name when updated.
        """
        self._update_callback = callback
        if self._handler is not None:
            self._handler.update_callback = callback

    async def start_watching(self, directory: Path) -> None:
        """
        Start watching a directory for changes.

        Args:
            directory: Path to journal directory.
        """
        if self._observer is not None:
            logger.warning("File watcher already running")
            return

        if not directory.exists():
            logger.error("Journal directory does not exist: %s", directory)
            raise FileNotFoundError(f"Journal directory not found: {directory}")

        self._directory = directory

        # Create handler
        self._handler = JournalFileHandler(
            self.parser,
            self.system_tracker,
            self.repository,
            self._update_callback,
            loop=self._loop,
        )

        # Create and start observer
        self._observer = Observer()
        self._observer.schedule(self._handler, str(directory), recursive=False)
        self._observer.start()

        # If the observer thread immediately died, treat this as a failure and
        # still allow the polling fallback to run.
        try:
            alive = bool(getattr(self._observer, "is_alive")())
        except Exception:
            alive = True

        if alive:
            logger.info("Started watching journal directory: %s", directory)
        else:
            logger.error(
                "Watchdog observer thread is not alive after start(); live events may be unavailable"
            )

        # Process existing files
        await self._process_existing_files(directory)

        # In the packaged runtime, watchdog can fail to deliver events on some
        # systems (or deliver only directory events). As a safety net, also
        # poll for file mtime changes and process the newest journal.
        self._start_polling_if_enabled(directory)

    async def stop_watching(self) -> None:
        """Stop watching directory."""
        # Stop polling first so we don't race with handler teardown.
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001
                logger.exception("Error while stopping poller task")
            finally:
                self._poll_task = None
                self._poll_last_path = None
                self._poll_last_mtime = None

        if self._observer is None:
            return

        self._observer.stop()
        self._observer.join()
        self._observer = None
        self._handler = None
        self._directory = None

        logger.info("Stopped watching journal directory")

    # ------------------------------------------------------------------ polling fallback

    def _start_polling_if_enabled(self, directory: Path) -> None:
        """Start the polling fallback task (packaged runtime only)."""
        # Only enable in frozen runtime to avoid duplicate work during dev.
        if not is_frozen():
            return
        if self._poll_task is not None:
            return

        try:
            self._poll_task = asyncio.create_task(
                self._poll_for_latest_changes(directory),
                name="edca-journal-poller",
            )
            logger.info(
                "Started journal polling fallback (interval=%ss) for %s",
                self._poll_interval_s,
                directory,
            )
        except Exception:  # noqa: BLE001
            # Polling is best-effort; watchdog remains the primary mechanism.
            logger.exception("Failed to start polling fallback")

    async def _poll_for_latest_changes(self, directory: Path) -> None:
        """Periodically process the newest Journal.*.log when it changes."""
        # Small epsilon to avoid float edge cases.
        epsilon = 1e-6
        while True:
            try:
                journal_files = list(directory.glob("Journal.*.log"))
                if journal_files:
                    # Newest file by modified time.
                    latest = max(journal_files, key=lambda p: p.stat().st_mtime)
                    latest_mtime = latest.stat().st_mtime

                    changed = False
                    if self._poll_last_path is None or latest != self._poll_last_path:
                        changed = True
                    elif self._poll_last_mtime is None:
                        changed = True
                    elif latest_mtime > (self._poll_last_mtime + epsilon):
                        changed = True

                    if changed and self._handler is not None:
                        self._poll_last_path = latest
                        self._poll_last_mtime = latest_mtime
                        await self._handler._process_file(latest)  # noqa: SLF001
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Polling fallback encountered an error")

            await asyncio.sleep(self._poll_interval_s)

    async def _process_existing_files(self, directory: Path) -> None:
        """
        Process existing journal files in a directory.

        Args:
            directory: Path to journal directory.
        """
        logger.info("Processing existing journal files...")

        # Find all journal files
        journal_files = sorted(
            directory.glob("Journal.*.log"), key=lambda p: p.stat().st_mtime
        )

        if not journal_files:
            logger.warning("No existing journal files found")
            return

        # Process all existing files
        for file_path in journal_files:
            logger.info("Processing journal file: %s", file_path.name)
            if self._handler is not None:
                await self._handler._process_file(file_path)  # noqa: SLF001
