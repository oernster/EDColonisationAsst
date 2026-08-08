"""Tests for src/utils/ports.py.

Real sockets on real ports, no mock libraries: a port is held open by binding
one, which is the only way to produce the in-use case honestly. The reserved
case cannot be produced on demand, since it needs an operating-system port
reservation, so it is driven through the categoriser with the error the
platform actually raises (WSAEACCES arrives as EACCES).
"""

from __future__ import annotations

import errno
from pathlib import Path
import socket

from src.utils import ports

_HOST = "127.0.0.1"


def _free_port() -> int:
    """Return a port that is free at the moment it is asked for."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((_HOST, 0))
        return int(probe.getsockname()[1])


# ---------------------------------------------------------------------------
# probe_port and the categories
# ---------------------------------------------------------------------------


def test_probe_reports_a_free_port_as_free() -> None:
    assert ports.probe_port(_HOST, _free_port()) == ports.PORT_FREE


def test_probe_reports_a_held_port_as_in_use() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((_HOST, 0))
        held.listen()
        port = int(held.getsockname()[1])

        assert ports.probe_port(_HOST, port) == ports.PORT_IN_USE


def test_permission_denied_is_reserved_not_in_use() -> None:
    """A Windows port reservation refuses with EACCES while nothing listens.

    Telling this apart from a port in use is the whole point: an in-use port is
    a running instance worth opening, while a reserved one is a dead end that
    must be stepped over. Conflating them is why the splash once advised
    closing a program that was not running.
    """
    reserved = OSError(errno.EACCES, "forbidden by its access permissions")
    in_use = OSError(errno.EADDRINUSE, "address already in use")

    assert ports._categorise(reserved) == ports.PORT_RESERVED
    assert ports._categorise(in_use) == ports.PORT_IN_USE


def test_an_unrecognised_bind_failure_is_merely_unusable() -> None:
    assert ports._categorise(OSError(errno.ENOMEM, "out of memory")) == (
        ports.PORT_UNUSABLE
    )


def test_describe_names_each_category_and_shrugs_at_the_rest() -> None:
    assert "8000" in ports.describe(ports.PORT_IN_USE, 8000)
    assert "reserved by Windows" in ports.describe(ports.PORT_RESERVED, 8000)
    assert "8000" in ports.describe(ports.PORT_UNUSABLE, 8000)
    assert ports.describe(ports.PORT_FREE, 8000) == ""


# ---------------------------------------------------------------------------
# choose_port
# ---------------------------------------------------------------------------


def test_choose_prefers_the_configured_port_when_it_is_free() -> None:
    preferred = _free_port()

    assert ports.choose_port(_HOST, preferred) == preferred


def test_choose_reuses_a_recorded_port_so_the_address_stays_stable() -> None:
    recorded = _free_port()
    preferred = _free_port()

    assert ports.choose_port(_HOST, preferred, recorded=recorded) == recorded


def test_choose_reuses_a_recorded_port_that_is_already_being_served() -> None:
    """An in-use recorded port is this application's own running instance."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.bind((_HOST, 0))
        held.listen()
        recorded = int(held.getsockname()[1])

        assert ports.choose_port(_HOST, _free_port(), recorded=recorded) == recorded


def test_choose_steps_over_a_reserved_preference(monkeypatch) -> None:
    """A reserved configured port must not stop the backend starting.

    This is the case that took the application down: 8000 sat inside a range
    Windows had reserved, so it could never be bound however unused it looked.
    """
    preferred = 8000
    assigned = _free_port()

    monkeypatch.setattr(ports, "probe_port", lambda host, port: ports.PORT_RESERVED)
    monkeypatch.setattr(ports, "os_assigned_port", lambda host: assigned)

    assert ports.choose_port(_HOST, preferred) == assigned


def test_choose_steps_over_a_reserved_recorded_port(monkeypatch) -> None:
    """Reservations move between reboots, so a recorded port can go bad."""
    assigned = _free_port()
    monkeypatch.setattr(ports, "probe_port", lambda host, port: ports.PORT_RESERVED)
    monkeypatch.setattr(ports, "os_assigned_port", lambda host: assigned)

    assert ports.choose_port(_HOST, 8000, recorded=8049) == assigned


def test_choose_reports_nothing_when_no_port_can_be_had(monkeypatch) -> None:
    monkeypatch.setattr(ports, "probe_port", lambda host, port: ports.PORT_RESERVED)
    monkeypatch.setattr(ports, "os_assigned_port", lambda host: None)

    assert ports.choose_port(_HOST, 8000) is None


def test_os_assigned_port_returns_a_usable_port() -> None:
    assigned = ports.os_assigned_port(_HOST)

    assert assigned is not None
    assert ports.probe_port(_HOST, assigned) == ports.PORT_FREE


def test_os_assigned_port_reports_nothing_on_an_unusable_host() -> None:
    assert ports.os_assigned_port("this-host-does-not-resolve.invalid") is None


# ---------------------------------------------------------------------------
# Recording the chosen port
# ---------------------------------------------------------------------------


def test_recorded_port_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "runtime-port"
    ports.record_port(path, 9057)

    assert ports.read_recorded_port(path) == 9057


def test_reading_a_missing_record_reports_nothing(tmp_path: Path) -> None:
    assert ports.read_recorded_port(tmp_path / "absent") is None


def test_reading_a_record_that_is_not_a_number_reports_nothing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-port"
    path.write_text("not a port", encoding="utf-8")

    assert ports.read_recorded_port(path) is None


def test_recording_creates_the_directory_and_never_raises(tmp_path: Path) -> None:
    nested = tmp_path / "made" / "on" / "demand" / "runtime-port"
    ports.record_port(nested, 9057)

    assert ports.read_recorded_port(nested) == 9057


def test_recording_survives_a_path_it_cannot_write(tmp_path: Path) -> None:
    """A stable port is a convenience; failing to record it must cost nothing."""
    blocked = tmp_path / "a-file"
    blocked.write_text("in the way", encoding="utf-8")

    ports.record_port(blocked / "runtime-port", 9057)  # must not raise
