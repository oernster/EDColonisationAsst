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

The first sight of a file goes through the parser's whole-file path; every
pass after that is a seek to the stored offset. A file that has shrunk has
been truncated or rotated, so it cannot be a superset of what was already
read and the state for it is discarded.

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
    - Choose between a whole-file parse and a tail parse from that offset.
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

            if offset <= 0:
                return self._parse_whole_file(file_path, key, current_size)

            try:
                return self._parse_tail(file_path, key, offset, partial)
            except OSError:
                # Cannot open, seek or read: fall back to a whole-file parse
                # rather than lose the file until it next changes.
                return self._parse_whole_file(file_path, key, current_size)

    def _parse_whole_file(
        self,
        file_path: Path,
        key: str,
        fallback_size: int,
    ) -> list[JournalEvent]:
        """Parse the entire file and mark the offset at its end.

        The size is read again rather than reused: the parse takes time and
        the game may have appended during it, so the earlier reading would
        skip those bytes on the next pass. `fallback_size` covers the file
        disappearing between the two.
        """
        events = self._parser.parse_file(file_path)
        self.offsets[key] = self._size_of(file_path, default=fallback_size)
        self.partials[key] = b""
        return events

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
        # last pass, which is a handful of lines. The whole-file branch is the
        # expensive one: the first thing worth moving off the loop if this
        # ever becomes a problem.
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
