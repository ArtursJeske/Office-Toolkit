#!/usr/bin/env python3
"""
Office Toolkit — desktop app with a sidebar of office tools.

Run:      python app.py          (or double-click run.bat on Windows)
Requires: pip install -r requirements.txt

ADDING A NEW TOOL
    1. Put the PDF logic in core/<tool>.py
    2. Make ui/<tool>_page.py with a ToolPage subclass (see merge_page.py)
    3. Add the class to TOOLS below
"""

from __future__ import annotations

import sys
from pathlib import Path

# make "core" and "ui" importable no matter where the app is started from
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ui.merge_page import MergePage
from ui.rename_page import RenamePage
from ui.split_page import SplitPage

APP_NAME = "Office Toolkit"
APP_VERSION = "2.2"
APP_AUTHOR = "Artūrs Jeske"
APP_YEAR = 2026

# The sidebar, in order. Add new tools here.
TOOLS = [
    SplitPage,
    MergePage,
    RenamePage,
]

SETTINGS_ORG, SETTINGS_APP = "OfficeToolkit", "OfficeToolkit"


def migrate_old_settings(settings: QSettings):
    """Carry over settings saved under the app's old name ("PDF Tools")."""
    if settings.allKeys():
        return
    old = QSettings("DarbaScripti", "PDFTools")
    for key in old.allKeys():
        settings.setValue(key, old.value(key))


SIDEBAR_STYLE = """
QListWidget { border: none; background: palette(window); font-size: 14px; outline: 0; }
QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 2px 6px; }
QListWidget::item:selected { background: #2d7ff9; color: white; }
QListWidget::item:hover:!selected { background: palette(midlight); }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        migrate_old_settings(self.settings)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # sidebar
        side = QWidget()
        side.setFixedWidth(210)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 14, 0, 10)
        logo = QLabel(f"  {APP_NAME}")
        logo.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px 10px 10px 10px;")
        side_lay.addWidget(logo)
        self.nav = QListWidget()
        self.nav.setStyleSheet(SIDEBAR_STYLE)
        self.nav.setIconSize(QSize(0, 0))
        side_lay.addWidget(self.nav, stretch=1)
        footer = QLabel(f"v{APP_VERSION}<br>© {APP_YEAR} {APP_AUTHOR}")
        footer.setStyleSheet("color: gray; padding-left: 20px; font-size: 11px;")
        footer.setToolTip(f"{APP_NAME} {APP_VERSION} — developed by {APP_AUTHOR}, {APP_YEAR}")
        side_lay.addWidget(footer)
        layout.addWidget(side)

        line = QWidget()
        line.setFixedWidth(1)
        line.setStyleSheet("background: palette(mid);")
        layout.addWidget(line)

        # pages
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, stretch=1)
        self.pages = []
        for n, cls in enumerate(TOOLS, start=1):
            page = cls(self.settings)
            self.pages.append(page)
            self.stack.addWidget(page)
            item = QListWidgetItem(f"{n}.  {cls.ICON}  {cls.TITLE.split('  ')[0]}")
            item.setToolTip(cls.DESCRIPTION)
            self.nav.addItem(item)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        last = self.settings.value("last_tool", 0, type=int)
        self.nav.setCurrentRow(last if 0 <= last < len(TOOLS) else 0)

        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(1000, 780)

    def current_page(self):
        return self.pages[self.stack.currentIndex()]

    def closeEvent(self, e):
        for page in self.pages:
            page.shutdown()
        self.settings.setValue("last_tool", self.nav.currentRow())
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    # files dropped onto the .exe / passed on the command line go to the current tool
    if len(sys.argv) > 1:
        window.current_page().sources.add_paths(sys.argv[1:])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
