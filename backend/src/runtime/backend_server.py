"""In-process backend server control for the packaged runtime.

[`BackendServerController`] owns the FastAPI backend for the frozen build: it
starts uvicorn in a background thread inside this process, so a packaged
install needs no external Python interpreter; it also answers the readiness
probes the startup splash polls.

In DEV mode the controller is a no-op. The launcher window starts the backend
in a child process there; the hooks are kept so both modes present the same
interface to [`RuntimeApplication`](backend/src/runtime/app_runtime.py:1).
"""

from __future__ import annotations

import threading
import time

import uvicorn

from .common import RuntimeMode, _debug_log, fastapi_app, logger
from .environment import RuntimeEnvironment

_LOOPBACK_HOST = "127.0.0.1"
_PROBE_TIMEOUT_SECONDS = 1
_READY_POLL_INTERVAL_SECONDS = 1.0
_SHUTDOWN_JOIN_TIMEOUT_SECONDS = 10.0

# The range urllib reports for a reachable endpoint: 2xx and 3xx are both a
# server that answered, which is all readiness asks.
_HTTP_OK = 200
_HTTP_ERROR = 400


class BackendServerController:
    """
    Controls the FastAPI backend server.

    In FROZEN mode we start an in-process uvicorn.Server in a background
    thread so that no external Python interpreter is required. In DEV mode
    we currently do not use this controller; instead the existing launcher
    behaviour is preserved. The DEV hooks are provided for future extension.
    """

    def __init__(self, env: RuntimeEnvironment) -> None:
        self._env = env
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------- public API -----------------------------

    def start(self) -> None:
        """Start the backend server appropriate for the current runtime mode."""
        _debug_log(f"[BackendServerController] start() mode={self._env.mode}")
        if self._env.mode is RuntimeMode.FROZEN:
            self._start_inprocess()
        else:
            # For now DEV mode is handled by the existing launcher; we leave
            # this hook in place for possible future use.
            logger.info(
                "BackendServerController.start() called in DEV mode; "
                "no-op (launcher handles backend in development).",
            )

    def stop(self) -> None:
        """Stop the backend server if it was started in-process."""
        _debug_log(f"[BackendServerController] stop() mode={self._env.mode}")
        if self._env.mode is not RuntimeMode.FROZEN:
            _debug_log("[BackendServerController] stop() no-op in DEV mode")
            return

        if self._server is None:
            _debug_log(
                "[BackendServerController] stop() called with no server instance",
            )
            return

        logger.info("Stopping in-process uvicorn server...")
        self._server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=_SHUTDOWN_JOIN_TIMEOUT_SECONDS)
        logger.info("In-process uvicorn server stopped.")
        _debug_log("[BackendServerController] in-process uvicorn server stopped")

    def probe_ready(self) -> tuple[bool, bool]:
        """
        Run one readiness probe of the health and web UI endpoints.

        Returns a (backend_ok, frontend_ok) tuple. Each probe uses a short
        connection timeout so a single call never stalls the caller for
        long; the startup monitor invokes this repeatedly from a Qt timer.
        """
        import urllib.error
        import urllib.request

        base = f"http://{_LOOPBACK_HOST}:{self._env.backend_port}"
        health_url = f"{base}/api/health"
        frontend_url = f"{base}/app/"

        def _probe(url: str) -> bool:
            try:
                with urllib.request.urlopen(
                    url, timeout=_PROBE_TIMEOUT_SECONDS
                ) as resp:
                    code = resp.getcode()
                    return _HTTP_OK <= code < _HTTP_ERROR
            except urllib.error.URLError:
                return False

        return _probe(health_url), _probe(frontend_url)

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """
        Wait until the backend responds on /api/health and /app/ or timeout.

        Returns True if both endpoints appear to be available, False if the
        timeout elapses. The frozen runtime now prefers the non-blocking
        StartupMonitor; this blocking variant remains for callers that need
        a simple synchronous wait.
        """
        _debug_log(
            "[BackendServerController] wait_until_ready() "
            f"port={self._env.backend_port} timeout={timeout}",
        )

        deadline = time.time() + timeout
        while time.time() < deadline:
            backend_ok, frontend_ok = self.probe_ready()
            if backend_ok and frontend_ok:
                logger.info("Backend and frontend are ready.")
                _debug_log(
                    "[BackendServerController] backend/frontend reported ready",
                )
                return True
            time.sleep(_READY_POLL_INTERVAL_SECONDS)

        logger.warning(
            "Timeout waiting for backend/frontend readiness; continuing anyway.",
        )
        _debug_log("[BackendServerController] wait_until_ready() timed out")
        return False

    # ------------------------------- internals -----------------------------

    def _start_inprocess(self) -> None:
        """
        Start uvicorn.Server with backend.src.main:app in a background thread.

        In the frozen onefile build, uvicorn's default logging configuration can
        fail when it tries to attach a colourising formatter to a handler whose
        stream does not expose 'isatty()' in the way it expects. This manifests
        as:

            ValueError("Unable to configure formatter 'default'")

        when uvicorn.Config.configure_logging() calls logging.config.dictConfig.

        To avoid this entirely, we subclass uvicorn.Config and override
        configure_logging() as a no-op so that uvicorn does not touch the
        logging configuration at all. We then rely solely on the application's
        logging configuration from backend.src.utils.logger.setup_logging().
        """
        if self._server is not None:
            logger.info("In-process uvicorn server already started.")
            _debug_log(
                "[BackendServerController] _start_inprocess() called but "
                "server already running",
            )
            return

        class _QuietUvicornConfig(uvicorn.Config):
            def configure_logging(self) -> None:  # type: ignore[override]
                # Do not let uvicorn interfere with logging setup in the frozen
                # runtime.
                return

        host = self._resolve_host()

        _debug_log(
            "[BackendServerController] starting in-process uvicorn on "
            f"{host}:{self._env.backend_port}",
        )

        config = _QuietUvicornConfig(
            app=fastapi_app,
            host=host,
            port=self._env.backend_port,
            log_level="info",
            log_config=None,
        )
        server = uvicorn.Server(config=config)
        self._server = server

        thread = threading.Thread(
            target=self._make_runner(server, host),
            name="uvicorn-inprocess",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        _debug_log("[BackendServerController] uvicorn-inprocess thread started")

    def _resolve_host(self) -> str:
        """
        The bind host from the application's configuration.

        Read from configuration rather than hardcoded so that a configured
        0.0.0.0 allows LAN access.
        """
        try:
            try:
                from .config import get_config  # type: ignore[import-not-found]
            except ImportError:
                from backend.src.config import get_config  # type: ignore[import-error]

            _cfg = get_config()
            return (
                getattr(getattr(_cfg, "server", _cfg), "host", _LOOPBACK_HOST)
                or _LOOPBACK_HOST
            )
        except Exception as exc:  # noqa: BLE001
            # Deliberately broad. This reads host and port out of the parsed
            # configuration, which is built from hand-editable YAML, so a bad value
            # arrives as a validation error rather than one predictable type. The
            # loopback default below is what the installer configures anyway.
            _debug_log(
                "[BackendServerController] Failed to read config for host; "
                f"defaulting to {_LOOPBACK_HOST}: {exc!r}",
            )
            return _LOOPBACK_HOST

    def _make_runner(self, server: uvicorn.Server, host: str):
        """Build the thread body that runs the server until it exits."""

        def _run() -> None:
            try:
                logger.info(
                    "Starting in-process uvicorn server on http://%s:%d",
                    host,
                    self._env.backend_port,
                )
                _debug_log(
                    "[BackendServerController] uvicorn.Server.run() starting on "
                    f"{host}:{self._env.backend_port}",
                )
                server.run()
                _debug_log(
                    "[BackendServerController] uvicorn.Server.run() returned normally",
                )
            except Exception as exc:  # noqa: BLE001
                # Deliberately broad, around the uvicorn server's whole run. Anything
                # escaping here would kill the thread silently and leave the tray icon
                # sitting over a dead backend; logging it is what makes that visible.
                logger.exception("In-process uvicorn server crashed.")
                _debug_log(
                    "[BackendServerController] In-process uvicorn server crashed: "
                    f"{exc!r}",
                )

        return _run


__all__ = ["BackendServerController"]
