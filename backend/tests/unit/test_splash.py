from __future__ import annotations

"""Tests for the startup splash readiness logic.

These tests exercise [`src.runtime.splash`](backend/src/runtime/splash.py:1)
without a Qt event loop or worker threads:

- [`startup_status_message()`](backend/src/runtime/splash.py:1) is a pure
  function.
- [`StartupMonitor`](backend/src/runtime/splash.py:1) accepts an injectable
  clock and its probe_once()/poll_once() methods can be driven directly.
  In production probe_once() runs on a worker thread (blocking network
  probes) while poll_once() runs on the Qt timer and only reads the
  stored result, keeping the UI fluid; the tests drive the same pair
  synchronously.
"""

from typing import Iterator, List, Tuple

import src.runtime.splash as splash_mod


# ---------------------------------------------------------------------------
# startup_status_message
# ---------------------------------------------------------------------------


def test_startup_status_message_transitions() -> None:
    assert (
        splash_mod.startup_status_message(False, False)
        == splash_mod.STATUS_STARTING_BACKEND
    )
    # The frontend is served by the backend, so backend-down dominates even
    # if the frontend probe somehow passed.
    assert (
        splash_mod.startup_status_message(False, True)
        == splash_mod.STATUS_STARTING_BACKEND
    )
    assert (
        splash_mod.startup_status_message(True, False)
        == splash_mod.STATUS_WAITING_FRONTEND
    )
    assert splash_mod.startup_status_message(True, True) == splash_mod.STATUS_READY


# ---------------------------------------------------------------------------
# StartupMonitor
# ---------------------------------------------------------------------------


class MonitorHarness:
    """Collects monitor callbacks for assertions."""

    def __init__(self) -> None:
        self.statuses: List[str] = []
        self.ready_calls = 0
        self.timeout_calls = 0

    def on_status(self, message: str) -> None:
        self.statuses.append(message)

    def on_ready(self) -> None:
        self.ready_calls += 1

    def on_timeout(self) -> None:
        self.timeout_calls += 1


def make_monitor(
    probe_results: Iterator[Tuple[bool, bool]],
    harness: MonitorHarness,
    clock_values: Iterator[float],
    timeout_seconds: float = 10.0,
) -> splash_mod.StartupMonitor:
    last_clock: List[float] = [0.0]

    def probe() -> Tuple[bool, bool]:
        return next(probe_results)

    def monotonic() -> float:
        try:
            last_clock[0] = next(clock_values)
        except StopIteration:
            pass
        return last_clock[0]

    return splash_mod.StartupMonitor(
        probe=probe,
        on_status=harness.on_status,
        on_ready=harness.on_ready,
        on_timeout=harness.on_timeout,
        timeout_seconds=timeout_seconds,
        monotonic=monotonic,
    )


def step(monitor: splash_mod.StartupMonitor) -> None:
    """One production cycle: worker probes, then the UI timer consumes."""
    monitor.probe_once()
    monitor.poll_once()


def test_monitor_reports_progress_then_ready_exactly_once() -> None:
    harness = MonitorHarness()
    probes = iter([(False, False), (True, False), (True, True)])
    # Clock stays well inside the 10s budget.
    clock = iter([0.0, 0.0, 1.0, 1.0, 2.0, 2.0])

    monitor = make_monitor(probes, harness, clock)

    step(monitor)
    step(monitor)
    step(monitor)

    assert harness.statuses == [
        splash_mod.STATUS_STARTING_BACKEND,
        splash_mod.STATUS_WAITING_FRONTEND,
        splash_mod.STATUS_READY,
    ]
    assert harness.ready_calls == 1
    assert harness.timeout_calls == 0
    assert monitor.finished is True

    # Further polls are no-ops once finished.
    monitor.poll_once()
    assert harness.ready_calls == 1
    assert len(harness.statuses) == 3


def test_monitor_poll_before_first_probe_reports_starting() -> None:
    """The UI timer may fire before the worker's first probe completes;
    the default stored result must read as backend-not-ready."""
    harness = MonitorHarness()
    probes: Iterator[Tuple[bool, bool]] = iter([])
    clock = iter([0.0, 0.0])

    monitor = make_monitor(probes, harness, clock)

    monitor.poll_once()

    assert harness.statuses == [splash_mod.STATUS_STARTING_BACKEND]
    assert monitor.finished is False


def test_monitor_times_out_when_budget_elapses() -> None:
    harness = MonitorHarness()

    def never_ready() -> Iterator[Tuple[bool, bool]]:
        while True:
            yield (False, False)

    # First poll anchors the deadline at 0 + 10; the second poll's timeout
    # check reads 11.0 which is past the deadline.
    clock = iter([0.0, 5.0, 11.0, 11.0])

    monitor = make_monitor(never_ready(), harness, clock, timeout_seconds=10.0)

    step(monitor)
    assert harness.timeout_calls == 0

    step(monitor)
    assert harness.timeout_calls == 1
    assert harness.ready_calls == 0
    assert monitor.finished is True


def test_monitor_treats_probe_exception_as_not_ready() -> None:
    harness = MonitorHarness()

    def exploding_probe() -> Tuple[bool, bool]:
        raise OSError("probe failed")

    clock_value: List[float] = [0.0]

    monitor = splash_mod.StartupMonitor(
        probe=exploding_probe,
        on_status=harness.on_status,
        on_ready=harness.on_ready,
        on_timeout=harness.on_timeout,
        timeout_seconds=10.0,
        monotonic=lambda: clock_value[0],
    )

    monitor.probe_once()
    monitor.poll_once()

    assert harness.statuses == [splash_mod.STATUS_STARTING_BACKEND]
    assert harness.ready_calls == 0
    assert harness.timeout_calls == 0
    assert monitor.finished is False


def test_monitor_probe_loop_stops_when_ready_or_stopped() -> None:
    """Drive the worker-thread loop body synchronously: it must stop on a
    ready result and honour the stop event without further probing."""
    harness = MonitorHarness()
    calls: List[int] = []

    def probe() -> Tuple[bool, bool]:
        calls.append(1)
        return (True, True)

    monitor = splash_mod.StartupMonitor(
        probe=probe,
        on_status=harness.on_status,
        on_ready=harness.on_ready,
        on_timeout=harness.on_timeout,
        timeout_seconds=10.0,
        interval_ms=1,
        monotonic=lambda: 0.0,
    )

    # Ready result terminates the loop after one probe.
    monitor._probe_loop()
    assert calls == [1]

    # A set stop event prevents any probing at all.
    calls.clear()
    monitor._stop_event.set()
    monitor._probe_loop()
    assert calls == []
