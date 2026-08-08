"""Journal catch-up performed once at application startup.

Two paths, chosen by whether the database already holds anything:

- `prime_colonisation_database_if_empty` is the first-run backfill. A fresh
  install with years of existing journals should show its construction sites
  without the user reaching for a manual reload, so this walks the whole
  journal directory once.
- `sync_latest_journals_best_effort` is the repeat-run path. The packaged
  runtime persists its database under `%LOCALAPPDATA%`, which survives a
  reinstall, so the full history is already there and only the tail can be
  stale. Re-reading everything on every launch would cost minutes for nothing.

Both run as a detached task, which is why both are written to degrade rather
than raise: startup ingestion failing must never stop the server answering
`/api/health`. Both drive the same `JournalFileHandler` the live watcher uses,
so the merge rules that stop a stale snapshot regressing progress apply
identically here.

Detached from the lifespan is NOT detached from the event loop; the
first-run path used to prove it: against a real 72-file, 67 MB journal folder
it took 137 s and held the loop for every one of them in a single unbroken
stall, so `/api/health` went unanswered and the startup splash sat there. The
cost was never parsing (0.3 s of it); it was one SQLite commit per depot
event, roughly 4,000 of them, each on a connection of its own. Two changes
fixed it, both worth keeping: colonisation_db shares one connection and runs
in WAL, which took the import to 3 s; the loop below then hands control back
between files so that what remains is not one uninterrupted block.

`lifespan` in backend/src/main.py owns the choice between them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import get_config
from ..repositories.colonisation_repository import ColonisationRepository
from ..utils.logger import get_logger
from .change_bus import change_bus
from .journal_ingestion import JournalFileHandler
from .journal_parser import JournalParser
from .startup_progress import startup_progress
from .system_tracker import SystemTracker

logger = get_logger(__name__)

_JOURNAL_GLOB = "Journal.*.log"

# How many of the most recent journal files the repeat-run path re-reads.
# Enough to catch a session the watcher missed, few enough to keep startup
# bounded.
_TAIL_JOURNAL_FILE_COUNT = 3


def _journal_files_oldest_first(journal_dir: Path) -> list[Path]:
    """Journal files in the directory, oldest modification first.

    Order matters: newer depot snapshots must be ingested after older ones so
    the later reading is the one that wins the merge.
    """
    return sorted(journal_dir.glob(_JOURNAL_GLOB), key=lambda p: p.stat().st_mtime)


def _file_size(path: Path) -> int:
    """The file's size, or zero when it cannot be read.

    Only used to weight a progress bar, so a file that disappeared between
    being listed and being measured contributes nothing, which is honest.
    """
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _build_handler(
    parser: JournalParser,
    system_tracker: SystemTracker,
    repository: ColonisationRepository,
    loop: asyncio.AbstractEventLoop,
) -> JournalFileHandler:
    """Build the same ingestion handler the live file watcher uses."""
    return JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=loop,
    )


async def prime_colonisation_database_if_empty(
    repository: ColonisationRepository,
    parser: JournalParser,
    system_tracker: SystemTracker,
) -> None:
    """
    On first run (or after the database has been deleted), backfill the
    colonisation database from existing journal files.

    This mirrors the behaviour of the /api/debug/reload-journals endpoint but
    is applied automatically when the database contains no sites. It ensures
    that a fresh installation with existing Elite journals immediately shows
    construction sites and delivered commodities without requiring a manual
    reload step.
    """
    try:
        stats = await repository.get_stats()
    except Exception as exc:  # noqa: BLE001
        # Deliberately broad: this is the repository interface, so the
        # concrete failure depends on the implementation behind it (sqlite3
        # errors today, anything tomorrow). The preload is an optimisation for
        # a fresh install, so skipping it degrades nothing the user can see.
        logger.warning(
            "Initial journal preload skipped: failed to read repository stats: %s",
            exc,
        )
        return

    total_sites = stats.get("total_sites", 0)
    if total_sites > 0:
        logger.info(
            "Initial journal preload skipped: repository already contains %s site(s)",
            total_sites,
        )
        return

    try:
        config = get_config()
        journal_dir = Path(config.journal.directory)
    except Exception as exc:  # noqa: BLE001
        # Deliberately broad: get_config parses user-edited YAML and builds
        # pydantic models, so a bad value surfaces as a validation error rather
        # than one predictable type. Without a journal directory there is
        # nothing to preload, so returning is the whole recovery.
        logger.warning(
            "Initial journal preload skipped: failed to resolve journal directory: %s",
            exc,
        )
        return

    if not journal_dir.exists():
        logger.info(
            "Initial journal preload skipped: journal directory %s does not exist",
            journal_dir,
        )
        return

    journal_files = _journal_files_oldest_first(journal_dir)
    if not journal_files:
        logger.info(
            "Initial journal preload skipped: no %s files found in %s",
            _JOURNAL_GLOB,
            journal_dir,
        )
        return

    handler = _build_handler(
        parser, system_tracker, repository, asyncio.get_running_loop()
    )

    # Sizes are taken once, before any reading, so the splash can show a real
    # total rather than a bar that grows its own denominator as it goes. A
    # file that vanishes between listing and reading counts as nothing, which
    # is also what it contributes.
    file_sizes = [_file_size(path) for path in journal_files]
    startup_progress.begin_import(file_sizes)

    processed_files = 0
    for journal_file, file_size in zip(journal_files, file_sizes, strict=True):
        # Hand the loop back between files. Every await inside _process_file
        # resolves without suspending, so without this the whole import runs as
        # one uninterrupted block and the server cannot answer /api/health for
        # its duration, however fast the import itself becomes.
        await asyncio.sleep(0)
        try:
            await handler._process_file(journal_file)
            processed_files += 1
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad; per file on purpose. These are journal
            # files written by the game across years of format changes, so one
            # unparseable file must not abandon the remaining history. The
            # loop continues and the count below reports what got through.
            logger.error(
                "Error preloading journal file %s during initial import: %s",
                journal_file,
                exc,
            )
        finally:
            # Counted whether or not it parsed: an unreadable file still took
            # its share of the wait, so a bar that stalled on one would be
            # reporting the wrong thing.
            startup_progress.file_imported(file_size)

    startup_progress.finish()

    logger.info(
        "Initial journal preload completed: processed %s journal file(s) from %s",
        processed_files,
        journal_dir,
    )


async def sync_latest_journals_best_effort(
    parser: JournalParser,
    system_tracker: SystemTracker,
    repository: ColonisationRepository,
    journal_dir: Path,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Best-effort sync of the most recent journal files.

    Motivation:
    - The packaged runtime persists its SQLite DB under %LOCALAPPDATA%.
      Reinstalling the app does not necessarily delete that DB.
    - If the DB is stale (e.g. older depot snapshot values) and watchdog events
      are unavailable, users can see old numbers until a manual reload.

    Strategy:
    - Process the most recently modified N journal files (oldest->newest) so
      newer depot snapshots win.
    - Use the same JournalFileHandler ingestion path so merge logic applies.
    - Send a global refresh hint at the end so the UI refetches.

    This is intentionally non-fatal.
    """
    try:
        if not journal_dir.exists():
            return

        journal_files = _journal_files_oldest_first(journal_dir)
        if not journal_files:
            return

        # Process only the tail of history to keep startup cost bounded.
        tail = journal_files[-_TAIL_JOURNAL_FILE_COUNT:]

        startup_progress.begin_catch_up()

        handler = _build_handler(parser, system_tracker, repository, loop)
        for journal_file in tail:
            await handler._process_file(journal_file)

        # Signal UI clients (AJAX long-poll) that data may have changed.
        await notify_clients_best_effort()
    except Exception:
        # Deliberately broad, as the docstring above says: this whole function
        # is a best-effort catch-up over game-written files and must never
        # take startup down with it. Logged with a traceback, then dropped.
        logger.exception("Best-effort latest journal sync failed")
    finally:
        # Whichever way the catch-up ended, startup is no longer waiting on
        # it, and a splash left reading "catching up" would say otherwise.
        startup_progress.finish()


async def notify_clients_best_effort() -> None:
    """Bump the change sequence so long-poll clients refetch.

    Deliberately broad; deliberately not narrowed. change_bus is a
    module-level singleton holding an asyncio.Condition. The obvious candidate
    (a bump from a different event loop) does not raise: measured on CPython
    3.13, reusing a Condition across loops completes silently. No failure mode
    could be demonstrated, so there is no honest type to name here. The guard
    stays because the cost of being wrong is asymmetric: swallowing it loses
    one refresh hint that the next poll recovers, while letting it out would
    fail the caller.
    """
    try:
        await change_bus.bump()
    except Exception:  # noqa: BLE001, S110
        pass


__all__ = [
    "notify_clients_best_effort",
    "prime_colonisation_database_if_empty",
    "sync_latest_journals_best_effort",
]
