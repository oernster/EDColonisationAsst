"""Watching the backend come up, without blocking the UI thread.

Split out of splash.py, which had reached the module limit while carrying two
jobs: drawing the splash window, and deciding when the thing it is waiting for
is ready. This is the second, and it is the half with rules worth testing:
none of it needs a Qt event loop, a running backend or a thread.

The splash window re-exports what lives here, so callers may import either.
"""

from __future__ import annotations

from collections.abc import Callable
import threading
import time

from PySide6.QtCore import QTimer

# Readiness polling cadence and overall budget. First runs can be slow, so
# the budget is deliberately generous; the monitor stops polling as soon as
# both endpoints respond.
POLL_INTERVAL_MS = 500
READINESS_TIMEOUT_SECONDS = 180.0

# How long the splash stays visible after a timeout so the user can read the
# failure status before it closes.
SPLASH_FAILURE_CLOSE_DELAY_MS = 6000

STATUS_STARTING_BACKEND = "Starting the local backend..."
STATUS_WAITING_FRONTEND = "Backend is up. Preparing the web interface..."
STATUS_READY = "Ready. Opening your browser..."
STATUS_TIMED_OUT = (
    "Startup is taking longer than expected. The tray icon remains "
    "available; use Open Web UI once the backend responds."
)


def startup_status_message(backend_ok: bool, frontend_ok: bool) -> str:
    """Map a readiness probe result onto a user-facing status line."""
    if backend_ok and frontend_ok:
        return STATUS_READY
    if backend_ok:
        return STATUS_WAITING_FRONTEND
    return STATUS_STARTING_BACKEND


class StartupMonitor:
    """Watches a readiness probe and reports progress to the splash.

    The probe returns a ``(backend_ok, frontend_ok)`` tuple and may BLOCK
    (network connect timeouts), so it must never run on the Qt UI thread:
    a blocked timer slot freezes the splash's progress animation. The
    monitor therefore splits the work across two sides:

    - A daemon worker thread runs ``probe_once()`` in a loop, storing the
      latest result (a single tuple assignment, atomic under the GIL).
    - A Qt timer on the UI thread runs ``poll_once()``, which only READS
      the latest result and drives the status/ready/timeout callbacks, so
      each UI tick costs microseconds and the event loop stays fluid.

    Waiting has exactly three ends. When both probes pass the monitor stops
    and calls ``on_ready`` exactly once. When ``failure_reason`` returns a
    reason, the backend is known to be unable to answer and ``on_failure``
    reports that named cause immediately. Only when neither happens inside
    the budget does ``on_timeout`` fire, which is then an honest "still
    starting" rather than a stand-in for every other way startup can fail.
    The clock is injectable and ``probe_once()``/``poll_once()`` can be
    driven directly, so tests need neither threads nor a running Qt event
    loop.
    """

    def __init__(
        self,
        probe: Callable[[], tuple[bool, bool]],
        on_status: Callable[[str], None],
        on_ready: Callable[[], None],
        on_timeout: Callable[[], None],
        failure_reason: Callable[[], str | None],
        on_failure: Callable[[str], None],
        timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
        interval_ms: int = POLL_INTERVAL_MS,
        monotonic: Callable[[], float] = time.monotonic,
        startup_report: Callable[[], object | None] | None = None,
        on_startup_report: Callable[[object], None] | None = None,
    ) -> None:
        self._probe = probe
        self._on_status = on_status
        self._on_ready = on_ready
        self._on_timeout = on_timeout
        self._failure_reason = failure_reason
        self._on_failure = on_failure
        self._startup_report = startup_report
        self._on_startup_report = on_startup_report
        self._timeout_seconds = timeout_seconds
        self._interval_ms = interval_ms
        self._monotonic = monotonic
        self._deadline: float | None = None
        self._timer: QTimer | None = None
        self._finished = False
        self._latest: tuple[bool, bool] = (False, False)
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

    @property
    def finished(self) -> bool:
        return self._finished

    def start(self) -> None:
        """Start the probe worker thread and the UI-side Qt timer."""
        worker = threading.Thread(
            target=self._probe_loop,
            name="startup-readiness-probe",
            daemon=True,
        )
        self._worker = worker
        worker.start()

        timer = QTimer()
        timer.setInterval(self._interval_ms)
        timer.timeout.connect(self.poll_once)
        self._timer = timer
        timer.start()

    def probe_once(self) -> None:
        """Run one blocking probe and record the result.

        Called from the worker thread in production; tests call it
        directly to feed results without a thread.
        """
        try:
            self._latest = self._probe()
        except Exception:  # noqa: BLE001
            # Deliberately broad. The probe makes HTTP requests to a backend that is by
            # definition still starting, so refused connections, timeouts and half-open
            # sockets are all normal here. Not-ready is the honest answer and the next
            # tick tries again.
            self._latest = (False, False)

    def poll_once(self) -> None:
        """Consume the latest probe result; never blocks the UI thread."""
        if self._finished:
            return

        # The deadline is anchored to the first poll so that timer start
        # latency does not eat into the readiness budget.
        if self._deadline is None:
            self._deadline = self._monotonic() + self._timeout_seconds

        backend_ok, frontend_ok = self._latest
        self._on_status(startup_status_message(backend_ok, frontend_ok))
        self._report_startup()

        if backend_ok and frontend_ok:
            self._finish()
            self._on_ready()
            return

        reason = self._failure_reason()
        if reason is not None:
            self._finish()
            self._on_failure(reason)
            return

        if self._monotonic() >= self._deadline:
            self._finish()
            self._on_timeout()

    def _report_startup(self) -> None:
        """Pass on what the backend says it is doing, when it says anything.

        Silence is the normal case early on, and it means "keep showing what
        you were showing" rather than "clear the line", so nothing is
        forwarded until there is a reading.
        """
        if self._startup_report is None or self._on_startup_report is None:
            return

        report = self._startup_report()
        if report is not None:
            self._on_startup_report(report)

    def _probe_loop(self) -> None:
        """Worker-thread loop: probe, store, sleep, until stopped or ready."""
        while not self._stop_event.is_set():
            self.probe_once()
            if self._latest == (True, True):
                return
            self._stop_event.wait(self._interval_ms / 1000.0)

    def _finish(self) -> None:
        self._finished = True
        self._stop_event.set()
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
