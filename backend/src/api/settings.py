"""API routes for application settings"""

import os
from pathlib import Path

from fastapi import APIRouter, Request
import yaml

from ..config import get_config, get_config_paths
from ..models.api_models import AppSettings
from ..services.change_bus import change_bus
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# A damaged config.yaml is renamed to this; further damage gets a numbered
# copy, so a file kept aside earlier is never overwritten.
_DAMAGED_SUFFIX = ".damaged"
_PARTIAL_SUFFIX = ".partial"


def _keep_aside(path: Path) -> Path:
    """Move a damaged file to the first free kept-aside name; return it."""
    target = path.with_name(path.name + _DAMAGED_SUFFIX)
    copy_number = 0
    while target.exists():
        copy_number += 1
        target = path.with_name(f"{path.name}{_DAMAGED_SUFFIX}.{copy_number}")
    path.replace(target)
    return target


def _load_for_update(path: Path) -> dict:
    """The settings already saved, as a mapping the save can extend.

    Absence is an answer (nothing saved yet), not a fault. A file that cannot
    be READ raises: treating it as empty would save over settings that may be
    perfectly good. A file that reads but is damaged (malformed YAML, another
    encoding, not a mapping, a `journal` that is not one) is kept aside under
    a name the warning reports; the save then starts clean. That used to be a
    500 on every save, so the Settings page could not repair what broke it.
    """
    if not path.exists():
        return {}
    with open(path, "rb") as handle:
        raw = handle.read()
    try:
        data = yaml.safe_load(raw.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError):
        data = None
    if isinstance(data, dict) and isinstance(data.get("journal", {}), dict):
        return data
    kept = _keep_aside(path)
    logger.warning(
        "config.yaml could not be used and was kept aside as %s; "
        "saving the settings to a fresh file",
        kept,
    )
    return {}


def _write_atomically(path: Path, data: dict) -> None:
    """Write the settings so an interruption never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + _PARTIAL_SUFFIX)
    try:
        with open(partial, "w", encoding="utf-8") as handle:
            yaml.dump(data, handle, default_flow_style=False)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


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
    config.yaml (backend/ in a source checkout, the per-user configuration
    folder in a packaged runtime). The dormant Inara configuration is not settable
    here: it lives in backend/commander.yaml (hand-created from the example)
    and environment variables, because no shipped feature reads it.
    """
    # The file operations in the helpers above are blocking, which ASYNC230
    # flags because this is an async endpoint and a blocking read parks the
    # event loop. They
    # are suppressed rather than moved to a thread deliberately: config.yaml is
    # one local file of a few hundred bytes, written only when the user presses
    # Save on the settings page. The cost of an asyncio.to_thread hop per call
    # is larger than the block it removes. Revisit if the file ever grows or
    # moves off local disk.
    # Resolve config paths in a runtime-aware way so that a packaged runtime
    # always reads and writes the per-user configuration directory instead of
    # the install location, which an upgrade overwrites.
    config_path, _commander_path = get_config_paths()

    config_data = _load_for_update(config_path)
    config_data.setdefault("journal", {})["directory"] = settings.journal_directory
    _write_atomically(config_path, config_data)

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
