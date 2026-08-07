"""File watcher service for monitoring journal files."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Callable
from datetime import UTC
from pathlib import Path

from watchdog.observers import Observer

from ..repositories.colonisation_repository import IColonisationRepository
from ..utils.logger import get_logger
from .file_watcher_polling import PollingFallbackMixin
from .journal_ingestion import JournalFileHandler
from .journal_parser import IJournalParser
from .system_tracker import ISystemTracker

logger = get_logger(__name__)


class IFileWatcher(ABC):
    """Interface for file watching."""

    @abstractmethod
    async def start_watching(
        self, directory: Path, process_existing: bool = True
    ) -> None:
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


class FileWatcher(PollingFallbackMixin, IFileWatcher):
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
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self.parser = parser
        self.system_tracker = system_tracker
        self.repository = repository
        self._observer: Observer | None = None
        self._handler: JournalFileHandler | None = None
        self._update_callback: Callable | None = None
        self._directory: Path | None = None
        self._watchdog_started_at: str | None = None
        self._watchdog_last_error: str | None = None
        # Event loop used to schedule async processing from watchdog threads.
        self._loop: asyncio.AbstractEventLoop = loop or asyncio.get_event_loop()

        # Fallback polling for environments where watchdog events are unreliable
        # (observed in some packaged/installed contexts).
        self._poll_task: asyncio.Task[None] | None = None
        # Smaller interval improves perceived immediacy in packaged mode where
        # watchdog may be unavailable.
        self._poll_interval_s: float = 0.25
        self._poll_last_path: Path | None = None
        self._poll_last_mtime: float | None = None
        self._poll_last_checked_at: str | None = None
        self._poll_last_error: str | None = None

    def is_running(self) -> bool:
        """Return True if the watchdog observer is active."""
        if self._observer is None:
            return False
        # watchdog Observer exposes is_alive() on its thread-like object.
        try:
            return bool(self._observer.is_alive())
        except Exception:  # noqa: BLE001
            # Best-effort fallback.
            return True

    def watchdog_status(self) -> dict:
        """Return diagnostic status for the watchdog observer."""
        alive = None
        try:
            alive = (
                bool(self._observer.is_alive()) if self._observer is not None else False
            )
        except Exception:  # noqa: BLE001
            # Deliberately broad. watchdog's Observer is a thread subclass whose
            # is_alive() reaches into platform observer internals, so its failure modes
            # are not enumerable from here. None means 'cannot tell', which the status
            # endpoint renders as such.
            alive = None

        return {
            "configured": self._observer is not None,
            "alive": alive,
            "started_at": self._watchdog_started_at,
            "last_error": self._watchdog_last_error,
        }

    def poller_running(self) -> bool:
        """Return True if the polling fallback task is active."""
        return self._poll_task is not None and not self._poll_task.done()

    def poller_status(self) -> dict:
        """Return diagnostic status for the polling fallback."""
        task = self._poll_task
        exc: str | None = None
        done = None
        try:
            done = task.done() if task is not None else None
            if task is not None and task.done():
                try:
                    task_exc = task.exception()
                except asyncio.CancelledError:
                    task_exc = None
                except Exception as e:  # noqa: BLE001
                    # Deliberately broad. Task.exception() re-raises whatever the task
                    # failed with; that task runs the polling loop, so this is the
                    # failure being reported rather than a new one. Capturing it is the
                    # point.
                    task_exc = e
                if task_exc is not None:
                    exc = f"{type(task_exc).__name__}: {task_exc}"
        except Exception:  # noqa: BLE001
            # Deliberately broad. Reading a task's completion state can race with the
            # loop shutting down. None means 'cannot tell', which is what the diagnostic
            # reports.
            done = None

        return {
            "running": self.poller_running(),
            "task_done": done,
            "task_exception": exc,
            "last_checked_at": self._poll_last_checked_at,
            "last_seen_file": str(self._poll_last_path)
            if self._poll_last_path
            else None,
            "last_seen_mtime": self._poll_last_mtime,
            "last_error": self._poll_last_error,
            "interval_s": self._poll_interval_s,
        }

    def watched_directory(self) -> Path | None:
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

    async def start_watching(
        self, directory: Path, process_existing: bool = True
    ) -> None:
        """
        Start watching a directory for changes.

        Args:
            directory: Path to journal directory.
            process_existing: When True (the default), synchronously scan and
                ingest all existing journal files before returning. The
                packaged runtime passes False so this potentially minutes-long
                full-history scan does not block server readiness; the initial
                catch-up is instead performed by a background task in the
                application lifespan.
        """
        if self._observer is not None:
            # If the previous observer thread died, treat this as a restart.
            try:
                alive = bool(self._observer.is_alive())
            except Exception:  # noqa: BLE001
                # Deliberately broad. watchdog's Observer is a thread subclass whose
                # is_alive() reaches into platform observer internals, so its failure
                # modes are not enumerable from here. Assuming alive is the conservative
                # answer: it keeps the existing observer rather than starting a second
                # one.
                alive = True

            if alive:
                logger.warning("File watcher already running")
                return

            logger.warning(
                "File watcher observer exists but is not alive; restarting watcher"
            )
            await self.stop_watching()

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

        # Always attempt to start watchdog but treat failures as non-fatal.
        # The polling fallback can still provide live-ish updates.
        self._watchdog_last_error = None
        try:
            from datetime import datetime

            self._watchdog_started_at = datetime.now(UTC).isoformat()
        except Exception:  # noqa: BLE001
            # Deliberately broad. This only stamps a start time for diagnostics. A
            # missing stamp is invisible; failing here would abandon a watcher that
            # started successfully.
            self._watchdog_started_at = None

        try:
            self._observer = Observer()
            self._observer.schedule(self._handler, str(directory), recursive=False)
            self._observer.start()

            try:
                alive = bool(self._observer.is_alive())
            except Exception:  # noqa: BLE001
                # Deliberately broad. watchdog's Observer is a thread subclass whose
                # is_alive() reaches into platform observer internals, so its failure
                # modes are not enumerable from here. Assuming alive keeps the watcher
                # that has just been started.
                alive = True

            if alive:
                logger.info("Started watching journal directory: %s", directory)
            else:
                self._watchdog_last_error = (
                    "Observer thread is not alive after start(); "
                    "watchdog events unavailable"
                )
                logger.error(self._watchdog_last_error)
        except Exception as exc:
            # Deliberately broad, the reason the polling fallback exists. watchdog
            # sits on OS notification APIs whose failures are platform-specific and
            # open-ended. Recording the error and falling through to polling is what
            # keeps live updates working.
            self._watchdog_last_error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Failed to start watchdog observer: %s", self._watchdog_last_error
            )
            self._observer = None

        # Process existing files but never prevent polling from starting.
        # When process_existing is False the caller (the packaged lifespan)
        # performs the initial catch-up in the background so that starting the
        # watcher stays fast and does not block server readiness.
        try:
            if process_existing:
                await self._process_existing_files(directory)
        except Exception:
            # Deliberately broad. This scans journal files the game owns, so one
            # unreadable file must not stop the watcher from starting. Logged with a
            # traceback and then dropped.
            logger.exception("Error while processing existing journals")
        finally:
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
            except Exception:
                # Deliberately broad, on the shutdown path. Awaiting a cancelled task
                # surfaces whatever it died of; none of it should stop the rest of the
                # shutdown.
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
        self._watchdog_started_at = None
        self._watchdog_last_error = None

        logger.info("Stopped watching journal directory")

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
                await self._handler._process_file(file_path)
