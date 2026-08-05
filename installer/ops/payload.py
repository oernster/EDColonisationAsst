"""The application payload the setup program carries, and finding it.

The payload is a plain directory tree rather than an archive, staged by
buildinstaller.py and embedded as Nuitka data. Nuitka strips loose executables
out of an included data directory, so the runtime executable is embedded a
second time under its own directory and recovered from there when the copied
payload turns out not to carry it.

A payload that cannot be found is fatal. The previous behaviour fell back to
the repository root, which after the move into a subpackage would have resolved
to the installer's own sources and cheerfully installed those. British spelling
is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from installer.constants import (
    BUILD_DIR_NAME,
    EXE_NAME,
    ICON_FILE_NAME,
    LICENSE_FILE_NAME,
    PAYLOAD_DIR_NAME,
    PNG_FILE_NAME,
    RUNTIME_DIR_NAME,
    VERSION_FILE_NAME,
)
from installer.ops.errors import PayloadError
from installer.shared.resource_path import installer_root, launcher_dir, program_root

LICENCE_HEADER = "GNU General Public License v3 (GPL-3.0)\n\n"
LICENCE_FALLBACK = (
    "The licence text was not bundled with this installer.\n\n"
    "Please see: https://www.gnu.org/licenses/lgpl-3.0.html"
)
PAYLOAD_MISSING_MESSAGE = (
    "The application payload could not be found. This installer is incomplete; "
    "download it again rather than installing from it."
)
REFLOW_WIDTH = 75

_INDENTS = ("    ", "\t")
_PARAGRAPH_BREAK = "\n\n"


def _anchors() -> tuple[Path, ...]:
    """Return the directories a bundled resource may be anchored on, in order."""
    roots = [installer_root(), program_root()]
    launcher = launcher_dir()
    if launcher is not None:
        roots.append(launcher)
    return tuple(roots)


def payload_candidates() -> tuple[Path, ...]:
    """Return every place the staged payload may live, in preference order.

    The package anchor comes first: it is the one that holds in both a source
    run and a compiled run. The source-tree staging directory and the directory
    beside the launcher follow, so an installer built before the package move
    still resolves its payload.
    """
    candidates = [anchor / PAYLOAD_DIR_NAME for anchor in _anchors()]
    candidates.append(program_root() / BUILD_DIR_NAME / PAYLOAD_DIR_NAME)
    return tuple(candidates)


def find_payload_root() -> Path | None:
    """Return the staged payload directory, or None when there is not one.

    A directory that exists but holds nothing is not a payload: an empty stage
    would deploy an empty install and report success.
    """
    for candidate in payload_candidates():
        if not candidate.is_dir():
            continue
        try:
            populated = any(candidate.iterdir())
        except OSError:  # pragma: no cover
            # Defensive: is_dir() has already succeeded, so a listing failure
            # needs the directory to vanish between the two calls.
            continue
        if populated:
            return candidate
    return None


def payload_root() -> Path:
    """Return the staged payload directory, or fail loudly when there is none."""
    found = find_payload_root()
    if found is None:
        raise PayloadError(PAYLOAD_MISSING_MESSAGE)
    return found


def runtime_exe_candidates() -> tuple[Path, ...]:
    """Return every place the runtime executable may be found, in order."""
    candidates = [anchor / RUNTIME_DIR_NAME / EXE_NAME for anchor in _anchors()]
    found = find_payload_root()
    if found is not None:
        candidates.append(found / EXE_NAME)
    return tuple(candidates)


def bundled_runtime_exe() -> Path | None:
    """Return the embedded runtime executable, or None when it is absent."""
    for candidate in runtime_exe_candidates():
        if candidate.is_file():
            return candidate
    return None


def _first_readable(candidates: tuple[Path, ...]) -> str | None:
    """Return the text of the first candidate that can be read."""
    for candidate in candidates:
        try:
            return candidate.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _resource_candidates(name: str) -> tuple[Path, ...]:
    """Return the payload and every anchor as places one loose file may sit."""
    found = find_payload_root()
    roots = list(_anchors())
    if found is not None:
        roots.insert(0, found)
    return tuple(root / name for root in roots)


def app_version() -> str:
    """Return the bundled application version, or an empty string if absent."""
    for candidate in _resource_candidates(VERSION_FILE_NAME):
        text = _first_readable((candidate,))
        if text and text.strip():
            return text.strip()
    return ""


def reflow_licence(text: str, width: int = REFLOW_WIDTH) -> str:
    """Rewrap the licence body, leaving indented blocks exactly as they are.

    The raw licence is formatted for an eighty-column console. Rewrapping the
    running paragraphs keeps it readable in a resizable dialog, while an
    indented block keeps its own line breaks because they carry meaning.
    """
    reflowed: list[str] = []
    for paragraph in text.split(_PARAGRAPH_BREAK):
        lines = [line.rstrip() for line in paragraph.splitlines()]
        if not any(lines):
            reflowed.append("")
            continue
        if any(line.startswith(_INDENTS) for line in lines):
            reflowed.append("\n".join(lines))
            continue
        joined = " ".join(line.strip() for line in lines)
        reflowed.append(textwrap.fill(joined, width=width))
    return _PARAGRAPH_BREAK.join(reflowed)


def licence_text() -> str:
    """Return the bundled licence text, or a fallback when it is absent."""
    text = _first_readable(_resource_candidates(LICENSE_FILE_NAME))
    if not text:
        return LICENCE_HEADER + LICENCE_FALLBACK
    return LICENCE_HEADER + reflow_licence(text)


def icon_file() -> Path | None:
    """Return the bundled application .ico, or None when it is absent."""
    for candidate in _resource_candidates(ICON_FILE_NAME):
        if candidate.is_file():
            return candidate
    return None


def png_file() -> Path | None:
    """Return the bundled application PNG, or None when it is absent."""
    for candidate in _resource_candidates(PNG_FILE_NAME):
        if candidate.is_file():
            return candidate
    return None


def installed_icon(install_dir: Path) -> Path | None:
    """Return the .ico inside an install directory, or None when absent."""
    path = install_dir / ICON_FILE_NAME
    return path if path.is_file() else None
