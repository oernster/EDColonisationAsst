"""Main FastAPI application entry point"""

from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from . import __version__
from .config import get_config
from .utils.logger import setup_logging, get_logger
from .utils.runtime import is_frozen
from .services.journal_parser import JournalParser
from .services.file_watcher import FileWatcher
from .services.data_aggregator import DataAggregator
from .services.system_tracker import SystemTracker
from .repositories.colonisation_repository import ColonisationRepository
from .api.routes import router as colonisation_router, set_dependencies
from .api.settings import router as settings_router
from .api.journal import router as journal_router
from .api.carriers import router as carriers_router
from .api.websocket import websocket_endpoint, set_aggregator, notify_system_update

# Setup logging
setup_logging()
logger = get_logger(__name__)

# Project root (installation root when packaged)
#
# In development we keep using the source layout
#   backend/src/main.py -> src -> backend -> project_root
# so PROJECT_ROOT is based on this file location.
#
# In a frozen runtime (Nuitka onefile EXE) we want PROJECT_ROOT to be the
# directory containing the runtime executable, because that is where the
# installer places the "frontend/dist" assets and other payload files.
try:
    if is_frozen():
        # Directory of the running EXE (install root when packaged).
        PROJECT_ROOT = Path(__file__).resolve()
        # In the frozen bundle, __file__ will typically live under the
        # extracted backend package directory. Use sys.argv[0] instead so
        # that we point at the real install directory containing the EXE.
        import sys as _sys  # local import to avoid polluting module namespace

        PROJECT_ROOT = Path(_sys.argv[0]).resolve().parent
    else:
        PROJECT_ROOT = Path(__file__).resolve().parents[2]
except Exception:
    # Fallback to the original behaviour if anything goes wrong.
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Application lifespan management


async def _prime_colonisation_database_if_empty(
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

    # Reuse the same ingestion pipeline as the live FileWatcher and the
    # /api/debug/reload-journals endpoint so behaviour is consistent.
    from .services.file_watcher import (
        JournalFileHandler,
    )  # local import to avoid cycles
    import asyncio

    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    journal_files = sorted(
        journal_dir.glob("Journal.*.log"),
        key=lambda p: p.stat().st_mtime,
    )
    if not journal_files:
        logger.info(
            "Initial journal preload skipped: no Journal.*.log files found in %s",
            journal_dir,
        )
        return

    processed_files = 0
    for journal_file in journal_files:
        try:
            await handler._process_file(journal_file)
            processed_files += 1
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error preloading journal file %s during initial import: %s",
                journal_file,
                exc,
            )

    logger.info(
        "Initial journal preload completed: processed %s journal file(s) from %s",
        processed_files,
        journal_dir,
    )


async def _sync_latest_journals_best_effort(
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

        journal_files = sorted(
            journal_dir.glob("Journal.*.log"),
            key=lambda p: p.stat().st_mtime,
        )
        if not journal_files:
            return

        # Process only the tail of history to keep startup cost bounded.
        tail_count = 3
        tail = journal_files[-tail_count:]

        from .services.file_watcher import JournalFileHandler  # local import

        handler = JournalFileHandler(
            parser=parser,
            system_tracker=system_tracker,
            repository=repository,
            update_callback=notify_system_update,
            loop=loop,
        )

        for jf in tail:
            await handler._process_file(jf)

        try:
            from .api.websocket import notify_global_refresh

            await notify_global_refresh()
        except Exception:
            # No-op if websocket layer isn't ready.
            pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("Best-effort latest journal sync failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Responsible for:
    - constructing core services and repositories
    - wiring FastAPI route and WebSocket dependencies
    - performing a one-time initial journal import when the DB is empty
    - starting and stopping the journal file watcher
    """
    logger.info("Starting Elite: Dangerous Colonisation Assistant")

    config = get_config()

    # Capture the *running* asyncio loop for the FastAPI lifespan.
    #
    # The journal file watcher uses watchdog (threads) and schedules async work
    # back onto this loop. If we capture the wrong loop (or a non-running loop),
    # live updates can silently stop.
    loop = asyncio.get_running_loop()

    # Initialize core components
    repository = ColonisationRepository()
    aggregator = DataAggregator(repository)
    system_tracker = SystemTracker()
    parser = JournalParser()
    # FileWatcher accepts an optional `loop` kwarg in production so watchdog
    # threads can schedule work onto the running FastAPI event loop.
    #
    # In unit tests, FileWatcher may be monkeypatched with a dummy class that
    # does not accept newer keyword args, so fall back gracefully.
    try:
        file_watcher = FileWatcher(parser, system_tracker, repository, loop=loop)
    except TypeError:
        file_watcher = FileWatcher(parser, system_tracker, repository)  # type: ignore[call-arg]

    # Expose components via application state for other parts of the app
    app.state.repository = repository
    app.state.aggregator = aggregator
    app.state.system_tracker = system_tracker
    app.state.file_watcher = file_watcher

    # Set dependencies for API routes and WebSocket layer
    set_dependencies(repository, aggregator, system_tracker)
    set_aggregator(aggregator)

    # Perform a one-time initial import of existing journals when the
    # colonisation database is empty. This ensures that on a fresh
    # installation (or after the DB has been deleted) we immediately
    # populate sites and commodities without requiring the user to call
    # /api/debug/reload-journals manually.
    await _prime_colonisation_database_if_empty(repository, parser, system_tracker)

    # In the packaged runtime, also do a *bounded* best-effort sync of the most
    # recent journal files even when the DB is not empty. This mitigates stale
    # persistent DB state after reinstall/upgrade.
    try:
        if is_frozen():
            journal_dir_for_sync = Path(config.journal.directory)
            asyncio.create_task(
                _sync_latest_journals_best_effort(
                    parser,
                    system_tracker,
                    repository,
                    journal_dir_for_sync,
                    loop,
                ),
                name="edca-startup-journal-sync",
            )
    except Exception:
        # Non-fatal.
        pass

    # Set update callback for file watcher
    file_watcher.set_update_callback(notify_system_update)

    # Start watching journal directory for incremental updates
    journal_dir = Path(config.journal.directory)
    try:
        await file_watcher.start_watching(journal_dir)
        logger.info("File watcher started successfully")
    except FileNotFoundError as e:
        # Expected "directory missing" case – log clearly but do not block startup.
        logger.error("Failed to start file watcher: %s", e)
        logger.warning("Application will start but journal monitoring is disabled")
    except Exception as e:  # noqa: BLE001
        # On some environments (or Python/runtime combinations), watchdog or the
        # underlying OS file notification APIs can raise unexpected exceptions
        # (for example, permission or low-level OS errors). In the packaged
        # runtime, an unhandled exception here would cause the entire FastAPI
        # app startup to fail, which in turn makes the embedded uvicorn server
        # exit immediately and the browser cannot reach /api/health or /app/.
        #
        # To keep the application usable even when journal monitoring cannot be
        # initialised, we treat any unexpected error as non-fatal: log it with
        # full details and continue starting the API without an active watcher.
        logger.exception("Unexpected error while starting file watcher: %s", e)
        logger.warning(
            "Application will start but journal monitoring is disabled due to the error above"
        )

    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down Elite: Dangerous Colonisation Assistant")
        file_watcher_from_state: FileWatcher | None = getattr(
            app.state, "file_watcher", None
        )
        if file_watcher_from_state is not None:
            await file_watcher_from_state.stop_watching()


# Create FastAPI application
app = FastAPI(
    title="Elite: Dangerous Colonisation Assistant",
    description="Real-time tracking for Elite: Dangerous colonisation efforts",
    version=__version__,
    lifespan=lifespan,
)

# Configure CORS
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the built frontend (React/Vite) as static files if available.
# The expected layout is:
#   <project_root>/frontend/dist/...
frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    logger.info("Mounting frontend static files from %s", frontend_dist)
    app.mount(
        "/app",
        StaticFiles(directory=frontend_dist, html=True),
        name="frontend",
    )
else:
    logger.warning(
        "Frontend dist directory not found at %s; /app will not serve the web UI.",
        frontend_dist,
    )

# Include routers
app.include_router(colonisation_router)
app.include_router(settings_router)
app.include_router(journal_router)
app.include_router(carriers_router)

# WebSocket endpoint
app.add_api_websocket_route("/ws/colonisation", websocket_endpoint)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Elite: Dangerous Colonisation Assistant",
        "version": __version__,
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
        log_level=config.logging.level.lower(),
    )
