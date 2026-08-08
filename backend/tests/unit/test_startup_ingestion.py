"""Tests for the startup journal catch-up in src.services.startup_ingestion.

These two paths ran unmeasured while they lived in main.py, which the coverage
gate omits: every test that touched them replaced them with a fake. They are
gated now, so both are driven here for real, including every degradation path,
because degrading rather than raising is the whole point of them.

The ingestion itself is not re-tested: the handler these functions build is the
same one test_coverage_journal_ingestion covers. What is asserted here is which
files get handed to it, in what order and what happens when a collaborator
fails.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import src.services.startup_ingestion as startup_ingestion
from src.services.startup_ingestion import (
    notify_clients_best_effort,
    prime_colonisation_database_if_empty,
    sync_latest_journals_best_effort,
)


class FakeRepository:
    """Repository fake answering only the stats query these paths make."""

    def __init__(self, total_sites: int = 0) -> None:
        self._total_sites = total_sites

    async def get_stats(self) -> dict[str, int]:
        return {"total_sites": self._total_sites}


class RaisingStatsRepository(FakeRepository):
    """Repository fake whose stats query always fails."""

    async def get_stats(self) -> dict[str, int]:
        raise RuntimeError("database unavailable")


class RecordingHandler:
    """JournalFileHandler stand-in recording the files it was given."""

    def __init__(self, **_kwargs: Any) -> None:
        self.processed: list[Path] = []

    async def _process_file(self, file_path: Path) -> None:
        self.processed.append(file_path)


class FailingHandler(RecordingHandler):
    """Handler stand-in that fails on one named file and records the rest."""

    failing_name = "Journal.bad.log"

    async def _process_file(self, file_path: Path) -> None:
        if Path(file_path).name == self.failing_name:
            raise RuntimeError("unparseable journal")
        self.processed.append(file_path)


class RaisingChangeBus:
    """Change bus fake whose bump always fails."""

    async def bump(self) -> None:
        raise RuntimeError("no listeners")


def write_journals(directory: Path, names: list[str]) -> list[Path]:
    """Create journal files with increasing modification times."""
    created: list[Path] = []
    for index, name in enumerate(names):
        path = directory / name
        path.write_text("{}\n", encoding="utf-8")
        # Stagger mtimes so the oldest-first sort is deterministic rather than
        # dependent on filesystem timestamp resolution.
        import os

        os.utime(path, (1_000_000 + index, 1_000_000 + index))
        created.append(path)
    return created


def install_handler(
    monkeypatch: pytest.MonkeyPatch,
    handler_cls: type = RecordingHandler,
) -> list[RecordingHandler]:
    """Swap the real handler for a recording stand-in; return built instances."""
    built: list[RecordingHandler] = []

    def _factory(**kwargs: Any) -> RecordingHandler:
        handler = handler_cls(**kwargs)
        built.append(handler)
        return handler

    monkeypatch.setattr(startup_ingestion, "JournalFileHandler", _factory)
    return built


def install_journal_dir(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Point get_config at a journal directory of our choosing."""
    config = SimpleNamespace(journal=SimpleNamespace(directory=str(directory)))
    monkeypatch.setattr(startup_ingestion, "get_config", lambda: config)


# --------------------------------------------------------------- prime


async def test_prime_skips_when_stats_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A repository that cannot answer stats skips the preload entirely."""
    built = install_handler(monkeypatch)
    install_journal_dir(monkeypatch, tmp_path)
    write_journals(tmp_path, ["Journal.one.log"])

    await prime_colonisation_database_if_empty(
        RaisingStatsRepository(), object(), object()
    )

    assert built == []


async def test_prime_skips_when_database_already_has_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A populated database is never backfilled."""
    built = install_handler(monkeypatch)
    install_journal_dir(monkeypatch, tmp_path)
    write_journals(tmp_path, ["Journal.one.log"])

    await prime_colonisation_database_if_empty(
        FakeRepository(total_sites=3), object(), object()
    )

    assert built == []


async def test_prime_skips_when_config_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configuration that will not parse leaves nothing to preload from."""
    built = install_handler(monkeypatch)

    def _raising_config() -> Any:
        raise ValueError("invalid journal directory")

    monkeypatch.setattr(startup_ingestion, "get_config", _raising_config)

    await prime_colonisation_database_if_empty(FakeRepository(), object(), object())

    assert built == []


async def test_prime_skips_when_journal_directory_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal directory that does not exist is reported, not created."""
    built = install_handler(monkeypatch)
    missing = tmp_path / "no-such-directory"
    install_journal_dir(monkeypatch, missing)

    await prime_colonisation_database_if_empty(FakeRepository(), object(), object())

    assert built == []
    assert not missing.exists()


async def test_prime_skips_when_directory_holds_no_journals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing directory with no Journal.*.log files builds no handler."""
    built = install_handler(monkeypatch)
    install_journal_dir(monkeypatch, tmp_path)
    (tmp_path / "Market.json").write_text("{}", encoding="utf-8")

    await prime_colonisation_database_if_empty(FakeRepository(), object(), object())

    assert built == []


async def test_prime_processes_every_journal_oldest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full history is walked in modification order on a first run."""
    built = install_handler(monkeypatch)
    install_journal_dir(monkeypatch, tmp_path)
    created = write_journals(
        tmp_path, ["Journal.first.log", "Journal.second.log", "Journal.third.log"]
    )

    await prime_colonisation_database_if_empty(FakeRepository(), object(), object())

    assert built[0].processed == created


async def test_prime_continues_past_a_file_that_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One unparseable journal must not abandon the remaining history."""
    built = install_handler(monkeypatch, handler_cls=FailingHandler)
    install_journal_dir(monkeypatch, tmp_path)
    write_journals(
        tmp_path,
        ["Journal.first.log", FailingHandler.failing_name, "Journal.last.log"],
    )

    await prime_colonisation_database_if_empty(FakeRepository(), object(), object())

    processed = [path.name for path in built[0].processed]
    assert processed == ["Journal.first.log", "Journal.last.log"]


# --------------------------------------------------------------- tail sync


async def test_tail_sync_returns_when_directory_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing journal directory ends the tail sync before any work."""
    built = install_handler(monkeypatch)
    loop = asyncio.get_running_loop()

    await sync_latest_journals_best_effort(
        object(), object(), FakeRepository(), tmp_path / "gone", loop
    )

    assert built == []


async def test_tail_sync_returns_when_no_journals_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty journal directory ends the tail sync before any work."""
    built = install_handler(monkeypatch)
    loop = asyncio.get_running_loop()

    await sync_latest_journals_best_effort(
        object(), object(), FakeRepository(), tmp_path, loop
    )

    assert built == []


async def test_tail_sync_processes_only_the_newest_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the bounded tail is re-read, newest last so it wins the merge."""
    built = install_handler(monkeypatch)
    created = write_journals(
        tmp_path,
        [f"Journal.{index}.log" for index in range(5)],
    )
    loop = asyncio.get_running_loop()

    await sync_latest_journals_best_effort(
        object(), object(), FakeRepository(), tmp_path, loop
    )

    expected = created[-startup_ingestion._TAIL_JOURNAL_FILE_COUNT :]
    assert built[0].processed == expected


async def test_tail_sync_survives_a_handler_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure anywhere in the sync is logged and swallowed, never raised."""
    install_handler(monkeypatch, handler_cls=FailingHandler)
    write_journals(tmp_path, [FailingHandler.failing_name])
    loop = asyncio.get_running_loop()

    # No assertion beyond "this returns": the contract is that startup is
    # never taken down by the best-effort catch-up.
    await sync_latest_journals_best_effort(
        object(), object(), FakeRepository(), tmp_path, loop
    )


# --------------------------------------------------------------- refresh hint


async def test_notify_clients_bumps_the_change_sequence() -> None:
    """The happy path advances the sequence long-poll clients watch."""
    before = startup_ingestion.change_bus.seq

    await notify_clients_best_effort()

    assert startup_ingestion.change_bus.seq > before


async def test_notify_clients_swallows_a_failing_bump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refresh hint that cannot be sent costs one poll, never an exception."""
    monkeypatch.setattr(startup_ingestion, "change_bus", RaisingChangeBus())

    await notify_clients_best_effort()
