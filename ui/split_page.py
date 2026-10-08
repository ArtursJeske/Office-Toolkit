"""Tool 1: split PDFs into single-page PDFs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton

from core import split
from core.common import page_count
from ui.widgets import OutputSection, SourceSection, TaskWorker, ToolPage


class SplitPage(ToolPage):
    TITLE = "PDF Splitter"
    ICON = "✂"
    DESCRIPTION = "Saves every page of a PDF as a separate PDF file."
    RUN_LABEL = "Split PDFs"
    KEY = "split"

    def build(self):
        self.sources = SourceSection(
            "1. PDF files", "Drag & drop PDF files or folders here\n\nor use the buttons below",
            self.settings, self.KEY, describe=self._describe, expand_folders=True, log=self.log,
        )
        self.sources.changed.connect(self._update_summary)
        self.root.addWidget(self.sources, stretch=3)

        self.output = OutputSection("2. Output", "Same folder as the original PDF",
                                    self.settings, self.KEY)
        s = self.settings
        self.subfolder_cb = QCheckBox("Create a subfolder for each PDF (named after the file)")
        self.subfolder_cb.setChecked(s.value(f"{self.KEY}/subfolder", True, type=bool))
        self.output.add_row(self.subfolder_cb)

        row = QHBoxLayout()
        row.addWidget(QLabel("File names:"))
        self.pattern_edit = QLineEdit(s.value(f"{self.KEY}/pattern", split.DEFAULT_PATTERN))
        row.addWidget(self.pattern_edit, stretch=1)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self.pattern_edit.setText(split.DEFAULT_PATTERN))
        row.addWidget(reset)
        self.output.add_row(row)
        hint = QLabel(split.PATTERN_HELP)
        hint.setStyleSheet("color: gray;")
        self.output.add_row(hint)
        self.root.addWidget(self.output)

        self._update_summary()

    @staticmethod
    def _describe(p: Path):
        pages = page_count(p)
        return f"{p.name}   —   {pages} page{'s' if pages != 1 else ''}", pages

    def _update_summary(self):
        entries = self.sources.entries()
        pages = sum(m for _, m in entries)
        self.sources.set_summary(
            f"{len(entries)} file(s), {pages} page(s) in total" if entries else "No files added yet")

    def save_settings(self):
        self.sources.save_settings()
        self.output.save_settings()
        self.settings.setValue(f"{self.KEY}/subfolder", self.subfolder_cb.isChecked())
        self.settings.setValue(f"{self.KEY}/pattern", self.pattern_edit.text())

    def start(self):
        jobs = self.sources.entries()
        if not jobs:
            QMessageBox.information(self, self.TITLE, "Add some PDF files first.")
            return
        ok, out_dir = self.output.output_dir()
        if not ok:
            return
        pattern = self.pattern_edit.text().strip()
        if error := split.validate_pattern(pattern):
            QMessageBox.warning(self, self.TITLE, error)
            return

        options = split.SplitOptions(output_dir=out_dir, subfolder=self.subfolder_cb.isChecked(),
                                     pattern=pattern, overwrite=self.output.overwrite)
        total = sum(pages for _, pages in jobs)
        self.log(f"Splitting {len(jobs)} file(s)…")

        def task(w: TaskWorker):
            done = files_ok = written_total = errors = 0
            first_out = None
            for path, _pages in jobs:
                if w.stopped():
                    break
                base = done
                try:
                    out, written = split.split_pdf(
                        path, options,
                        on_page=lambda i, _t, b=base: w.step(b + i, total),
                        should_stop=w.stopped,
                    )
                    done += written
                    written_total += written
                    files_ok += 1
                    first_out = first_out or out
                    w.say(f"✔ {path.name}: {written} pages → {out}")
                except Exception as e:
                    errors += 1
                    w.say(f"✖ {path.name}: {e}")
            return files_ok, written_total, errors, first_out

        self.run_task(task, total)

    def on_finished(self, result):
        if not result:
            return
        files_ok, pages, errors, first_out = result
        msg = f"Done: {files_ok} file(s) split into {pages} page PDF(s)."
        if errors:
            msg += f" {errors} file(s) failed — see above."
        self.log(msg)
        if self.output.open_after:
            self.open_folder(first_out)
