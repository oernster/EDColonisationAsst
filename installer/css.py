#!/usr/bin/env python3
"""
QSS style definitions for the ED Colonisation Assistant GUI installer.

This module isolates the dark and light theme QSS strings so that the main
`installer/app.py` script can remain more focused on application logic.

Usage (from installer/app.py):

    from css import DARK_QSS, LIGHT_QSS
"""

DARK_QSS = """
QMainWindow {
    background-color: #151020;
    color: #f5f5f7;
}

QToolBar {
    background-color: #1e1630;
    border-bottom: 1px solid #2b2040;
}

QStatusBar {
    background-color: #1e1630;
    color: #f5f5f7;
    border-top: 1px solid #2b2040;
}

QLabel#titleLabel {
    color: #f5f5f7;
    font-size: 22px;
    font-weight: 600;
    padding-bottom: 4px;
}

QLabel {
    color: #d0cfe8;
}

QTextEdit {
    background-color: #1c142a;
    color: #f5f5f7;
    border: 1px solid #3a275e;
    border-radius: 8px;
}

/* Primary action buttons as rounded pills */
QPushButton#installButton,
QPushButton#repairButton,
QPushButton#uninstallButton {
    min-height: 40px;
    padding: 8px 18px;
    border-radius: 20px;
    font-weight: 600;
    border: none;
}

/* Theme toggle emoji buttons (header) – shared dark background */
QPushButton#lightThemeButton,
QPushButton#darkThemeButton {
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    padding: 0;
    border: 1px solid #3a275e;
    background-color: #1e1630;
    color: #f5f5f7;
}

/* Active (checked) theme button: brighter border/background */
QPushButton#lightThemeButton:checked,
QPushButton#darkThemeButton:checked {
    border: 1px solid #ff9f1c;
    background-color: #2a203f;
}

/* Install: strong purple -> orange gradient */
QPushButton#installButton {
    color: #f5f5f7;
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #8e6bff, stop:1 #ff9f1c);
}

QPushButton#installButton:hover {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #a389ff, stop:1 #ffb347);
}

QPushButton#installButton:pressed {
    background-color: qlineargradient(spread:pad, x1:0, y1:1, x2:1, y2:0,
                                      stop:0 #6c5ce7, stop:1 #ff851b);
}

/* Repair: slightly softer gradient */
QPushButton#repairButton {
    color: #f5f5f7;
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #5a3fd8, stop:1 #f6b26b);
}

QPushButton#repairButton:hover {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #7461e3, stop:1 #ffd28c);
}

QPushButton#repairButton:pressed {
    background-color: qlineargradient(spread:pad, x1:0, y1:1, x2:1, y2:0,
                                      stop:0 #4b32c2, stop:1 #e69138);
}

/* Uninstall: outlined orange pill on dark background */
QPushButton#uninstallButton {
    background-color: transparent;
    color: #ffb347;
    border: 1px solid #ff9f1c;
}

QPushButton#uninstallButton:hover {
    background-color: rgba(255, 159, 28, 0.08);
}

QPushButton#uninstallButton:pressed {
    background-color: rgba(255, 159, 28, 0.18);
}

"""

LIGHT_QSS = """
QMainWindow {
    background-color: #f4f7fb;
    color: #000000;
}

QToolBar {
    background-color: #e3edf9;
    border-bottom: 1px solid #c7d7f0;
}

/* Ensure toolbar buttons / title-bar style items are readable in light mode */
QToolBar QToolButton {
    color: #000000;
    background-color: transparent;
}

QToolBar QToolButton:hover {
    background-color: #e3edf9;
    color: #000000;
}

QToolBar QToolButton:pressed {
    background-color: #d0e2ff;
    color: #000000;
}

QMenuBar {
    color: #000000;
}

/* Top-level menu items */
QMenuBar::item {
    color: #000000;
    background-color: transparent;
}

/* Hover/selected for top-level menu items: light backgrounds with dark text */
QMenuBar::item:selected {
    background-color: #e3edf9;
    color: #000000;
}

QMenuBar::item:pressed {
    background-color: #d0e2ff;
    color: #000000;
}

QMenu {
    color: #000000;
}

/* Normal menu items in drop-down menus */
QMenu::item {
    color: #000000;
    background-color: transparent;
}

/* Hovered/selected menu items in drop-down menus: light backgrounds */
QMenu::item:selected {
    background-color: #e3edf9;
    color: #000000;
}

QStatusBar {
    background-color: #e3edf9;
    color: #000000;
    border-top: 1px solid #c7d7f0;
}

/* Message boxes in light mode: light background, dark text */
QMessageBox {
    background-color: #ffffff;
    color: #000000;
}

QMessageBox QLabel {
    color: #000000;
}

/* OK/Cancel/etc buttons in message boxes: light background in all states */
QMessageBox QPushButton {
    color: #000000;
    background-color: #f4f7fb;
    border: 1px solid #c7d7f0;
    padding: 4px 10px;
    border-radius: 4px;
}

QMessageBox QPushButton:hover {
    background-color: #e3edf9;
}

QMessageBox QPushButton:pressed {
    background-color: #d0e2ff;
}

QLabel#titleLabel {
    color: #000000;
    font-size: 22px;
    font-weight: 600;
    padding-bottom: 4px;
}

QLabel {
    color: #000000;
}

QCheckBox {
    color: #000000;
}

/* Checkbox indicator in light mode: light background, visible when checked */
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    background-color: #f4f7fb;
    border: 1px solid #c7d7f0;
    border-radius: 3px;
}

QCheckBox::indicator:hover {
    background-color: #e3edf9;
}

QCheckBox::indicator:checked {
    background-color: #4f8df5;
    border-color: #4f8df5;
}

QTextEdit {
    background-color: #ffffff;
    color: #000000;
    border: 1px solid #c7d7f0;
    border-radius: 8px;
}

/* Primary action buttons as rounded pills */
QPushButton#installButton,
QPushButton#repairButton,
QPushButton#uninstallButton {
    min-height: 40px;
    padding: 8px 18px;
    border-radius: 20px;
    font-weight: 600;
    border: none;
}

/* Theme toggle emoji buttons (header) – light mauve background in light mode */
QPushButton#lightThemeButton,
QPushButton#darkThemeButton {
    border-radius: 16px;
    min-width: 32px;
    min-height: 32px;
    max-width: 32px;
    max-height: 32px;
    padding: 0;
    border: 1px solid #c7b5ff;
    background-color: #efe5ff;  /* light mauve */
    color: #1f2933;
}

QPushButton#lightThemeButton:checked,
QPushButton#darkThemeButton:checked {
    border: 1px solid #8e6bff;
    background-color: #e0d0ff;
}

/* Install: light blue -> light orange gradient */
QPushButton#installButton {
    color: #ffffff;
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #4f8df5, stop:1 #ffb347);
}

QPushButton#installButton:hover {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #6da1f7, stop:1 #ffd08a);
}

QPushButton#installButton:pressed {
    background-color: qlineargradient(spread:pad, x1:0, y1:1, x2:1, y2:0,
                                      stop:0 #3478f0, stop:1 #ff9f1c);
}

/* Repair: softer blue/orange */
QPushButton#repairButton {
    color: #ffffff;
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #3b7dd8, stop:1 #f9c784);
}

QPushButton#repairButton:hover {
    background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                                      stop:0 #5a93e3, stop:1 #ffe0a8);
}

QPushButton#repairButton:pressed {
    background-color: qlineargradient(spread:pad, x1:0, y1:1, x2:1, y2:0,
                                      stop:0 #2f64b3, stop:1 #f2a654);
}

/* Uninstall: subtle outlined orange pill */
QPushButton#uninstallButton {
    background-color: transparent;
    color: #e67e22;
    border: 1px solid #f5a623;
}

QPushButton#uninstallButton:hover {
    background-color: rgba(245, 166, 35, 0.10);
}

QPushButton#uninstallButton:pressed {
    background-color: rgba(245, 166, 35, 0.20);
}

"""
