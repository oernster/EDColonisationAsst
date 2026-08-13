"""Remembering the one release the commander asked not to hear about again.

Kept beside the colonisation database rather than in `config.yaml`: that file
is tracked, so anything written into it is one machine's state shipped to
everybody. This is per-user state and belongs where the database already is.

Every failure here is silent and costs at most one extra prompt, so nothing in
this module is allowed to raise at the caller.

British spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..utils.logger import get_logger
from ..utils.runtime import is_packaged
from ..utils.user_data import user_data_dir

logger = get_logger(__name__)

_STATE_FILENAME = "update-state.json"
_SKIPPED_KEY = "skipped_version"


def resolve_state_file() -> Path:
    """Return where the skipped version is recorded.

    Mirrors `resolve_db_file`: beside the source packages in development and
    under the user-local directory in a packaged build. The user-local
    directory is what makes a skip survive an upgrade replacing the install
    directory; it is also why this is not kept next to the recorded port.
    """
    if not is_packaged():
        return Path(__file__).parent.parent / _STATE_FILENAME

    return user_data_dir() / _STATE_FILENAME


def _read_state(state_file: Path) -> dict[str, object]:
    """Return the recorded state; an empty one when it cannot be read."""
    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Missing, unreadable or holding something that is not JSON. All
        # three mean the same thing to both callers: nothing is recorded.
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def load_skipped_version(path: Path | None = None) -> str | None:
    """Return the version the commander skipped; None when there is none."""
    value = _read_state(path or resolve_state_file()).get(_SKIPPED_KEY)
    if isinstance(value, str) and value:
        return value
    return None


def save_skipped_version(version: str, path: Path | None = None) -> None:
    """Record the skipped version, preserving anything else in the file.

    Best effort. Failing to write costs one more prompt at the next check and
    nothing else, so it is never reported to the user.
    """
    state_file = path or resolve_state_file()
    state = _read_state(state_file)
    state[_SKIPPED_KEY] = version
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        logger.debug("Could not record the skipped update version.")


__all__ = ["load_skipped_version", "resolve_state_file", "save_skipped_version"]
