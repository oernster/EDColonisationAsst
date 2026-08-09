"""API routes for application settings"""

from pathlib import Path

from fastapi import APIRouter, Request
import yaml

from ..config import get_config, get_config_paths
from ..models.api_models import AppSettings
from ..services.change_bus import change_bus

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_app_settings():
    """Get application settings"""
    config = get_config()
    return AppSettings(journal_directory=config.journal.directory)


@router.post("", response_model=AppSettings)
async def update_app_settings(
    settings: AppSettings,
    request: Request = None,  # type: ignore[assignment]
):
    """Update application settings.

    The one user-editable setting is the journal directory, stored in
    backend/config.yaml. The dormant Inara configuration is not settable
    here: it lives in backend/commander.yaml (hand-created from the example)
    and environment variables, because no shipped feature reads it.
    """
    # The three file operations below are blocking, which ASYNC230 flags because
    # this is an async endpoint and a blocking read parks the event loop. They
    # are suppressed rather than moved to a thread deliberately: config.yaml is
    # one local file of a few hundred bytes, written only when the user presses
    # Save on the settings page. The cost of an asyncio.to_thread hop per call
    # is larger than the block it removes. Revisit if the file ever grows or
    # moves off local disk.
    # Resolve config paths in a runtime-aware way so that in the packaged
    # executable we always read/write from a per-user writable directory
    # instead of the (potentially read-only) install location.
    config_path, _commander_path = get_config_paths()

    if not config_path.exists():
        # Create a default config if it doesn't exist
        with open(config_path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
            yaml.dump({"journal": {}}, f)

    with open(config_path, "r", encoding="utf-8") as f:  # noqa: ASYNC230
        config_data = yaml.safe_load(f) or {}

    if "journal" not in config_data:
        config_data["journal"] = {}

    config_data["journal"]["directory"] = settings.journal_directory

    with open(config_path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
        yaml.dump(config_data, f, default_flow_style=False)

    # Update in-memory config so the running app sees the changes
    from ..config import _config

    old_journal_dir: str | None = None
    if _config is not None:
        old_journal_dir = _config.journal.directory
        _config.journal.directory = settings.journal_directory

    # Best-effort: restart the live file watcher if the journal directory changed.
    #
    # The watcher is started once during app lifespan startup in
    # [`lifespan()`](backend/src/main.py:149). Without a restart, changing
    # journal_directory in settings would not take effect until the user restarts
    # the whole application.
    try:
        changed = (
            old_journal_dir is None or old_journal_dir != settings.journal_directory
        )

        # When called via FastAPI, `request` is provided. In unit tests this
        # function is called directly, so request may be None.
        file_watcher = None
        if request is not None:
            app_state = getattr(getattr(request, "app", None), "state", None)
            file_watcher = (
                getattr(app_state, "file_watcher", None) if app_state else None
            )

        if changed and file_watcher is not None:
            await file_watcher.stop_watching()
            await file_watcher.start_watching(Path(settings.journal_directory))

        # Prompt connected clients (AJAX long-poll) to refetch their data.
        await change_bus.bump()
    except Exception:  # noqa: BLE001, S110
        # Deliberately broad. The settings are already written to disk by
        # this point; everything in this block is the live watcher catching
        # up with them. Restarting a watchdog observer can fail in
        # platform-specific ways; the next restart picks the new
        # directory up regardless, so never fail the save over it.
        pass

    return settings
