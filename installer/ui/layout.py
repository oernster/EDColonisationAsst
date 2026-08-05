"""Object names and geometry for the setup window.

The object names are shared by the widgets and the stylesheet, so the two
cannot drift apart. Every size is named here rather than written inline, so a
spacing change is one edit. British spelling is used in comments. No em dashes
appear anywhere.
"""

from __future__ import annotations

# --- object names, so the stylesheet and the widgets agree ------------------

TITLE_LABEL = "titleLabel"
SUBTITLE_LABEL = "subtitleLabel"
STATUS_LABEL = "statusLabel"
PATH_LABEL = "pathLabel"
PRIMARY_BUTTON = "installButton"
REPAIR_BUTTON = "repairButton"
UNINSTALL_BUTTON = "uninstallButton"
LIGHT_THEME_BUTTON = "lightThemeButton"
DARK_THEME_BUTTON = "darkThemeButton"
PROGRESS_BAR = "installProgress"

# --- geometry ---------------------------------------------------------------

WINDOW_WIDTH = 780
WINDOW_HEIGHT = 560
LICENCE_DIALOG_WIDTH = 520
LICENCE_DIALOG_HEIGHT = 650
CONTENT_MARGIN = 16
DIALOG_MARGIN = 16
SECTION_SPACING = 12
BUTTON_SPACING = 8
OPTION_SPACING = 2
THEME_BUTTON_SPACING = 6
THEME_BUTTON_PX = 32
ACTION_BUTTON_HEIGHT_PX = 40
PROGRESS_HEIGHT_PX = 18
BORDER_RADIUS_PX = 20
THEME_BUTTON_RADIUS_PX = 16
