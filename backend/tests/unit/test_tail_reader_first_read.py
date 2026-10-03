"""The first read of a journal keeps every line, as every later read does.

The tail path already kept a half-written last line and survived bad bytes.
The FIRST sight of a file went through a whole-file parse instead, which:

- set the offset to the file's size after parsing, so anything the game
  appended while the parse ran was never read;
- had no partial-line handling, so a last line the game had not finished
  writing was parsed as broken JSON, dropped and then skipped by the offset;
- opened the file as strict UTF-8, so one bad byte (or a multi-byte
  character split by the game mid-write) returned no events for the file.

Depot snapshots, contributions and Docked events vanished on every start and
folder change, depending on timing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.journal_events import CommanderEvent, JournalEvent
from src.services.journal_parser import JournalParser
from src.services.journal_tail_reader import JournalTailReader


def _commander(name: str) -> bytes:
    return json.dumps(
        {
            "timestamp": "2025-01-01T00:00:00Z",
            "event": "Commander",
            "Name": name,
            "FID": f"F-{name}",
        }
    ).encode("utf-8")


def _names(events: list[JournalEvent]) -> list[str]:
    return [e.name for e in events if isinstance(e, CommanderEvent)]


@pytest.fixture
def journal(tmp_path: Path) -> Path:
    return tmp_path / "Journal.2025-01-01T000000.01.log"


@pytest.mark.asyncio
async def test_a_half_written_last_line_is_read_once_finished(journal: Path) -> None:
    whole = _commander("Second")
    journal.write_bytes(_commander("First") + b"\n" + whole[:10])
    reader = JournalTailReader(JournalParser())

    first = await reader.read_events(journal)
    with open(journal, "ab") as handle:
        handle.write(whole[10:] + b"\n")
    second = await reader.read_events(journal)

    assert _names(first) == ["First"]
    assert _names(second) == ["Second"]


class _AppendingParser(JournalParser):
    """A real parser that has the game append a line while it is working."""

    def __init__(self, journal: Path, line: bytes) -> None:
        super().__init__()
        self._journal = journal
        self._line = line
        self._appended = False

    def _append_once(self) -> None:
        if not self._appended:
            self._appended = True
            with open(self._journal, "ab") as handle:
                handle.write(self._line + b"\n")

    def parse_file(self, file_path: Path) -> list[JournalEvent]:
        # The whole file has been read by the time the parse returns, so the
        # append lands after the bytes this parse saw, as the game's would.
        self._appended_blocked = True
        events = super().parse_file(file_path)
        self._appended_blocked = False
        self._append_once()
        return events

    def parse_line(self, line: str) -> JournalEvent | None:
        event = super().parse_line(line)
        if not getattr(self, "_appended_blocked", False):
            self._append_once()
        return event


@pytest.mark.asyncio
async def test_a_line_appended_during_the_first_read_is_not_skipped(
    journal: Path,
) -> None:
    journal.write_bytes(_commander("First") + b"\n")
    reader = JournalTailReader(_AppendingParser(journal, _commander("Appended")))

    first = await reader.read_events(journal)
    second = await reader.read_events(journal)

    assert _names(first) + _names(second) == ["First", "Appended"]


@pytest.mark.asyncio
async def test_one_bad_byte_costs_one_line_on_the_first_read(journal: Path) -> None:
    journal.write_bytes(
        _commander("Before") + b"\n\xff\xfe broken\n" + _commander("After") + b"\n"
    )
    reader = JournalTailReader(JournalParser())

    events = await reader.read_events(journal)

    assert _names(events) == ["Before", "After"]


def test_a_whole_file_parse_survives_a_bad_byte(journal: Path) -> None:
    journal.write_bytes(
        _commander("Before") + b"\n\xff\xfe broken\n" + _commander("After") + b"\n"
    )

    events = JournalParser().parse_file(journal)

    assert _names(events) == ["Before", "After"]
