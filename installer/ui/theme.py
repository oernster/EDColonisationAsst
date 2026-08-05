"""The two palettes the setup program offers.

The colours are EDCA's own and are unchanged: the dark theme's deep purple with
its orange accent, and the light theme's blue with a warm orange. What has
changed is that every colour is now a named field on one value rather than a
literal repeated through a stylesheet, so the two themes are the same shape and
a colour appears exactly once. British spelling is used in comments. No em
dashes appear anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

DARK = "dark"
LIGHT = "light"


@dataclass(frozen=True, slots=True)
class Theme:
    """Every colour one theme needs, named for the role it plays."""

    name: str
    window_bg: str
    chrome_bg: str
    border: str
    base_bg: str
    text: str
    title_text: str
    body_text: str
    accent: str
    # The primary action's gradient, in its three states.
    primary_text: str
    primary_start: str
    primary_end: str
    primary_hover_start: str
    primary_hover_end: str
    primary_pressed_start: str
    primary_pressed_end: str
    # The repair action's gradient, in its three states.
    repair_text: str
    repair_start: str
    repair_end: str
    repair_hover_start: str
    repair_hover_end: str
    repair_pressed_start: str
    repair_pressed_end: str
    # The uninstall action is an outlined pill rather than a filled one.
    danger_text: str
    danger_border: str
    danger_hover_bg: str
    danger_pressed_bg: str
    # The two emoji theme buttons in the header.
    toggle_bg: str
    toggle_border: str
    toggle_text: str
    toggle_checked_bg: str
    toggle_checked_border: str
    # Checkboxes and the progress bar.
    indicator_bg: str
    indicator_hover_bg: str
    indicator_checked_bg: str
    progress_chunk: str
    # Message boxes, which Qt paints from the stylesheet rather than the palette.
    dialog_bg: str
    dialog_button_bg: str
    dialog_button_hover_bg: str
    dialog_button_pressed_bg: str


DARK_THEME = Theme(
    name=DARK,
    window_bg="#151020",
    chrome_bg="#1e1630",
    border="#2b2040",
    base_bg="#1c142a",
    text="#f5f5f7",
    title_text="#f5f5f7",
    body_text="#d0cfe8",
    accent="#ff9f1c",
    primary_text="#f5f5f7",
    primary_start="#8e6bff",
    primary_end="#ff9f1c",
    primary_hover_start="#a389ff",
    primary_hover_end="#ffb347",
    primary_pressed_start="#6c5ce7",
    primary_pressed_end="#ff851b",
    repair_text="#f5f5f7",
    repair_start="#5a3fd8",
    repair_end="#f6b26b",
    repair_hover_start="#7461e3",
    repair_hover_end="#ffd28c",
    repair_pressed_start="#4b32c2",
    repair_pressed_end="#e69138",
    danger_text="#ffb347",
    danger_border="#ff9f1c",
    danger_hover_bg="rgba(255, 159, 28, 0.08)",
    danger_pressed_bg="rgba(255, 159, 28, 0.18)",
    toggle_bg="#1e1630",
    toggle_border="#3a275e",
    toggle_text="#f5f5f7",
    toggle_checked_bg="#2a203f",
    toggle_checked_border="#ff9f1c",
    indicator_bg="#1c142a",
    indicator_hover_bg="#2a203f",
    indicator_checked_bg="#ff9f1c",
    progress_chunk="#ff9f1c",
    dialog_bg="#151020",
    dialog_button_bg="#1e1630",
    dialog_button_hover_bg="#2a203f",
    dialog_button_pressed_bg="#3a275e",
)

LIGHT_THEME = Theme(
    name=LIGHT,
    window_bg="#f4f7fb",
    chrome_bg="#e3edf9",
    border="#c7d7f0",
    base_bg="#ffffff",
    text="#000000",
    title_text="#000000",
    body_text="#000000",
    accent="#4f8df5",
    primary_text="#ffffff",
    primary_start="#4f8df5",
    primary_end="#ffb347",
    primary_hover_start="#6da1f7",
    primary_hover_end="#ffd08a",
    primary_pressed_start="#3478f0",
    primary_pressed_end="#ff9f1c",
    repair_text="#ffffff",
    repair_start="#3b7dd8",
    repair_end="#f9c784",
    repair_hover_start="#5a93e3",
    repair_hover_end="#ffe0a8",
    repair_pressed_start="#2f64b3",
    repair_pressed_end="#f2a654",
    danger_text="#e67e22",
    danger_border="#f5a623",
    danger_hover_bg="rgba(245, 166, 35, 0.10)",
    danger_pressed_bg="rgba(245, 166, 35, 0.20)",
    toggle_bg="#efe5ff",
    toggle_border="#c7b5ff",
    toggle_text="#1f2933",
    toggle_checked_bg="#e0d0ff",
    toggle_checked_border="#8e6bff",
    indicator_bg="#f4f7fb",
    indicator_hover_bg="#e3edf9",
    indicator_checked_bg="#4f8df5",
    progress_chunk="#4f8df5",
    dialog_bg="#ffffff",
    dialog_button_bg="#f4f7fb",
    dialog_button_hover_bg="#e3edf9",
    dialog_button_pressed_bg="#d0e2ff",
)

THEMES = {DARK: DARK_THEME, LIGHT: LIGHT_THEME}


def theme_for(name: str) -> Theme:
    """Return the named theme, falling back to dark for anything unknown."""
    return THEMES.get(name, DARK_THEME)
