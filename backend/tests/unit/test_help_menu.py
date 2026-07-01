from __future__ import annotations

"""Tests for the shared tray Help menu and About dialog content.

These tests exercise [`src.runtime.help_menu`](backend/src/runtime/help_menu.py:1)
with lightweight menu fakes so that no real Qt widgets or event loops are
required. The AboutDialog widget itself is only constructed lazily when the
About action fires, which lets us substitute a recording dummy.
"""

from pathlib import Path
from typing import Any, List, Optional

import pytest

import src.runtime.help_menu as help_menu_mod


# ---------------------------------------------------------------------------
# Menu fakes (mirroring the style used in test_runtime_components.py)
# ---------------------------------------------------------------------------


class DummySignal:
    def __init__(self) -> None:
        self._callbacks: List[Any] = []

    def connect(self, cb: Any) -> None:
        self._callbacks.append(cb)

    def emit(self) -> None:
        for cb in list(self._callbacks):
            cb()


class DummyAction:
    def __init__(self, text: str) -> None:
        self.text = text
        self.triggered = DummySignal()


class DummyMenu:
    def __init__(self) -> None:
        self.actions: List[DummyAction | str] = []
        self.submenus: List[tuple[str, "DummyMenu"]] = []

    def addAction(self, text: str) -> DummyAction:  # noqa: N802
        act = DummyAction(text)
        self.actions.append(act)
        return act

    def addSeparator(self) -> None:
        self.actions.append("---")

    def addMenu(self, title: str) -> "DummyMenu":  # noqa: N802
        submenu = DummyMenu()
        self.submenus.append((title, submenu))
        return submenu


# ---------------------------------------------------------------------------
# Constants and About HTML content
# ---------------------------------------------------------------------------


def test_releases_url_points_at_github_releases() -> None:
    assert (
        help_menu_mod.RELEASES_URL
        == "https://github.com/oernster/EDColonisationAsst/releases"
    )


def test_build_about_html_contains_required_content() -> None:
    """
    The About body must carry the app identity, author, copyright year,
    licence, open source credits and the caffeine acknowledgement.
    """
    html = help_menu_mod.build_about_html("9.9.9")

    assert help_menu_mod.APP_NAME in html
    assert "9.9.9" in html
    assert help_menu_mod.APP_AUTHOR in html
    assert f"by {help_menu_mod.APP_AUTHOR}" in html
    assert "&copy;" in html
    assert help_menu_mod.COPYRIGHT_YEAR in html
    assert "LGPL-3.0" in html
    assert "Open source credits" in html
    # A representative sample of the shipped dependency credits.
    for dependency in ("PySide6", "FastAPI", "Uvicorn", "React", "Nuitka"):
        assert dependency in html
    # The sarcastic caffeine credit.
    assert "caffeine" in html
    assert "billed per mug" in html


def test_build_about_html_never_hardcodes_a_version() -> None:
    """
    The version shown must be exactly the one passed in; the canonical value
    comes from the top-level VERSION file via the package __version__.
    """
    html = help_menu_mod.build_about_html("1.2.3-test")
    assert "1.2.3-test" in html


# ---------------------------------------------------------------------------
# Icon resolution
# ---------------------------------------------------------------------------


def test_resolve_about_icon_prefers_png_then_ico(tmp_path: Path) -> None:
    png = tmp_path / "EDColonisationAsst.png"
    ico = tmp_path / "EDColonisationAsst.ico"
    png.write_bytes(b"")
    ico.write_bytes(b"")

    assert help_menu_mod.resolve_about_icon(tmp_path) == png

    png.unlink()
    assert help_menu_mod.resolve_about_icon(tmp_path) == ico

    ico.unlink()
    assert help_menu_mod.resolve_about_icon(tmp_path) is None


# ---------------------------------------------------------------------------
# Check for Updates action
# ---------------------------------------------------------------------------


def test_open_releases_page_opens_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: List[str] = []
    monkeypatch.setattr(
        help_menu_mod.webbrowser, "open", lambda url: opened.append(url)
    )

    help_menu_mod.open_releases_page()

    assert opened == [help_menu_mod.RELEASES_URL]


def test_open_releases_page_swallows_browser_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_url: str) -> None:
        raise OSError("no browser available")

    monkeypatch.setattr(help_menu_mod.webbrowser, "open", boom)

    # Must not raise.
    help_menu_mod.open_releases_page()


# ---------------------------------------------------------------------------
# add_help_menu wiring
# ---------------------------------------------------------------------------


def test_add_help_menu_creates_about_and_updates_actions() -> None:
    menu = DummyMenu()

    submenu = help_menu_mod.add_help_menu(menu, version="1.0.0")

    assert menu.submenus == [("Help", submenu)]
    action_texts = [act.text for act in submenu.actions if isinstance(act, DummyAction)]
    assert action_texts == ["About", "Check for Updates"]


def test_help_menu_check_for_updates_opens_releases_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: List[str] = []
    monkeypatch.setattr(
        help_menu_mod.webbrowser, "open", lambda url: opened.append(url)
    )

    menu = DummyMenu()
    submenu = help_menu_mod.add_help_menu(menu, version="1.0.0")

    updates_action = next(
        act
        for act in submenu.actions
        if isinstance(act, DummyAction) and act.text == "Check for Updates"
    )
    updates_action.triggered.emit()

    assert opened == [help_menu_mod.RELEASES_URL]


def test_help_menu_about_action_shows_dialog(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Triggering About must construct the dialog with the resolved version and
    icon path, then exec() it. A recording dummy stands in for the real
    Qt dialog.
    """
    created: List[dict] = []

    class DummyAboutDialog:
        def __init__(
            self,
            version: str,
            icon_path: Optional[Path] = None,
            parent: Any = None,
        ) -> None:
            self._record = {
                "version": version,
                "icon_path": icon_path,
                "parent": parent,
                "exec_called": False,
            }
            created.append(self._record)

        def exec(self) -> int:
            self._record["exec_called"] = True
            return 0

    monkeypatch.setattr(help_menu_mod, "AboutDialog", DummyAboutDialog)

    icon = tmp_path / "EDColonisationAsst.png"
    icon.write_bytes(b"")

    menu = DummyMenu()
    submenu = help_menu_mod.add_help_menu(menu, icon_path=icon, version="4.5.6")

    about_action = next(
        act
        for act in submenu.actions
        if isinstance(act, DummyAction) and act.text == "About"
    )
    about_action.triggered.emit()

    assert len(created) == 1
    assert created[0]["version"] == "4.5.6"
    assert created[0]["icon_path"] == icon
    assert created[0]["exec_called"] is True


def test_add_help_menu_defaults_to_package_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    When no explicit version is supplied, the menu resolves the package
    __version__ (which itself is loaded from the VERSION file).
    """
    from src import __version__

    captured: List[str] = []

    class DummyAboutDialog:
        def __init__(
            self,
            version: str,
            icon_path: Optional[Path] = None,
            parent: Any = None,
        ) -> None:
            captured.append(version)

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(help_menu_mod, "AboutDialog", DummyAboutDialog)

    menu = DummyMenu()
    submenu = help_menu_mod.add_help_menu(menu)

    about_action = next(
        act
        for act in submenu.actions
        if isinstance(act, DummyAction) and act.text == "About"
    )
    about_action.triggered.emit()

    assert captured == [__version__]
