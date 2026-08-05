"""Putting the payload on disk, and taking it off again, file by file.

The payload is a directory tree rather than an archive, so deployment is a walk
and a copy. It is done file by file rather than with a single ``copytree`` for
two reasons: it lets the operation report real per-file progress, which is what
makes a several-thousand-file install legible; and it lets every destination be
checked before it is written.

There is no archive here, so this is not the zip-slip case. The guard is still
enforced rather than assumed, because a link inside the staged tree, or an
install directory that is itself a link, would otherwise let a write land
outside the directory the user agreed to. Link detection is injected rather
than called directly, so the skip is exercised on a platform where creating a
link needs a privilege the test suite does not have. British spelling is used
in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from installer.constants import (
    IGNORED_DIR_NAMES,
    PY_SUFFIX,
    STAGED_PY_SUFFIX,
)
from installer.ops.errors import UnsafePayloadEntryError
from installer.ops.progress import (
    COPY_END_PCT,
    COPY_MESSAGE,
    COPY_START_PCT,
    DELETE_END_PCT,
    DELETE_MESSAGE,
    DELETE_START_PCT,
    ProgressCallback,
    report,
    scaled,
)

_IGNORED = frozenset(IGNORED_DIR_NAMES)

# Answers whether a path is a link, so a copy can skip one without following it.
LinkCheck = Callable[[Path], bool]


def is_link(path: Path) -> bool:
    """Return True when a path is a symbolic link or a junction."""
    return path.is_symlink()


def deployed_name(name: str) -> str:
    """Return the name a staged file is installed under.

    buildinstaller.py ships the backend sources as ``*.py_`` because Nuitka
    strips ``*.py`` out of an included data directory. The real extension is
    restored here, which is the other half of that arrangement.
    """
    if name.endswith(STAGED_PY_SUFFIX):
        return name[: -len(STAGED_PY_SUFFIX)] + PY_SUFFIX
    return name


def _wanted(names: list[str]) -> list[str]:
    """Return the directory names worth descending into."""
    return [name for name in names if name not in _IGNORED]


def count_files(root: Path) -> int:
    """Return how many files a copy of ``root`` would write.

    The same pruning the copy applies is applied here, so the total the
    progress bar is scaled against is the total that actually gets written.
    """
    total = 0
    for _dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = _wanted(dirnames)
        total += len(filenames)
    return total


def safe_destination(root: Path, destination: Path) -> Path:
    """Return a resolved destination, refusing one that escapes ``root``.

    Resolution is what makes this real: a relative path cannot escape a walked
    tree, but a link in the staged payload or an install directory that is
    itself a link can, and both resolve to somewhere outside.
    """
    resolved = destination.resolve()
    anchor = root.resolve()
    if resolved != anchor and anchor not in resolved.parents:
        raise UnsafePayloadEntryError(
            f"Payload entry {destination.name!r} would be written outside {anchor}."
        )
    return resolved


def copy_tree(
    source: Path,
    target: Path,
    *,
    progress: ProgressCallback | None = None,
    total: int | None = None,
    link_check: LinkCheck = is_link,
) -> int:
    """Copy ``source`` into ``target``, overwriting, and return the file count.

    Links are skipped rather than followed. The payload is a staged tree that
    never contains one, so skipping costs nothing and removes the one way a
    walk can leave the directory it started in.
    """
    expected = total if total is not None else count_files(source)
    copied = 0
    report(progress, COPY_START_PCT, COPY_MESSAGE)
    target.mkdir(parents=True, exist_ok=True)

    for dirpath, dirnames, filenames in os.walk(source):
        base = Path(dirpath)
        dirnames[:] = [
            name for name in _wanted(dirnames) if not link_check(base / name)
        ]
        target_root = safe_destination(target, target / base.relative_to(source))
        target_root.mkdir(parents=True, exist_ok=True)

        for name in filenames:
            entry = base / name
            if link_check(entry):
                continue
            destination = safe_destination(target, target_root / deployed_name(name))
            shutil.copy2(entry, destination)
            copied += 1
            report(
                progress,
                scaled(copied, expected, COPY_START_PCT, COPY_END_PCT),
                COPY_MESSAGE,
            )
    report(progress, COPY_END_PCT, COPY_MESSAGE)
    return copied


def _remove_files(
    base: Path,
    names: list[str],
    removed: int,
    expected: int,
    progress: ProgressCallback | None,
) -> int:
    """Delete one directory's files, reporting each, and return the new count."""
    for name in names:
        try:
            (base / name).unlink()
        except OSError:
            pass
        removed += 1
        report(
            progress,
            scaled(removed, expected, DELETE_START_PCT, DELETE_END_PCT),
            DELETE_MESSAGE,
        )
    return removed


def delete_tree(
    root: Path,
    *,
    progress: ProgressCallback | None = None,
    total: int | None = None,
) -> None:
    """Remove a directory tree file by file, reporting progress as it goes.

    A single ``rmtree`` gives the user a frozen window for the whole removal.
    Walking it bottom up reports real progress instead. Anything that cannot be
    removed is left for the caller: an uninstaller running from inside the tree
    hands the remains to a detached helper rather than failing here.
    """
    if not root.exists():
        return
    expected = total if total is not None else count_files(root)
    removed = 0
    report(progress, DELETE_START_PCT, DELETE_MESSAGE)

    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        base = Path(dirpath)
        removed = _remove_files(base, filenames, removed, expected, progress)
        for name in dirnames:
            try:
                (base / name).rmdir()
            except OSError:
                continue
    try:
        root.rmdir()
    except OSError:
        return
