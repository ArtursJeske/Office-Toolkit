"""Tool 2: merge ENG + LV PDF pairs into one file named <name>_ENG_LV.pdf."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from core import merge
from core.common import collect_pdfs
from ui.widgets import OutputSection, SourceSection, TaskWorker, ToolPage

OK_COLOR = QColor("#1a7f37")
WARN_COLOR = QColor("#c25e00")


class MergePage(ToolPage):
    TITLE = "PDF Merger  ENG + LV"
    ICON = "⧉"
    DESCRIPTION = ("Finds English and Latvian files with the same name "
                   "(e.g. 4014-12x50.pdf and 4014-12x50_LV.pdf) and merges each pair "
                   "into one PDF: 4014-12x50_ENG_LV.pdf. The ENG and LV files can be in "
                   "two folders or in the same folder.")
    RUN_LABEL = "Merge PDFs"
    KEY = "merge"

    def build(self):
        s = self.settings
        self.pairs: list[merge.Pair] = []

        # 1. sources
        self.sources = SourceSection(
            "1. ENG and LV folders (or files)",
            "Drag & drop the ENG folder and the LV folder here\n(or one folder with both)",
            s, self.KEY, describe=self._describe, expand_folders=False, log=self.log,
        )
        self.sources.list.setMinimumHeight(80)
        self.sources.changed.connect(self.refresh_pairs)
        self.root.addWidget(self.sources, stretch=1)

        # 2. pairs preview
        box = QGroupBox("2. Matched pairs")
        lay = QVBoxLayout(box)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "ENG file", "LV file", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(150)
        lay.addWidget(self.table)
        self.pairs_summary = QLabel()
        lay.addWidget(self.pairs_summary)
        self.root.addWidget(box, stretch=3)

        # 3. settings + output
        self.output = OutputSection("3. Settings and output", "Same folder as the ENG file", s, self.KEY)

        row = QHBoxLayout()
        row.addWidget(QLabel("LV file ends with:"))
        self.lv_edit = QLineEdit(s.value(f"{self.KEY}/lv_suffix", merge.DEFAULT_LV_SUFFIX))
        self.lv_edit.setMaximumWidth(90)
        row.addWidget(self.lv_edit)
        row.addSpacing(16)
        row.addWidget(QLabel("Add to merged name:"))
        self.out_edit = QLineEdit(s.value(f"{self.KEY}/out_suffix", merge.DEFAULT_OUT_SUFFIX))
        self.out_edit.setMaximumWidth(110)
        row.addWidget(self.out_edit)
        row.addSpacing(16)
        row.addWidget(QLabel("Page order:"))
        self.order_combo = QComboBox()
        self.order_combo.addItems(["ENG first, then LV", "LV first, then ENG"])
        self.order_combo.setCurrentIndex(1 if s.value(f"{self.KEY}/lv_first", False, type=bool) else 0)
        row.addWidget(self.order_combo)
        row.addStretch()
        self.output.add_row(row)

        self.example = QLabel()
        self.example.setStyleSheet("color: gray;")
        self.output.add_row(self.example)
        self.root.addWidget(self.output)

        self.lv_edit.editingFinished.connect(self.refresh_pairs)
        self.out_edit.editingFinished.connect(self.refresh_pairs)
        self.lv_edit.textChanged.connect(self._update_example)
        self.out_edit.textChanged.connect(self._update_example)

        self._update_example()
        self.refresh_pairs()

    # ---------------------------------------------------------------- sources & pairs

    def _describe(self, p: Path):
        if p.is_dir():
            n = len(collect_pdfs([p], recursive=self.sources.recursive))
            return f"📁  {p}   —   {n} PDF file(s)", None
        return f"📄  {p.name}", None

    def _update_example(self):
        lv, out = self.lv_edit.text(), self.out_edit.text()
        self.example.setText(f"Example:  4014-12x50.pdf  +  4014-12x50{lv}.pdf   →   4014-12x50{out}.pdf")

    def refresh_pairs(self):
        lv_suffix, out_suffix = self.lv_edit.text().strip(), self.out_edit.text().strip()
        pdfs = collect_pdfs(self.sources.paths(), recursive=self.sources.recursive)
        self.pairs = merge.find_pairs(pdfs, lv_suffix, out_suffix) if lv_suffix else []

        self.sources.set_summary(f"{len(pdfs)} PDF file(s) found" if pdfs else "Nothing added yet")
        self.table.setRowCount(len(self.pairs))
        for r, pair in enumerate(self.pairs):
            cells = [
                pair.name,
                pair.eng.name if pair.eng else "—",
                pair.lv.name if pair.lv else "—",
                "✔ Ready" if pair.ok else f"⚠ {pair.problem}",
            ]
            tips = ["", str(pair.eng or ""), str(pair.lv or ""), ""]
            for c, (text, tip) in enumerate(zip(cells, tips)):
                item = QTableWidgetItem(text)
                if tip:
                    item.setToolTip(tip)
                if c == 3:
                    item.setForeground(OK_COLOR if pair.ok else WARN_COLOR)
                self.table.setItem(r, c, item)

        ready = sum(p.ok for p in self.pairs)
        problems = len(self.pairs) - ready
        text = f"{ready} pair(s) ready to merge"
        if problems:
            text += f",  {problems} without a pair (will be skipped)"
        self.pairs_summary.setText(text if self.pairs else "No pairs yet")

    # ---------------------------------------------------------------- run

    def save_settings(self):
        self.sources.save_settings()
        self.output.save_settings()
        s = self.settings
        s.setValue(f"{self.KEY}/lv_suffix", self.lv_edit.text())
        s.setValue(f"{self.KEY}/out_suffix", self.out_edit.text())
        s.setValue(f"{self.KEY}/lv_first", self.order_combo.currentIndex() == 1)

    def start(self):
        lv_suffix, out_suffix = self.lv_edit.text().strip(), self.out_edit.text().strip()
        if not lv_suffix or not out_suffix:
            QMessageBox.warning(self, self.TITLE, "Both name endings must be filled in.")
            return
        if lv_suffix.lower() == out_suffix.lower():
            QMessageBox.warning(self, self.TITLE, "The LV ending and the merged-name ending must differ.")
            return
        self.refresh_pairs()  # pick up any files added to the folders meanwhile
        jobs = [p for p in self.pairs if p.ok]
        if not jobs:
            QMessageBox.information(self, self.TITLE, "No complete ENG + LV pairs found.")
            return
        ok, out_dir = self.output.output_dir()
        if not ok:
            return

        options = merge.MergeOptions(output_dir=out_dir, out_suffix=out_suffix,
                                     lv_first=self.order_combo.currentIndex() == 1,
                                     overwrite=self.output.overwrite)
        self.log(f"Merging {len(jobs)} pair(s)…")

        def task(w: TaskWorker):
            ok_count = errors = 0
            first_out = None
            for i, pair in enumerate(jobs, start=1):
                if w.stopped():
                    break
                try:
                    target = merge.merge_pair(pair, options)
                    ok_count += 1
                    first_out = first_out or target.parent
                    w.say(f"✔ {target.name}")
                except Exception as e:
                    errors += 1
                    w.say(f"✖ {pair.name}: {e}")
                w.step(i, len(jobs))
            return ok_count, errors, first_out

        self.run_task(task, len(jobs))

    def on_finished(self, result):
        if not result:
            return
        ok_count, errors, first_out = result
        msg = f"Done: {ok_count} merged file(s) created."
        if errors:
            msg += f" {errors} failed — see above."
        self.log(msg)
        self.refresh_pairs()
        if self.output.open_after:
            self.open_folder(first_out)
