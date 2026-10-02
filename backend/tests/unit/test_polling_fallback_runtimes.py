"""Whether the journal polling fallback starts, per way of running EDCA.

The fallback is the safety net for journal appends that watchdog reports
inconsistently, so it has to run in every build that ships. Neither shipped
route is a frozen executable. The Windows shortcut runs a renamed pythonw.exe
over edca_launch.py, which sets the deployment marker. The Flatpak runs
python3 -m backend.src.runtime_entry inside a sandbox that names itself. These
tests present each route's process conditions to the real watcher (started on
a real directory) then read back whether the poller is running.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import pytest

from src.utils.runtime import APPLICATION_ID
from tests.unit._test_coverage_file_watcher_support import _make_watcher

DEPLOYED_ENV = "EDCA_PACKAGED"
DEPLOYED_VALUE = "1"
FLATPAK_ENV = "FLATPAK_ID"

# argv[0] as each route leaves it. A script run puts the path of the Python
# file there rather than the interpreter's; python -m does the same.
LAUNCH_SCRIPT = "edca_launch.py"
RUNTIME_ENTRY = Path("backend") / "src" / "runtime_entry.py"


def _present_route(
    monkeypatch: pytest.MonkeyPatch, argv0: Path, env: dict[str, str]
) -> None:
    """Make the process look like one way of running EDCA and nothing else."""
    monkeypatch.delenv(DEPLOYED_ENV, raising=False)
    monkeypatch.delenv(FLATPAK_ENV, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "argv", [str(argv0)])
    for name, value in env.items():
        monkeypatch.setenv(name, value)


async def _poller_runs_after_start(directory: Path) -> bool:
    """Start the real watcher on directory; answer whether the poller runs."""
    watcher = _make_watcher(loop=asyncio.get_running_loop())
    await watcher.start_watching(directory, process_existing=False)
    try:
        return watcher.poller_running()
    finally:
        await watcher.stop_watching()


async def test_installed_windows_build_starts_the_poller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shortcut's process: launch script argv, marker set, not frozen."""
    _present_route(
        monkeypatch, tmp_path / LAUNCH_SCRIPT, {DEPLOYED_ENV: DEPLOYED_VALUE}
    )

    assert await _poller_runs_after_start(tmp_path) is True


async def test_flatpak_build_starts_the_poller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox's process: python -m argv, FLATPAK_ID set, not frozen."""
    _present_route(monkeypatch, tmp_path / RUNTIME_ENTRY, {FLATPAK_ENV: APPLICATION_ID})

    assert await _poller_runs_after_start(tmp_path) is True


async def test_source_checkout_does_not_start_the_poller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A developer's run states nothing, so watchdog alone serves it."""
    _present_route(monkeypatch, tmp_path / RUNTIME_ENTRY, {})

    assert await _poller_runs_after_start(tmp_path) is False
