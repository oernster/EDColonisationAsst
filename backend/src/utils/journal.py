"""Utility functions for handling Elite: Dangerous journal files."""

from __future__ import annotations

from collections.abc import Iterable
import os
from pathlib import Path

# Elite journals live under ".../Saved Games/Frontier Developments/Elite Dangerous"
_JOURNAL_SUBPATH = Path("Saved Games") / "Frontier Developments" / "Elite Dangerous"

# Steam App ID for Elite Dangerous (used by Proton compatdata path)
_STEAM_APP_ID_ELITE_DANGEROUS = "359320"


def _get_home_dir() -> Path:
    """
    Resolve a home directory for candidate generation.

    Notes:
    - In production, we fall back to Path.home().
    - In unit tests we sometimes monkeypatch the module-level `os` with a minimal
      stub that only provides `name` and `environ`. In that case, falling back
      to Path.home() would probe the real machine and make tests nondeterministic.
    """
    try:
        home_env = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    except Exception:  # noqa: BLE001
        # Deliberately broad. On the real stdlib os this cannot fail; the
        # the docstring above explains that the tests substitute a fake os
        # module to keep this deterministic; a substitute is free to
        # raise anything from .environ. Treating that as 'no home set'
        # keeps the fallback below in charge.
        home_env = None
    if home_env:
        return Path(home_env)

    # Only use Path.home() when `os` is the real stdlib module.
    if getattr(os, "__name__", "") == "os":
        return Path.home()

    # Deterministic fallback for tests/stubs.
    return Path("/nonexistent")


def _iter_linux_journal_candidates() -> Iterable[Path]:
    """
    Yield likely Elite journal directories on Linux.

    Supports:
      - Steam Proton (compatdata) via STEAM_COMPAT_DATA_PATH or common Steam roots
      - Wine / Lutris via WINEPREFIX or ~/.wine
    """
    home = _get_home_dir()
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"

    # Proton: explicit compat prefix if caller provided it.
    compat = os.environ.get("STEAM_COMPAT_DATA_PATH")
    if compat:
        compat_path = Path(compat)
        yield (
            compat_path / "pfx" / "drive_c" / "users" / "steamuser" / _JOURNAL_SUBPATH
        )
        yield (compat_path / "pfx" / "drive_c" / "users" / user / _JOURNAL_SUBPATH)

    # Proton: common Steam install roots.
    steam_roots = [
        home / ".steam" / "steam",
        home / ".steam" / "root",
        home / ".local" / "share" / "Steam",
        # Steam Flatpak
        home
        / ".var"
        / "app"
        / "com.valvesoftware.Steam"
        / ".local"
        / "share"
        / "Steam",
    ]

    for root in steam_roots:
        yield (
            root
            / "steamapps"
            / "compatdata"
            / _STEAM_APP_ID_ELITE_DANGEROUS
            / "pfx"
            / "drive_c"
            / "users"
            / "steamuser"
            / _JOURNAL_SUBPATH
        )
        yield (
            root
            / "steamapps"
            / "compatdata"
            / _STEAM_APP_ID_ELITE_DANGEROUS
            / "pfx"
            / "drive_c"
            / "users"
            / user
            / _JOURNAL_SUBPATH
        )

    # Wine: explicit prefix if provided.
    wineprefix = os.environ.get("WINEPREFIX")
    prefixes: list[Path] = []
    if wineprefix:
        prefixes.append(Path(wineprefix))

    # Wine: default prefix.
    prefixes.append(home / ".wine")

    for prefix in prefixes:
        yield prefix / "drive_c" / "users" / user / _JOURNAL_SUBPATH
        yield prefix / "drive_c" / "users" / "steamuser" / _JOURNAL_SUBPATH


def find_journal_directory() -> Path | None:
    """Best-effort auto-detection of the journal directory for the current OS."""
    if os.name == "nt":
        # Import only on Windows to avoid accidental platform-specific import issues.
        from .windows import get_saved_games_path  # noqa: WPS433 (late import)

        saved_games_path = get_saved_games_path()
        if not saved_games_path:
            return None

        journal_path = saved_games_path / "Frontier Developments" / "Elite Dangerous"
        return journal_path if journal_path.is_dir() else None

    for candidate in _iter_linux_journal_candidates():
        if candidate.is_dir():
            return candidate

    return None


def get_journal_directory() -> Path:
    """
    Return the journal directory every view reads: the configured one.

    The configuration's own default is the detected folder (see
    config._default_journal_directory), so a normal installation still needs
    no setup; a folder saved on the Settings page replaces it. This used to
    re-detect from Saved Games on every call, so the commander header and
    the carrier views read a different folder from the colonisation watcher
    whenever the user had set one.

    A configured folder that does not exist is reported rather than swapped
    for the detected one: two folders answering different views is the defect
    this function exists to prevent.

    Raises:
        FileNotFoundError: if the configured directory does not exist.
    """
    # Late for the reason config.py gives: utils/__init__ imports the logger,
    # the logger imports config, so a top-level import here is circular.
    from ..config import get_config

    journal_dir = Path(get_config().journal.directory)
    if journal_dir.is_dir():
        return journal_dir
    raise FileNotFoundError(f"The journal directory does not exist: {journal_dir}")


def get_latest_journal_file(journal_dir: Path) -> Path | None:
    """Get the latest journal file from the given directory."""
    files = get_journal_files(journal_dir)
    return files[-1] if files else None


def get_journal_files(journal_dir: Path) -> list[Path]:
    """Return all Journal.*.log files sorted oldest → newest by mtime.

    Fleet carrier related events (CarrierStats/CarrierLocation/CarrierTradeOrder)
    are not always present in the *latest* journal file. Callers that need the
    most recent carrier data should scan multiple recent files rather than only
    parsing the latest file.
    """
    files = list(journal_dir.glob("Journal.*.log"))
    if not files:
        return []
    return sorted(files, key=lambda p: p.stat().st_mtime)
