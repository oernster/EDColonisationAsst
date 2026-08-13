from __future__ import annotations

"""Tests for the identity a window announces to the desktop.

A desktop ties a running window back to the launcher it was started from by
matching strings. Those strings live in two languages: the Qt application
name and the desktop-file id in Python, the same two values written into the
generated .desktop entry by build_flatpak.sh. Nothing at runtime checks that
they agree. If they drift the application still starts, still works and simply
appears in the dock as a second, generic entry beside its own launcher, which
is exactly the kind of failure nobody notices until a user mentions it.

So the agreement is asserted here, against the real constants rather than two
copies of the expected text.
"""

from pathlib import Path
import re

import pytest

import src.runtime.app_runtime as app_runtime_mod
from src.utils import runtime as runtime_mod

BUILD_SCRIPT = Path(__file__).resolve().parents[3] / "build_flatpak.sh"


def _shell_assignment(name: str) -> str:
    """Return the value of a top-level double-quoted assignment in the script."""
    text = BUILD_SCRIPT.read_text(encoding="utf-8")
    match = re.search(rf'^{name}="([^"]*)"$', text, re.MULTILINE)
    assert match is not None, f"{name} is not assigned in {BUILD_SCRIPT.name}"
    return match.group(1)


# ---------------------------------------------------------------------------
# desktop_file_name
# ---------------------------------------------------------------------------


def test_desktop_file_name_is_the_application_id_outside_a_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FLATPAK_ID", raising=False)

    assert runtime_mod.desktop_file_name() == runtime_mod.APPLICATION_ID


def test_desktop_file_name_is_taken_from_the_sandbox_when_there_is_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flatpak states the id; it is the same string that named the file.

    Reading it back cannot disagree with the desktop entry on disk the way a
    second copy of the constant could.
    """
    monkeypatch.setenv("FLATPAK_ID", "uk.co.oernster.SomethingElse")

    assert runtime_mod.desktop_file_name() == "uk.co.oernster.SomethingElse"


# ---------------------------------------------------------------------------
# The two languages have to agree
# ---------------------------------------------------------------------------


def test_the_packaged_app_id_matches_the_one_the_application_claims() -> None:
    """The flatpak app id names the desktop entry the application claims."""
    assert _shell_assignment("APP_ID") == runtime_mod.APPLICATION_ID


def test_the_desktop_entry_declares_the_qt_application_name() -> None:
    """StartupWMClass has to be the class half of WM_CLASS, exactly.

    Qt takes that half from the Qt application name, so the packaging script's
    copy of the string and the application's own have to be identical
    character for character. A near miss matches nothing at all and fails
    silently: a second dock entry rather than an error.
    """
    assert _shell_assignment("QT_APPLICATION_NAME") == (
        app_runtime_mod._APPLICATION_NAME
    )


def test_the_desktop_entry_uses_that_name_for_startup_wm_class() -> None:
    """The value is written from the variable rather than typed out twice."""
    text = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "StartupWMClass=${QT_APPLICATION_NAME}" in text


def test_the_launcher_states_the_wm_class_instance_name() -> None:
    """Qt derives the instance half from the executable when this is unset.

    Inside the sandbox the executable is python3, so without this every window
    would announce itself as python3 and match no launcher at all.
    """
    text = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert 'export RESOURCE_NAME="${APP_ID}"' in text
