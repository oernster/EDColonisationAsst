"""Loading the real application icon.

The icon is always the bundled file. Painting a glyph onto a pixmap would ship a
setup program whose icon does not match the application it installs. British
spelling is used in comments. No em dashes appear anywhere.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap

from installer.ops.payload import icon_file, png_file


def app_icon() -> QIcon:
    """Return the bundled application icon, or an empty icon when absent."""
    path = icon_file()
    if path is None:
        return QIcon()
    return QIcon(str(path))


def splash_pixmap() -> QPixmap | None:
    """Return the bundled artwork for the splash, or None when absent."""
    path = png_file() or icon_file()
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    return None if pixmap.isNull() else pixmap
