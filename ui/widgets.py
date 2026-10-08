"""
Reusable building blocks for tool pages:

- SourceSection  — drag & drop list of files/folders with Add/Remove/Clear buttons
- OutputSection  — "same folder / this folder", overwrite, open-when-done
- ToolPage       — base class for every tool: title, run bar, log, background worker
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPainter, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QRadioButton, QVBoxLayout, QWidget,
)

PATH_ROLE = Qt.ItemDataRole.UserRole
META_ROLE = Qt.ItemDataRole.UserRole + 1


# ====================================================================== drop list

class DropList(QListWidget):
    """List that accepts dragged files/folders and shows a hint when empty."""

    pathsDropped = Signal(list)
    itemsRemoved = Signal()

    def __init__(self, hint: str, parent=None):
        super().__init__(parent)
        self.hint = hint
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self._hover = False
        self._restyle()
        QShortcut(QKeySequence.StandardKey.Delete, self, self.remove_selected)

    def _restyle(self):
        color = "#2d7ff9" if self._hover else "#9aa4b2"
        self.setStyleSheet(
            f"QListWidget {{ border: 2px dashed {color}; border-radius: 8px; padding: 4px; }}"
        )

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover = True
            self._restyle()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._hover = False
        self._restyle()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        self._hover = False
        self._restyle()
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.pathsDropped.emit(paths)

    def remove_selected(self):
        for item in self.selectedItems():
            self.takeItem(self.row(item))
        self.itemsRemoved.emit()

    def paintEvent(self, e):
        super().paintEvent(e)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.hint)
            painter.end()


# ====================================================================== sources

class SourceSection(QGroupBox):
    """
    Drop zone + buttons. Two modes:
      expand_folders=True  -> dropped folders are expanded into their PDF files
      expand_folders=False -> folders stay as one entry (the tool scans them itself)
    `describe(path)` returns (display text, meta) for each entry, or raises to reject it.
    any_file=True accepts every file type (not only PDFs).
    """

    changed = Signal()

    def __init__(self, title: str, hint: str, settings: QSettings, key: str,
                 describe: Callable[[Path], tuple[str, object]],
                 expand_folders: bool, log: Callable[[str], None], any_file: bool = False):
        super().__init__(title)
        self.settings, self.key = settings, key
        self.describe, self.expand_folders, self.log = describe, expand_folders, log
        self.any_file = any_file

        self.body = lay = QVBoxLayout(self)
        self.list = DropList(hint)
        self.list.setMinimumHeight(130)
        self.list.pathsDropped.connect(self.add_paths)
        self.list.itemsRemoved.connect(self.changed)
        lay.addWidget(self.list)

        row = QHBoxLayout()
        b_files = QPushButton("Add files…")
        b_files.clicked.connect(self._pick_files)
        b_folder = QPushButton("Add folder…")
        b_folder.clicked.connect(self._pick_folder)
        self.recursive_cb = QCheckBox("Include subfolders")
        self.recursive_cb.setChecked(settings.value(f"{key}/recursive", False, type=bool))
        self.recursive_cb.toggled.connect(self.changed)
        b_remove = QPushButton("Remove selected")
        b_remove.clicked.connect(self.list.remove_selected)
        b_clear = QPushButton("Clear")
        b_clear.clicked.connect(self.clear)
        for w in (b_files, b_folder, self.recursive_cb):
            row.addWidget(w)
        row.addStretch()
        row.addWidget(b_remove)
        row.addWidget(b_clear)
        lay.addLayout(row)

        self.summary = QLabel()
        lay.addWidget(self.summary)

    # -- public
    @property
    def recursive(self) -> bool:
        return self.recursive_cb.isChecked()

    def paths(self) -> list[Path]:
        return [Path(self.list.item(i).data(PATH_ROLE)) for i in range(self.list.count())]

    def entries(self) -> list[tuple[Path, object]]:
        return [(Path(self.list.item(i).data(PATH_ROLE)), self.list.item(i).data(META_ROLE))
                for i in range(self.list.count())]

    def clear(self):
        self.list.clear()
        self.changed.emit()

    def add_paths(self, paths: list[str]):
        from core.common import collect_pdfs, is_pdf

        if self.expand_folders:
            candidates = collect_pdfs(paths, recursive=self.recursive)
            if not candidates:
                self.log("No PDF files found in what was added.")
        else:
            candidates = [Path(p) for p in paths
                          if Path(p).is_dir() or is_pdf(Path(p)) or (self.any_file and Path(p).is_file())]

        existing = {str(p).lower() for p in self.paths()}
        added = 0
        for p in candidates:
            key = str(p.resolve())
            if key.lower() in existing:
                continue
            try:
                text, meta = self.describe(p)
            except Exception as e:
                self.log(f"✖ Cannot read {p.name}: {e}")
                continue
            item = QListWidgetItem(text)
            item.setToolTip(key)
            item.setData(PATH_ROLE, key)
            item.setData(META_ROLE, meta)
            self.list.addItem(item)
            existing.add(key.lower())
            added += 1
        if added:
            self.log(f"Added {added} item(s).")
        self.changed.emit()

    def replace_paths(self, mapping: dict[str, str]):
        """Point list entries at new paths after their files were renamed."""
        for i in range(self.list.count()):
            item = self.list.item(i)
            new = mapping.get(item.data(PATH_ROLE))
            if new:
                item.setData(PATH_ROLE, new)
                item.setToolTip(new)
                try:
                    text, meta = self.describe(Path(new))
                    item.setText(text)
                    item.setData(META_ROLE, meta)
                except Exception:
                    pass

    def set_summary(self, text: str):
        self.summary.setText(text)

    def save_settings(self):
        self.settings.setValue(f"{self.key}/recursive", self.recursive)

    # -- dialogs
    def _last_dir(self) -> str:
        return self.settings.value("last_input_dir", "")

    def _pick_files(self):
        file_filter = "All files (*)" if self.any_file else "PDF files (*.pdf)"
        files, _ = QFileDialog.getOpenFileNames(self, "Choose files", self._last_dir(), file_filter)
        if files:
            self.settings.setValue("last_input_dir", str(Path(files[0]).parent))
            self.add_paths(files)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", self._last_dir())
        if folder:
            self.settings.setValue("last_input_dir", folder)
            self.add_paths([folder])


# ====================================================================== output

class OutputSection(QGroupBox):
    """Where results go. Tool-specific options can be inserted with add_row()."""

    def __init__(self, title: str, same_label: str, settings: QSettings, key: str):
        super().__init__(title)
        self.settings, self.key = settings, key
        self.body = QVBoxLayout(self)

        self.same_rb = QRadioButton(same_label)
        self.custom_rb = QRadioButton("This folder:")
        group = QButtonGroup(self)
        group.addButton(self.same_rb)
        group.addButton(self.custom_rb)
        self.body.addWidget(self.same_rb)

        row = QHBoxLayout()
        row.addWidget(self.custom_rb)
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("Choose destination folder…")
        self.dir_edit.textEdited.connect(lambda _: self.custom_rb.setChecked(True))
        row.addWidget(self.dir_edit, stretch=1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        self.body.addLayout(row)

        self._extra_at = self.body.count()  # tool-specific rows go here
        self.overwrite_cb = QCheckBox("Overwrite existing files (otherwise add (2), (3)…)")
        self.open_cb = QCheckBox("Open output folder when done")
        self.body.addWidget(self.overwrite_cb)
        self.body.addWidget(self.open_cb)

        s = settings
        (self.custom_rb if s.value(f"{key}/custom", False, type=bool) else self.same_rb).setChecked(True)
        self.dir_edit.setText(s.value(f"{key}/dir", ""))
        self.overwrite_cb.setChecked(s.value(f"{key}/overwrite", False, type=bool))
        self.open_cb.setChecked(s.value(f"{key}/open_after", True, type=bool))

    def add_row(self, widget_or_layout):
        if isinstance(widget_or_layout, QWidget):
            self.body.insertWidget(self._extra_at, widget_or_layout)
        else:
            self.body.insertLayout(self._extra_at, widget_or_layout)
        self._extra_at += 1

    def output_dir(self) -> tuple[bool, Path | None]:
        """(ok, folder). folder=None means 'same folder as source'. Shows a warning if not ok."""
        if not self.custom_rb.isChecked():
            return True, None
        text = self.dir_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "Output", "Choose a destination folder first.")
            return False, None
        return True, Path(text)

    @property
    def overwrite(self) -> bool:
        return self.overwrite_cb.isChecked()

    @property
    def open_after(self) -> bool:
        return self.open_cb.isChecked()

    def save_settings(self):
        s, k = self.settings, self.key
        s.setValue(f"{k}/custom", self.custom_rb.isChecked())
        s.setValue(f"{k}/dir", self.dir_edit.text())
        s.setValue(f"{k}/overwrite", self.overwrite)
        s.setValue(f"{k}/open_after", self.open_after)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose destination folder",
                                                  self.dir_edit.text() or "")
        if folder:
            self.dir_edit.setText(folder)
            self.custom_rb.setChecked(True)


# ====================================================================== worker

class TaskWorker(QObject):
    """Runs fn(worker) in a background thread. fn reports via worker.step / worker.say."""

    progress = Signal(int, int)
    log = Signal(str)
    finished = Signal(object)

    def __init__(self, fn: Callable[["TaskWorker"], object]):
        super().__init__()
        self.fn = fn
        self._stop = False

    def cancel(self):
        self._stop = True

    def stopped(self) -> bool:
        return self._stop

    def step(self, done: int, total: int):
        self.progress.emit(done, total)

    def say(self, text: str):
        self.log.emit(text)

    def run(self):
        try:
            result = self.fn(self)
        except Exception as e:
            self.say(f"✖ Unexpected error: {e}")
            result = None
        if self._stop:
            self.say("Cancelled.")
        self.finished.emit(result)


# ====================================================================== page base

class ToolPage(QWidget):
    """
    Base class for one tool in the sidebar.

    Subclass it, set TITLE / ICON / DESCRIPTION, build your sections in
    build(), and call self.run_task(fn, total) when the user clicks the button.
    Then add the class to TOOLS in app.py.
    """

    TITLE = "Tool"
    ICON = "•"
    DESCRIPTION = ""
    RUN_LABEL = "Run"
    KEY = "tool"   # settings prefix, must be unique per tool

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(16, 12, 16, 12)
        title = QLabel(f"{self.ICON}  {self.TITLE}")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.root.addWidget(title)
        if self.DESCRIPTION:
            desc = QLabel(self.DESCRIPTION)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: gray; margin-bottom: 6px;")
            self.root.addWidget(desc)

        # log is created first so build() can already write to it
        self.log_box = QPlainTextEdit(readOnly=True)
        self.log_box.setMaximumHeight(110)
        self.log_box.setPlaceholderText("Log")

        self.build()

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setValue(0)
        row.addWidget(self.progress, stretch=1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        row.addWidget(self.cancel_btn)
        self.run_btn = QPushButton(self.RUN_LABEL)
        self.run_btn.setMinimumSize(150, 36)
        self.run_btn.setStyleSheet("font-weight: bold;")
        self.run_btn.clicked.connect(self.start)
        row.addWidget(self.run_btn)
        self.root.addLayout(row)
        self.root.addWidget(self.log_box)

    # -- to override
    def build(self):
        """Add the tool's sections to self.root."""

    def start(self):
        """Validate input and call self.run_task(...)."""

    def on_finished(self, result):
        """Called on the UI thread when the task is done."""

    def save_settings(self):
        """Persist tool options."""

    # -- helpers
    def log(self, text: str):
        self.log_box.appendPlainText(text)

    @property
    def busy(self) -> bool:
        return self._worker is not None

    def run_task(self, fn: Callable[[TaskWorker], object], total: int):
        self.save_settings()
        self.progress.setMaximum(max(total, 1))
        self.progress.setValue(0)
        self._set_running(True)

        self._thread = QThread(self)
        self._worker = TaskWorker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        # connect to methods (not lambdas) so updates run on the UI thread
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self.log)
        self._worker.finished.connect(self._on_done)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def open_folder(self, folder: Path | str | None):
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def cancel(self):
        if self._worker:
            self._worker.cancel()

    def shutdown(self):
        self.cancel()
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self.save_settings()

    def _on_progress(self, done: int, total: int):
        self.progress.setValue(done)

    def _on_done(self, result):
        self._worker = None
        self._thread = None
        self._set_running(False)
        self.on_finished(result)

    def _set_running(self, running: bool):
        self.run_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
