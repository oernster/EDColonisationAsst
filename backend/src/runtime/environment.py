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

try:
    from ..utils.ports import (  # type: ignore[import-not-found]
        choose_port,
        read_recorded_port,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script,
    # which the frozen Nuitka build does. That is an ImportError; anything else
    # raised while importing is a real defect and should surface.
    from backend.src.utils.ports import (  # type: ignore[import-error]
        choose_port,
        read_recorded_port,
    )

# The port asked for before anything is known about the machine. It is a
# preference and never a guarantee: see utils.ports for why a fixed port cannot
# be relied on, then resolve_backend_port() below for what happens when it
# cannot be had.
DEFAULT_BACKEND_PORT = 8000

# Written by whichever instance is serving, read by the next run and by a
# second instance looking for the web UI of the one already running.
RECORDED_PORT_FILENAME = "runtime-port"

_LOOPBACK_HOST = "127.0.0.1"


def _configured_server(attribute: str, fallback: str | int) -> str | int:
    """Return one server setting from configuration; the fallback if unreadable.

    Read defensively and late: the value comes from hand-editable YAML, so a
    bad one arrives as a validation error rather than as one predictable type.
    A setting that cannot be read is not worth failing a startup over.
    """
    try:
        try:
            from ..config import get_config  # type: ignore[import-not-found]
        except ImportError:
            from backend.src.config import get_config  # type: ignore[import-error]

        config = get_config()
        server = getattr(config, "server", config)
        return getattr(server, attribute, fallback) or fallback
    except Exception:  # noqa: BLE001
        # Deliberately broad, for the reason in the docstring.
        return fallback


def configured_backend_port() -> int:
    """Return the port the configuration asks for; the default if unset."""
    return int(_configured_server("port", DEFAULT_BACKEND_PORT))


def configured_backend_host() -> str:
    """Return the host the server will bind; the loopback default if unset.

    The port is probed against this same host so that what the probe sees is
    what the server's own bind will see: a port free on the loopback can still
    be taken on the wildcard address.
    """
    return str(_configured_server("host", _LOOPBACK_HOST))


def resolve_backend_port(recorded_file: Path) -> int:
    """Return a port the backend can actually bind.

    The configured port is a preference. Windows reserves whole ranges, so it
    may be unbindable while appearing unused, in which case the operating
    system is asked for one instead. If even that fails there is nothing
    sensible left to try, so the configured port is returned and the backend
    controller reports the real reason it cannot start.
    """
    preferred = configured_backend_port()
    chosen = choose_port(
        configured_backend_host(),
        preferred,
        recorded=read_recorded_port(recorded_file),
    )
    return chosen if chosen is not None else preferred


@dataclass(frozen=True)
class RuntimeEnvironment:
    """
    Represents the runtime environment for the application.

    This encapsulates derived paths and constants that are shared by the
    backend server controller and the tray UI.
    """

    mode: RuntimeMode
    project_root: Path
    backend_port: int = DEFAULT_BACKEND_PORT

    @property
    def frontend_url(self) -> str:
        """Return the URL of the web UI served by the backend."""
        return f"http://127.0.0.1:{self.backend_port}/app/"

    @property
    def recorded_port_file(self) -> Path:
        """Where the port actually being served is recorded.

        Beside the runtime log in the install directory, so a second instance
        and the next run can both find it without reading configuration.
        """
        return self.project_root / RECORDED_PORT_FILENAME

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

        port = resolve_backend_port(project_root / RECORDED_PORT_FILENAME)
        return cls(mode=mode, project_root=project_root, backend_port=port)
