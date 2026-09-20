"""The installed deployment's marker, plus the mode it puts the runtime into.

A Windows deployment runs a plain interpreter over plain sources, so nothing
about the process can be read back to say that it is installed: ``sys.frozen``
is absent, the executable is a copy of pythonw.exe and there is no sandbox to
name the application. Its launch script states the fact in the environment
before it imports anything; this module holds every test of that statement.
These tests are separate from the general runtime suite because that file is at
the module size limit. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from src.utils import runtime as runtime_mod

DEPLOYED_ENV = "EDCA_PACKAGED"
FLATPAK_ENV = "FLATPAK_ID"


@pytest.fixture()
def plain_interpreter(monkeypatch):
    """Present the process as a plain interpreter in no sandbox at all.

    Every test here turns on the deployment marker being the only thing that
    answers; the other two detections are therefore silenced rather than left
    to whatever started the suite.
    """
    monkeypatch.delenv(FLATPAK_ENV, raising=False)
    monkeypatch.delenv(DEPLOYED_ENV, raising=False)
    orig_frozen = getattr(sys, "frozen", None)
    orig_argv0 = sys.argv[0]
    if hasattr(sys, "frozen"):
        delattr(sys, "frozen")
    sys.argv[0] = str(Path(sys.executable))
    try:
        yield
    finally:
        sys.argv[0] = orig_argv0
        if orig_frozen is not None:
            sys.frozen = orig_frozen  # type: ignore[attr-defined]
        elif hasattr(sys, "frozen"):
            delattr(sys, "frozen")


def test_nothing_claims_a_deployment_when_the_variable_is_absent(
    plain_interpreter,
) -> None:
    assert runtime_mod.is_deployed() is False


def test_an_empty_marker_is_not_a_deployment(plain_interpreter, monkeypatch) -> None:
    """An empty value is the variable being unset, not a deployment."""
    monkeypatch.setenv(DEPLOYED_ENV, "")

    assert runtime_mod.is_deployed() is False


def test_the_launch_script_marker_states_a_deployment(
    plain_interpreter, monkeypatch
) -> None:
    monkeypatch.setenv(DEPLOYED_ENV, "1")

    assert runtime_mod.is_deployed() is True


def test_a_deployment_is_the_packaged_mode_without_being_frozen(
    plain_interpreter, monkeypatch
) -> None:
    """This is the case the marker exists for.

    An installed EDCA ships an interpreter rather than a compiled executable,
    so is_frozen() answers no while the layout is every bit as fixed as a
    frozen one: the dependencies are already there and the install directory
    must not be written into.
    """
    monkeypatch.setenv(DEPLOYED_ENV, "1")

    assert runtime_mod.is_frozen() is False
    assert runtime_mod.is_flatpak() is False
    assert runtime_mod.get_runtime_mode() == runtime_mod.RuntimeMode.FROZEN
    assert runtime_mod.is_packaged() is True
