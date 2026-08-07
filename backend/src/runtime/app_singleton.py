"""Application instance locking for single-instance runtime.

This module implements a lightweight, cross-platform, per-user lock that
prevents multiple instances of the Elite: Dangerous Colonisation Assistant
from running concurrently for the same OS user.

The lock is based on an OS-level file lock:

- On Windows it uses msvcrt.locking on a per-user lock file under
  %LOCALAPPDATA%\\EDColonisationAsst.
- On POSIX systems it uses fcntl.flock on a file under either
  $XDG_RUNTIME_DIR, $XDG_CACHE_HOME or ~/.cache/EDColonisationAsst.

Operating system file locks are automatically released when the owning
process exits, so stale locks are not an issue under normal crashes or
reboots.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import IO, ClassVar, Self


class ApplicationInstanceLockError(Exception):
    """Raised when the application instance lock cannot be created or used."""


@dataclass
class ApplicationInstanceLock:
    """Per-user process-wide lock for the EDCA runtime.

    The typical usage pattern is:

    .. code-block:: python

        lock = ApplicationInstanceLock()
        if not lock.acquire():
            # Another instance is already running; exit early.
            sys.exit(0)

        try:
            run_application()
        finally:
            lock.release()
    """

    app_id: str = "edca"

    _file_handle: IO[str] | None = None
    _lock_path: Path | None = None

    # Tracks lock paths held within the current process to avoid re-entrantly
    # acquiring the same OS-level lock multiple times in one interpreter. This
    # supplements the OS-level file lock, which is primarily responsible for
    # cross-process exclusivity.
    _held_paths: ClassVar[set[Path]] = set()

    def acquire(self) -> bool:
        """Attempt to acquire the instance lock.

        Returns:
            True if this process successfully obtained the lock,
            False if another instance already holds it.

        Raises:
            ApplicationInstanceLockError: if the lock directory cannot be
            created or the lock file cannot be opened.
        """
        if self._file_handle is not None:
            # Lock already held by this instance.
            return True

        lock_path = self._resolve_lock_path()
        self._lock_path = lock_path

        # If this path is already marked as held inside the current process,
        # treat the lock as unavailable to additional ApplicationInstanceLock
        # instances, even though the underlying OS may permit re-entrant
        # locks within a single process.
        if lock_path in self.__class__._held_paths:
            return False

        try:
            fh = lock_path.open("a+")
        except OSError as exc:
            raise ApplicationInstanceLockError(
                f"Unable to open application lock file at {lock_path}: {exc}"
            ) from exc

        try:
            if os.name == "nt":
                acquired = self._acquire_windows_lock(fh)
            else:
                acquired = self._acquire_posix_lock(fh)
        except Exception:
            try:
                fh.close()
            except OSError:
                # Ignore secondary close errors.
                pass
            self._file_handle = None
            raise

        if not acquired:
            # Another instance holds the lock; we must close the handle and
            # not retain any reference to the file.
            try:
                fh.close()
            except OSError:
                pass
            self._file_handle = None
            return False

        # We now hold the lock; store the handle and write our PID for
        # debugging purposes. Errors while writing are non-fatal.
        self._file_handle = fh
        # Mark the path as held in this process.
        self.__class__._held_paths.add(lock_path)
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(str(os.getpid()))
            fh.flush()
        except OSError:
            # Do not treat failure to write the PID as fatal.
            pass

        return True

    def release(self) -> None:
        """Release the instance lock if held."""
        fh = self._file_handle
        if fh is None:
            return

        lock_path = self._lock_path

        try:
            if os.name == "nt":
                self._release_windows_lock(fh)
            else:
                self._release_posix_lock(fh)
        finally:
            try:
                fh.close()
            except OSError:
                pass
            self._file_handle = None
            if lock_path is not None:
                self.__class__._held_paths.discard(lock_path)
            self._lock_path = None

    # ------------------------------------------------------------------ context manager

    def __enter__(self) -> Self:
        acquired = self.acquire()
        if not acquired:
            raise ApplicationInstanceLockError(
                "Another instance of EDCA is already running for this user."
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Release the lock when leaving a context manager scope."""
        self.release()

    # ------------------------------------------------------------------ internals

    def _resolve_lock_path(self) -> Path:
        """Compute the per-user lock file path for this application."""
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA")
            if base:
                root = Path(base) / "EDColonisationAsst"
            else:
                # Pragmatic fallback if LOCALAPPDATA is missing.
                root = Path.home() / "AppData" / "Local" / "EDColonisationAsst"
        else:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            if runtime_dir:
                root = Path(runtime_dir) / "edca"
            else:
                cache_home = os.environ.get("XDG_CACHE_HOME")
                if cache_home:
                    root = Path(cache_home) / "EDColonisationAsst"
                else:
                    root = Path.home() / ".cache" / "EDColonisationAsst"

        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ApplicationInstanceLockError(
                f"Unable to create lock directory at {root}: {exc}"
            ) from exc

        return root / f"{self.app_id}.lock"

    @staticmethod
    def _acquire_windows_lock(fh: IO[str]) -> bool:
        """Attempt to acquire an exclusive lock on Windows."""
        import msvcrt  # type: ignore[import-not-found]

        try:
            # Lock the first byte of the file; the specific region is arbitrary
            # as long as all instances use the same region.
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            # Another process is holding the lock.
            return False

    @staticmethod
    def _release_windows_lock(fh: IO[str]) -> None:
        """Release the exclusive lock on Windows if held."""
        import msvcrt  # type: ignore[import-not-found]

        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            # Best-effort unlock; ignore errors.
            return

    @staticmethod
    def _acquire_posix_lock(fh: IO[str]) -> bool:
        """Attempt to acquire an exclusive lock on POSIX systems."""
        import fcntl  # type: ignore[import-not-found]

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            # Another process is holding the lock.
            return False

    @staticmethod
    def _release_posix_lock(fh: IO[str]) -> None:
        """Release the exclusive lock on POSIX systems if held."""
        import fcntl  # type: ignore[import-not-found]

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            # Best-effort unlock; ignore errors.
            return
