"""Main FastAPI application entry point"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.carriers import router as carriers_router
from .api.changes import router as changes_router
from .api.health import router as health_router
from .api.journal import router as journal_router
from .api.routes import router as colonisation_router, set_dependencies
from .api.settings import router as settings_router
from .config import get_config
from .repositories.colonisation_repository import ColonisationRepository
from .services.data_aggregator import DataAggregator
from .services.file_watcher import FileWatcher
from .services.journal_parser import JournalParser
from .services.startup_ingestion import (
    notify_clients_best_effort,
    prime_colonisation_database_if_empty,
    sync_latest_journals_best_effort,
)
from .services.system_tracker import SystemTracker
from .utils.logger import get_logger, setup_logging
from .utils.runtime import is_frozen

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
except (OSError, IndexError, TypeError):
    # The three demonstrated failures: resolve() touching the filesystem
    # (OSError), parents[2] on a shallower path (IndexError) and a
    # non-string sys.argv[0] in an embedded host (TypeError). No file is
    # read here, so decoding errors cannot arise. Fall back to the source
    # layout, which is what this line computed before the frozen case existed.
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Application lifespan management


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
        file_watcher = FileWatcher(  # type: ignore[call-arg]
            parser, system_tracker, repository
        )

    # Expose components via application state for other parts of the app
    app.state.repository = repository
    app.state.aggregator = aggregator
    app.state.system_tracker = system_tracker
    app.state.file_watcher = file_watcher

    # Set dependencies for API routes
    set_dependencies(repository, aggregator, system_tracker)

    journal_dir = Path(config.journal.directory)

    # Determine up front whether this is a first run (empty database) so the
    # heavy initial journal import can be scheduled in the BACKGROUND rather
    # than blocking server readiness.
    #
    # This await runs during ASGI lifespan startup, before uvicorn begins
    # serving requests. Any blocking work here (parsing the full journal
    # history, which can span years and take minutes) would leave the
    # packaged runtime unable to answer /api/health, freezing the startup
    # splash for the entire duration. The single stats query below is cheap.
    try:
        initial_stats = await repository.get_stats()
        db_is_empty = initial_stats.get("total_sites", 0) == 0
    except Exception as exc:  # noqa: BLE001
        # Deliberately broad, same repository boundary as the preload above.
        # Assuming an empty database is the safe wrong answer: it schedules a
        # full backfill, which is slower than a tail sync but never loses data,
        # whereas assuming a populated one would skip a genuine first run.
        logger.warning("Failed to read initial repository stats: %s", exc)
        db_is_empty = True

    async def _startup_ingestion() -> None:
        """Perform the initial journal catch-up off the readiness path.

        - First run (empty DB): backfill the full journal history once so a
          fresh install shows existing sites. This is the only case that
          scans everything; it now runs in the background while the UI
          is already available; the change-bus bump at the end drives the
          long-poll UI to refetch and populate progressively.
        - Repeat run (persisted DB under %LOCALAPPDATA%): only a bounded
          tail sync of the most recent journals. The full history is already
          persisted; live changes are handled by watchdog and polling,
          so re-scanning everything on every launch is unnecessary.
        """
        try:
            if db_is_empty:
                await prime_colonisation_database_if_empty(
                    repository, parser, system_tracker
                )
            else:
                await sync_latest_journals_best_effort(
                    parser, system_tracker, repository, journal_dir, loop
                )
        except Exception:
            # Deliberately broad. This runs as a detached task, so an escaping
            # exception would be reported only as "Task exception was never
            # retrieved" on the event loop, with no traceback in the
            # application log. Catching it here is what makes the failure
            # visible; the server itself stays up either way.
            logger.exception("Background startup journal ingestion failed")
        finally:
            # Signal long-poll clients that data may have changed so the UI
            # refetches once the background ingestion has made progress.
            await notify_clients_best_effort()

    try:
        asyncio.create_task(_startup_ingestion(), name="edca-startup-ingestion")
    except RuntimeError:
        # create_task raises RuntimeError when there is no running loop, which
        # is the only way scheduling can fail here. The application still
        # serves; it just starts with whatever the database already holds.
        logger.exception("Failed to schedule background startup ingestion")

    # Set update callback for file watcher.
    #
    # WebSockets have been removed. The UI now uses AJAX long-polling and
    # refetches via REST when the backend bumps the change sequence.
    async def _update_callback(_system_name: str) -> None:
        await notify_clients_best_effort()

    file_watcher.set_update_callback(_update_callback)

    # Start watching journal directory for incremental updates.
    #
    # process_existing=False: the initial full-history catch-up is owned by
    # the background _startup_ingestion task above, so starting the watcher
    # stays fast and never blocks readiness. Watchdog plus the polling
    # fallback still deliver live updates from here on.
    try:
        try:
            await file_watcher.start_watching(journal_dir, process_existing=False)
        except TypeError:
            # A monkeypatched FileWatcher in tests may not accept the newer
            # keyword argument; fall back to the original signature.
            await file_watcher.start_watching(journal_dir)
        logger.info("File watcher started successfully")
    except FileNotFoundError as e:
        # Expected "directory missing" case: log clearly but do not block startup.
        logger.error("Failed to start file watcher: %s", e)
        logger.warning("Application will start but journal monitoring is disabled")
    except Exception:
        # Deliberately broad, for the reason spelled out below: watchdog sits
        # on OS notification APIs whose failures are platform-specific and
        # open-ended. This is the one handler here where letting an
        # exception through would stop the application coming up at all.
        #
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
        logger.exception("Unexpected error while starting file watcher")
        logger.warning(
            "Application will start but journal monitoring is disabled "
            "due to the error above"
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
app.include_router(health_router)
app.include_router(colonisation_router)
app.include_router(settings_router)
app.include_router(journal_router)
app.include_router(carriers_router)
app.include_router(changes_router)

# WebSocket endpoint removed (replaced by /api/changes/longpoll).


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
