"""The two palettes the setup program offers.

Both are built around the Elite Dangerous HUD: amber on near-black, which is
what the game itself looks like and what a commander expects a tool for it to
look like. The dark theme is the authentic one; the light theme is the same
amber over warm paper, darkened enough to stay legible on white.

Every colour is a named field on one value rather than a literal repeated
through a stylesheet, so the two themes are the same shape and a colour appears
exactly once.

Two rules the previous palettes broke are now structural:

- **One hue per button.** Each action's gradient runs between two shades of a
  single colour. The earlier palettes ran purple to orange and blue to orange
  across one small pill, which is what made the window look garish.
- **The accent is never a border.** Focus and hover are shown in a contrasting
  green and disabled in red, because an amber ring on an amber button cannot be
  seen at all.

British spelling is used in comments. No em dashes appear anywhere.
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
    danger_hover_bg: str
    danger_pressed_bg: str
    # The focus ring, in the two states that draw one. Deliberately not the
    # accent: a ring has to contrast with the fill it sits on.
    focus_ring: str
    disabled_ring: str
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


# The Elite Dangerous HUD amber, plus the two shades either side that give
# a button depth without introducing a second hue.
_ED_AMBER = "#ff7100"
_ED_AMBER_BRIGHT = "#ff8f33"
_ED_AMBER_DEEP = "#d95c00"

DARK_THEME = Theme(
    name=DARK,
    window_bg="#0b0c0e",
    chrome_bg="#15171a",
    border="#2c2a26",
    base_bg="#101215",
    text="#efe6d9",
    title_text=_ED_AMBER,
    body_text="#a89b8a",
    accent=_ED_AMBER,
    # Near-black text on amber, which is the HUD's own contrast.
    primary_text="#140c02",
    primary_start=_ED_AMBER_BRIGHT,
    primary_end=_ED_AMBER,
    primary_hover_start="#ffa557",
    primary_hover_end=_ED_AMBER_BRIGHT,
    primary_pressed_start=_ED_AMBER,
    primary_pressed_end=_ED_AMBER_DEEP,
    # Repair is the same hue held back, so the primary action still leads.
    repair_text="#140c02",
    repair_start="#c98a2e",
    repair_end="#b0741f",
    repair_hover_start="#dea044",
    repair_hover_end="#c98a2e",
    repair_pressed_start="#b0741f",
    repair_pressed_end="#96611a",
    danger_text="#e8674a",
    danger_hover_bg="rgba(232, 103, 74, 0.10)",
    danger_pressed_bg="rgba(232, 103, 74, 0.20)",
    focus_ring="#5ad07a",
    disabled_ring="#8c3a26",
    toggle_bg="#15171a",
    toggle_border="#2c2a26",
    toggle_text="#efe6d9",
    toggle_checked_bg="#22201c",
    toggle_checked_border=_ED_AMBER,
    indicator_bg="#101215",
    indicator_hover_bg="#22201c",
    indicator_checked_bg=_ED_AMBER,
    progress_chunk=_ED_AMBER,
    dialog_bg="#0b0c0e",
    dialog_button_bg="#15171a",
    dialog_button_hover_bg="#22201c",
    dialog_button_pressed_bg="#2c2a26",
)

# The same amber, taken darker so it carries enough contrast against paper.
_ED_AMBER_INK = "#b8500a"
_ED_AMBER_INK_DEEP = "#94400a"

LIGHT_THEME = Theme(
    name=LIGHT,
    window_bg="#f7f3ec",
    chrome_bg="#efe7db",
    border="#d8cbb8",
    base_bg="#fffdf9",
    text="#1c1710",
    title_text=_ED_AMBER_INK,
    body_text="#4a4034",
    accent=_ED_AMBER_INK,
    primary_text="#fffdf9",
    primary_start="#d9660d",
    primary_end=_ED_AMBER_INK,
    primary_hover_start="#e8761c",
    primary_hover_end="#d9660d",
    primary_pressed_start=_ED_AMBER_INK,
    primary_pressed_end=_ED_AMBER_INK_DEEP,
    repair_text="#fffdf9",
    repair_start="#a8823c",
    repair_end="#8e6c2c",
    repair_hover_start="#bd964c",
    repair_hover_end="#a8823c",
    repair_pressed_start="#8e6c2c",
    repair_pressed_end="#775a23",
    danger_text="#b23a1c",
    danger_hover_bg="rgba(178, 58, 28, 0.08)",
    danger_pressed_bg="rgba(178, 58, 28, 0.16)",
    focus_ring="#1f7a3d",
    disabled_ring="#c2907f",
    toggle_bg="#efe7db",
    toggle_border="#d8cbb8",
    toggle_text="#1c1710",
    toggle_checked_bg="#e4d7c2",
    toggle_checked_border=_ED_AMBER_INK,
    indicator_bg="#fffdf9",
    indicator_hover_bg="#efe7db",
    indicator_checked_bg=_ED_AMBER_INK,
    progress_chunk=_ED_AMBER_INK,
    dialog_bg="#fffdf9",
    dialog_button_bg="#f7f3ec",
    dialog_button_hover_bg="#efe7db",
    dialog_button_pressed_bg="#e4d7c2",
)

THEMES = {DARK: DARK_THEME, LIGHT: LIGHT_THEME}


def theme_for(name: str) -> Theme:
    """Return the named theme, falling back to dark for anything unknown."""
    return THEMES.get(name, DARK_THEME)
