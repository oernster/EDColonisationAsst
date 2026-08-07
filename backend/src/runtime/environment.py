"""
Runtime environment description for the packaged and development runtimes.

This module encapsulates the detection of:

- Runtime mode (DEV vs FROZEN) via [`RuntimeMode`](backend/src/utils/runtime.py:1)
  and [`get_runtime_mode()`](backend/src/utils/runtime.py:1).
- A sensible project root directory depending on mode.
- Icon and frontend URL paths used by the runtime tray UI and application shell.

Keeping this logic in a small, focused module helps ensure that
[`runtime_entry`](backend/src/runtime_entry.py:1) remains a thin entrypoint
while the bulk of the environment logic is shared with
[`runtime.app_runtime`](backend/src/runtime/app_runtime.py:1) and its helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from .common import RuntimeMode, get_runtime_mode


@dataclass(frozen=True)
class RuntimeEnvironment:
    """
    Represents the runtime environment for the application.

    This encapsulates derived paths and constants that are shared by the
    backend server controller and the tray UI.
    """

    mode: RuntimeMode
    project_root: Path
    backend_port: int = 8000

    @property
    def frontend_url(self) -> str:
        """Return the URL of the web UI served by the backend."""
        return f"http://127.0.0.1:{self.backend_port}/app/"

    @property
    def icon_path(self) -> Path:
        """
        Best-effort resolution of the EDCA icon on disk.

        In a frozen onefile build we prefer the install directory that contains
        EDColonisationAsst.exe (so that the tray and any Qt surfaces use the
        same icon as the runtime EXE). In dev mode we fall back to the
        project_root next to backend/, which matches the existing layout.
        """
        candidates: list[Path] = []

        # 1) Directory of the running executable (frozen) or script (dev).
        try:
            exe_dir = Path(sys.argv[0]).resolve().parent
            candidates.append(exe_dir / "EDColonisationAsst.ico")
        except (OSError, TypeError, ValueError):
            # resolve() touching the filesystem (OSError) and an unusable
            # sys.argv[0] (TypeError, ValueError). Skipping this candidate
            # leaves the project-root one below, which is the dev path.
            pass

        # 2) Project root as detected by RuntimeEnvironment.detect().
        candidates.append(self.project_root / "EDColonisationAsst.ico")

        for path in candidates:
            if path.exists():
                return path

        # 3) Fallback: return the executable path itself so Qt can still
        # extract an icon resource from the EXE if available.
        try:
            return Path(sys.argv[0]).resolve()
        except (OSError, TypeError, ValueError):
            # resolve() touching the filesystem (OSError) and an unusable
            # sys.argv[0] (TypeError, ValueError) are the demonstrated failures.
            return self.project_root

    @classmethod
    def detect(cls) -> RuntimeEnvironment:
        """
        Detect the current runtime environment, including a sensible project root.

        - In DEV mode we keep using the source layout
          (backend/src/runtime_entry.py -> src -> backend -> project_root).
        - In FROZEN mode we treat the directory containing the runtime EXE as
          the project root, which is also where the installer places the icon
          and other payload files.
        """
        mode = get_runtime_mode()

        if mode is RuntimeMode.FROZEN:
            try:
                project_root = Path(sys.argv[0]).resolve().parent
            except (OSError, TypeError, ValueError):
                # As above. The source layout is the right fallback: it is
                # what the non-frozen branch below uses unconditionally.
                project_root = Path(__file__).resolve().parents[2]
        else:
            project_root = Path(__file__).resolve().parents[2]

        return cls(mode=mode, project_root=project_root)
