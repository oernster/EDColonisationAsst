"""
Runtime entrypoint for the Elite: Dangerous Colonisation Assistant.

This module is designed to be used as the main entry when building a
self-contained runtime executable with Nuitka. It now acts as a *thin*
entrypoint that focuses on:

- Single-instance enforcement via ApplicationInstanceLock.
- Crash logging for the packaged runtime.
- Delegation of all runtime orchestration to RuntimeApplication in
  [`runtime.app_runtime`](backend/src/runtime/app_runtime.py:1).

Two runtime modes are supported (as determined by utils.runtime.get_runtime_mode()):

- Development mode (DEV):
  Launched via the regular Python interpreter. Behaviour is delegated to
  the existing launcher window and virtual-environment logic so that the
  developer experience remains unchanged.

- Frozen mode (FROZEN):
  Launched via a Nuitka-built EXE that embeds Python and all backend
  dependencies. In this mode we:
    * Start the FastAPI backend (uvicorn) in-process.
    * Provide a simple Qt tray UI with an "Open Web UI" and "Exit" action.
    * Do NOT rely on any system-wide Python installation.

The actual EXE build step will continue to target this module, e.g.:

    python -m nuitka --onefile --enable-plugin=pyside6 backend/src/runtime_entry.py
"""

from __future__ import annotations

from pathlib import Path
import sys
import webbrowser


def _bootstrap_debug_log(message: str) -> None:
    """Minimal logger used when runtime.common cannot be imported.

    Writes to EDColonisationAsst-runtime.log next to the EXE (or CWD) and
    must never raise.
    """
    try:
        try:
            exe_dir = Path(sys.argv[0]).resolve().parent
        except (OSError, TypeError, ValueError):
            # resolve() touching the filesystem (OSError) and an unusable sys.argv[0]
            # (TypeError, ValueError) are the demonstrated failures. The current
            # directory is a fine second choice for a log file.
            exe_dir = Path.cwd()
        log_path = exe_dir / "EDColonisationAsst-runtime.log"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:  # noqa: BLE001, S110
        # Never let debug logging break the runtime.
        pass


# Attempt to import the shared runtime debug logger. This is deliberately
# defensive so that the frozen EXE can still log even if package layout
# differs from the source tree.
try:
    # When imported as src.runtime_entry or backend.src.runtime_entry
    from .runtime.common import _debug_log  # type: ignore[import-not-found]
except ImportError as exc1:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    try:
        # Fallback for environments where Nuitka packages modules differently.
        from backend.src.runtime.common import _debug_log  # type: ignore[import-error]
    except Exception as exc2:  # noqa: BLE001
        # As a last resort, fall back to a local bootstrap logger so that we
        # still get EDColonisationAsst-runtime.log even if runtime.common
        # cannot be imported at all.
        _bootstrap_debug_log(
            f"[runtime_entry] FATAL importing runtime.common: {exc1!r}; "
            f"fallback backend.src.runtime.common also failed: {exc2!r}"
        )

        def _debug_log(message: str) -> None:
            _bootstrap_debug_log(message)


# Single-instance lock for the packaged runtime. We mirror the defensive import
# strategy used elsewhere so that execution as a top-level script or as a
# package both work.
try:
    from .runtime.app_singleton import (  # type: ignore[import-not-found]
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.app_singleton import (  # type: ignore[import-error]
        ApplicationInstanceLock,
        ApplicationInstanceLockError,
    )

# The environment supplies the running instance's web UI address, so the
# already-running branch below opens the port actually in use rather than a
# hardcoded one that a configured port would silently invalidate.
try:
    from .runtime.environment import (  # type: ignore[import-not-found]
        RuntimeEnvironment,
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.environment import (  # type: ignore[import-error]
        RuntimeEnvironment,
    )

# Import the core runtime application orchestrator. This lives in
# backend.src.runtime.app_runtime so that this module can remain small and
# focused on process-level concerns.
try:
    from .runtime.app_runtime import (
        RuntimeApplication,  # type: ignore[import-not-found]
    )
except ImportError:
    # The relative form fails only when this module runs as a top-level script, which
    # the frozen Nuitka build does. That is an ImportError; anything else raised while
    # importing is a real defect and should surface.
    from backend.src.runtime.app_runtime import (
        RuntimeApplication,  # type: ignore[import-error]
    )


# --------------------------------------------------------------------------- entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    """
    Entry point for the packaged runtime executable.

    In FROZEN mode this is invoked by the Nuitka-built EDColonisationAsst.exe.
    To make failures in the frozen runtime debuggable on end-user machines,
    we capture any unhandled exceptions and write them to a plain text log file
    next to the executable.
    """
    _debug_log("[runtime_entry] main() starting")

    # When EDColonisationAsst.exe is started automatically (e.g. via Windows
    # "Run" key on login), we typically want the tray + backend to come up
    # silently without opening a browser window.
    #
    # The GUI installer can register the runtime with "--no-browser".
    no_browser = "--no-browser" in sys.argv or "--background" in sys.argv

    try:
        # Enforce a single running instance per user. If another instance is
        # already holding the lock, we do not start a second backend/tray
        # process; instead we best-effort open the existing web UI and exit.
        try:
            lock = ApplicationInstanceLock()
            if not lock.acquire():
                _debug_log(
                    "[runtime_entry] Another EDCA instance already running; "
                    "opening existing web UI and exiting.",
                )
                if not no_browser:
                    try:
                        # detect() resolves the port the RUNNING instance is
                        # serving on, because it prefers the recorded port when
                        # something is already bound there. The port is not
                        # fixed: Windows can reserve the configured one, so a
                        # hardcoded URL here would send the user nowhere.
                        webbrowser.open(RuntimeEnvironment.detect().frontend_url)
                    except Exception:  # noqa: BLE001, S110
                        # Browser launch failures must not crash the runtime.
                        pass
                return 0
        except ApplicationInstanceLockError as lock_exc:
            _debug_log(
                "[runtime_entry] Failed to create application lock; "
                f"continuing without single-instance enforcement: {lock_exc!r}",
            )

        # RuntimeApplication may be monkeypatched in unit tests with a dummy
        # class that does not accept our newer keyword args.
        try:
            runtime_app = RuntimeApplication(open_browser=not no_browser)
        except TypeError:
            runtime_app = RuntimeApplication()  # type: ignore[call-arg]
        # Accessing the internal _env attribute is acceptable here purely for
        # diagnostic logging; RuntimeApplication owns the public behaviour.
        try:
            mode = getattr(runtime_app, "_env", None)
            mode_repr = getattr(mode, "mode", mode)
        except Exception:  # noqa: BLE001
            # Deliberately broad. This reaches a private attribute purely to label a log
            # line, so any shape change there is expected to be survivable. An unknown
            # mode still logs; it must not stop shutdown.
            mode_repr = "<unknown>"
        _debug_log(
            f"[runtime_entry] RuntimeApplication created; mode={mode_repr}",
        )
        result = runtime_app.run()
        _debug_log(f"[runtime_entry] RuntimeApplication.run() returned {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        # Best-effort crash logging that does not depend on the backend logging
        # configuration or config.yaml being readable.
        import traceback  # type: ignore[import-not-found]

        try:
            exe_dir = Path(sys.argv[0]).resolve().parent
        except (OSError, TypeError, ValueError):
            # resolve() touching the filesystem (OSError) and an unusable sys.argv[0]
            # (TypeError, ValueError) are the demonstrated failures. The current
            # directory is a fine second choice for a log file.
            exe_dir = Path.cwd()

        log_path = exe_dir / "EDColonisationAsst-runtime-error.log"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write("[runtime_entry] FATAL exception in packaged runtime\n")
                f.write(f"Exception: {exc!r}\n")
                f.write("Traceback:\n")
                f.write(traceback.format_exc())
                f.write("\n\n")
        except Exception:  # noqa: BLE001, S110
            # Never let logging failures crash the process again.
            pass

        # Also emit something to stderr in case the process is started from a
        # console in development.
        try:
            print(f"[runtime_entry] FATAL: {exc!r}", file=sys.stderr)
        except Exception:  # noqa: BLE001, S110
            # Deliberately broad. This is the last-resort console report in a windowed
            # build, where sys.stderr may be absent or closed. There is nowhere left to
            # report a failure to report.
            pass

        _debug_log(f"[runtime_entry] FATAL exception: {exc!r}")
        return 1


__all__ = ["RuntimeApplication", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
