"""Incremental reading of Elite Dangerous journal files.

A journal is append-only: the game writes one JSON line at a time and keeps
the file open for the whole session. Re-parsing the whole file on every
watchdog event would replay every event already ingested, so this reader
remembers where it stopped.

Two pieces of state per file make that safe:

- the byte offset already consumed, so the next pass reads only what has been
  appended since;
- any trailing bytes of a line the game had not yet terminated with a
  newline, retained and retried on the next pass rather than parsed as a
  truncated JSON object.

The first sight of a file is the same read from offset zero, so it gets the
same partial-line retention and the same tolerance of bad bytes as every later
pass. It used to go through the parser's whole-file path, which set the
offset to the size measured AFTER parsing (skipping whatever the game appended
meanwhile). It also parsed a half-written last line as broken JSON before
skipping it; one byte that was not UTF-8 lost it the whole file. A file that has
shrunk has been truncated or rotated, so it cannot be a superset of what was
already read and the state for it is discarded.

`JournalFileHandler` in src.services.journal_ingestion owns the watchdog side
and delegates every read here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..models.journal_events import JournalEvent
from .journal_parser import IJournalParser


class JournalTailReader:
    """Reads only the journal lines that have not been consumed yet.

    Responsibilities:
    - Track a byte offset and a partial-line buffer per journal file.
    - Parse what lies past that offset, starting at zero on first sight.
    - Absorb the failures of a file being written while it is read.
    """

    def __init__(self, parser: IJournalParser) -> None:
        self._parser = parser
        # How many BYTES of each file have already been read.
        self.offsets: dict[str, int] = {}
        # Trailing partial-line bytes per file, retried on the next pass.
        self.partials: dict[str, bytes] = {}
        # Prevent concurrent incremental reads of the same file.
        self._lock = asyncio.Lock()

    async def read_events(self, file_path: Path) -> list[JournalEvent]:
        """Return the events appended to `file_path` since the last read.

        Args:
            file_path: path to the journal file to read.

        Returns:
            The events parsed from the new bytes, oldest first.
        """
        async with self._lock:
            key = str(file_path)
            offset = int(self.offsets.get(key, 0))
            partial = self.partials.get(key, b"")

            current_size = self._size_of(file_path, default=0)

            # Truncation or rotation: what is there now is not a superset of
            # what was already read, so start the file again.
            if current_size < offset:
                offset = 0
                partial = b""

            try:
                return self._parse_tail(file_path, key, offset, partial)
            except OSError:
                # Cannot open, seek or read. Nothing was consumed, so the
                # stored state is left as it was and the next pass retries
                # from the same place rather than skipping anything.
                return []

    def _parse_tail(
        self,
        file_path: Path,
        key: str,
        offset: int,
        partial: bytes,
    ) -> list[JournalEvent]:
        """Parse only the bytes appended since `offset`.

        Reading while the game is mid-write yields a final line with no
        terminating newline. That fragment is kept and prepended to the next
        chunk instead of being parsed as truncated JSON.
        """
        # This read blocks the event loop, deliberately: it seeks to the
        # stored offset and takes only what the game has appended since the
        # last pass, which is a handful of lines. The first sight of a file
        # reads all of it: the first thing worth moving off the loop if this
        # ever becomes a problem. The offset advances by exactly the bytes
        # read, so anything appended after this read is the next pass's.
        with open(file_path, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
            new_offset = offset + len(chunk)

        parts = (partial + chunk).split(b"\n")
        # The last part is whatever followed the final newline: empty when the
        # chunk was newline-terminated, a partial line when it was not.
        events = self._parse_lines(parts[:-1])

        self.offsets[key] = new_offset
        self.partials[key] = parts[-1]
        return events

    def _parse_lines(self, parts: list[bytes]) -> list[JournalEvent]:
        """Parse complete lines, skipping the ones that cannot be used."""
        events: list[JournalEvent] = []
        for part in parts:
            line = self._decode(part)
            if not line:
                continue
            try:
                event = self._parser.parse_line(line)
            except Exception:  # noqa: BLE001, S112
                # Keep processing. The parser logs the cause itself, so
                # logging again here would duplicate every parse failure; one
                # unparseable line must not stop the remaining events in the
                # chunk.
                continue
            if event is not None:
                events.append(event)
        return events

    @staticmethod
    def _decode(part: bytes) -> str:
        """Decode one line, returning an empty string for anything unusable."""
        if not part:
            return ""
        try:
            return part.decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            # errors="replace" already absorbs bad bytes, so reaching here
            # means the line is unusable rather than merely odd. One bad line
            # must not abandon the rest of the chunk; logging every one would
            # flood the log during a live tail.
            return ""

    @staticmethod
    def _size_of(file_path: Path, default: int) -> int:
        """Current size of the file; `default` when it cannot be read."""
        try:
            return file_path.stat().st_size
        except OSError:
            return default
