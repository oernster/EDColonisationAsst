"""Choosing a port the backend can actually bind; remembering which one.

A fixed port is not something a desktop application can rely on. Windows
reserves whole ranges for Hyper-V and WinNAT. A reserved port refuses a bind
with WSAEACCES while nothing whatsoever is listening on it, so the usual "is
anything using this port" check reports it as free. Measured on a real
machine, the entire 7949 to 9056 band was reserved, which swallowed the 8000
this application asked for by default: uvicorn could not bind, so the startup
splash waited for a backend that was never going to answer.

The two failures therefore have to be told apart, because they call for
opposite responses. A port already in use may well be this application's own
running instance, which is exactly where a second instance should send the
user. A reserved port is simply unusable and must be stepped over.

Where a preferred port cannot be had, the operating system is asked to supply
one. That is the only choice that cannot collide with a reservation, since the
kernel will not hand out a port it has reserved.
"""

from __future__ import annotations

from collections.abc import Sequence
import errno
from pathlib import Path
import socket

# Binding port zero asks the operating system for a free port of its choosing.
_OS_ASSIGNED = 0

# The categories a bind failure falls into. They are distinct because a port
# that is in use is a running instance worth talking to, while a reserved one
# is a dead end.
PORT_FREE = "free"
PORT_IN_USE = "in use"
PORT_RESERVED = "reserved"
PORT_UNUSABLE = "unusable"

# What the user is told, per category.
REASON_TEXT = {
    PORT_IN_USE: "port {port} is already in use by another program",
    PORT_RESERVED: (
        "port {port} is reserved by Windows and cannot be used by any "
        "application. This is usually Hyper-V, WSL or Docker holding a range "
        "of ports"
    ),
    PORT_UNUSABLE: "port {port} could not be opened",
}


def probe_port(host: str, port: int) -> str:
    """Return which category describes binding ``port`` on ``host`` right now.

    Deliberately without SO_REUSEADDR, because asyncio does not set it on
    Windows either: this bind therefore sees exactly what the server's own bind
    is about to see.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as exc:
            return _categorise(exc)
    return PORT_FREE


def _categorise(exc: OSError) -> str:
    """Map a bind failure onto one of the categories above."""
    if exc.errno == errno.EADDRINUSE:
        return PORT_IN_USE
    if exc.errno in (errno.EACCES, errno.EADDRNOTAVAIL):
        # WSAEACCES is what a Windows port reservation raises; it arrives here
        # as EACCES. Nothing is listening; the port is simply forbidden.
        return PORT_RESERVED
    return PORT_UNUSABLE


def describe(category: str, port: int) -> str:
    """Return the user-facing reason for a category; empty when there is none."""
    template = REASON_TEXT.get(category)
    return template.format(port=port) if template else ""


def os_assigned_port(host: str) -> int | None:
    """Return a free port chosen by the operating system; None if it will not.

    The socket is closed before the caller binds for real, so this is a
    recommendation rather than a reservation. On a desktop machine the window
    between the two is not a practical risk; the alternative is holding a
    socket open across a layer boundary for no measurable gain.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, _OS_ASSIGNED))
            return int(probe.getsockname()[1])
        except OSError:
            return None


def choose_port(
    host: str,
    preferred: int,
    recorded: int | None = None,
    candidates: Sequence[int] = (),
) -> int | None:
    """Pick the port the backend should serve on; None if none can be had.

    Preference order, with the reason for each step:

    1. The port a previous run recorded, when it is free or when something is
       already serving on it. Reusing it keeps the address stable across runs,
       and an in-use recorded port is this application's own instance.
    2. The configured port, when it can be bound.
    3. Each remaining candidate in turn. A known address is worth more than a
       random one: it keeps the web UI somewhere a bookmark can still find.
    4. Whatever the operating system will give, which is the only option a
       reservation cannot take away, at the cost of an address that moves.

    A recorded port that is RESERVED is stepped over rather than reused: that
    is the machine having changed its reservations since the last run.
    """
    if recorded is not None:
        category = probe_port(host, recorded)
        if category in (PORT_FREE, PORT_IN_USE):
            return recorded

    # dict.fromkeys keeps the order while dropping a preferred port that the
    # candidate list also contains, so it is never probed twice.
    for candidate in dict.fromkeys((preferred, *candidates)):
        if probe_port(host, candidate) == PORT_FREE:
            return candidate

    return os_assigned_port(host)


def read_recorded_port(path: Path) -> int | None:
    """Return the port a previous run recorded; None when there is none."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        # Missing, unreadable or holding something that is not a number. All
        # three mean the same thing to the caller: nothing to reuse.
        return None


def record_port(path: Path, port: int) -> None:
    """Record the port now being served, best effort.

    Read by the next run to keep the address stable; also by a second instance
    looking for the web UI of the one already running. Failing to write it
    costs a stable port and nothing else, so it never breaks startup.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(port), encoding="utf-8")
    except OSError:
        return


__all__ = [
    "PORT_FREE",
    "PORT_IN_USE",
    "PORT_RESERVED",
    "PORT_UNUSABLE",
    "choose_port",
    "describe",
    "os_assigned_port",
    "probe_port",
    "read_recorded_port",
    "record_port",
]
