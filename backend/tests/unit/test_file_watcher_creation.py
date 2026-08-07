"""Creation events and existing-file scans.

Split out of test_file_watcher.py; the scaffolding lives in _test_file_watcher_support.py.
"""

import asyncio
from pathlib import Path
import pytest
from src.repositories.colonisation_repository import ColonisationRepository
from src.services.file_watcher import FileWatcher, JournalFileHandler
from src.services.journal_parser import JournalParser
from src.services.system_tracker import SystemTracker

from tests.unit._test_file_watcher_support import (
    _DummyParser,
)


def test_journal_file_handler_on_created_schedules_for_journal_files(monkeypatch):
    """on_created should schedule processing for valid Journal.*.log files."""
    from types import SimpleNamespace

    parser = _DummyParser()
    system_tracker = SystemTracker()
    repository = ColonisationRepository()
    loop = asyncio.get_event_loop()
    handler = JournalFileHandler(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=loop,
    )

    scheduled: list[tuple[object, object]] = []

    def fake_run_coroutine_threadsafe(coro, target_loop):
        """
        Test stub for asyncio.run_coroutine_threadsafe for on_created.
        """
        scheduled.append((coro, target_loop))
        try:
            coro.close()  # type: ignore[func-returns-value]
        except Exception:
            pass

        class DummyFuture:
            def cancel(self) -> None:
                pass

        return DummyFuture()

    orig_run = asyncio.run_coroutine_threadsafe
    asyncio.run_coroutine_threadsafe = fake_run_coroutine_threadsafe
    try:
        # Directory events should be ignored
        dir_event = SimpleNamespace(
            is_directory=True, src_path=str(Path("Journal.2025-01-01T000000.01.log"))
        )
        handler.on_created(dir_event)
        assert scheduled == []

        # Non-journal files should be ignored
        non_journal_event = SimpleNamespace(
            is_directory=False, src_path=str(Path("notes.txt"))
        )
        handler.on_created(non_journal_event)
        assert scheduled == []

        # Valid journal file should schedule processing
        journal_event = SimpleNamespace(
            is_directory=False,
            src_path=str(Path("Journal.2025-01-01T000000.01.log")),
        )
        handler.on_created(journal_event)
        assert len(scheduled) == 1
        _, target_loop = scheduled[0]
        assert target_loop is loop
    finally:
        asyncio.run_coroutine_threadsafe = orig_run


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_with_no_events_does_not_invoke_callback(
    repository: ColonisationRepository,
):
    """_process_file should return early when parser yields no events."""
    system_tracker = SystemTracker()

    class EmptyParser:
        def parse_file(self, file_path: Path):
            return []

        def parse_line(self, line: str):
            return None

    callback_called: list[str] = []

    async def _callback(system_name: str) -> None:
        callback_called.append(system_name)

    handler = JournalFileHandler(
        parser=EmptyParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=_callback,
        loop=asyncio.get_running_loop(),
    )

    await handler._process_file(Path("Journal.empty.log"))
    # No systems should have been reported because there were no events
    assert callback_called == []


@pytest.mark.asyncio
async def test_journal_file_handler_process_file_handles_parser_exception(
    repository: ColonisationRepository,
):
    """_process_file should catch and log exceptions from parser.parse_file."""
    system_tracker = SystemTracker()

    class FailingParser:
        def parse_file(self, file_path: Path):
            raise RuntimeError("boom")

        def parse_line(self, line: str):
            return None

    handler = JournalFileHandler(
        parser=FailingParser(),
        system_tracker=system_tracker,
        repository=repository,
        update_callback=None,
        loop=asyncio.get_running_loop(),
    )

    # Should not raise despite the parser throwing
    await handler._process_file(Path("Journal.failure.log"))


@pytest.mark.asyncio
async def test_file_watcher_process_existing_files_invokes_handler_for_journals(
    tmp_path: Path,
    repository: ColonisationRepository,
):
    """_process_existing_files should call the handler for each existing Journal.*.log file."""
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir()

    # Non-journal file should be ignored
    (journal_dir / "notes.txt").write_text("ignore", encoding="utf-8")

    j1 = journal_dir / "Journal.2025-01-01T000000.01.log"
    j2 = journal_dir / "Journal.2025-01-02T000000.01.log"
    j1.write_text("one", encoding="utf-8")
    j2.write_text("two", encoding="utf-8")

    parser = JournalParser()
    system_tracker = SystemTracker()
    watcher = FileWatcher(
        parser=parser,
        system_tracker=system_tracker,
        repository=repository,
        loop=asyncio.get_running_loop(),
    )

    called_paths: list[Path] = []

    class DummyHandler:
        async def _process_file(self, file_path: Path) -> None:
            called_paths.append(file_path)

    # Inject our dummy handler so we can observe calls
    watcher._handler = DummyHandler()  # type: ignore[assignment]

    await watcher._process_existing_files(journal_dir)

    assert {p.name for p in called_paths} == {j1.name, j2.name}
