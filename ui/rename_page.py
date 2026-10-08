"""Tool 3: batch-rename files in a folder with a list of rules + live preview + undo."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from core import rename
from core.rename import OPERATIONS, NUMERIC_OPS, Rule
from ui.widgets import SourceSection, TaskWorker, ToolPage

OK_COLOR = QColor("#1a7f37")
WARN_COLOR = QColor("#c25e00")
GRAY = QColor("#8a8f98")


class RenamePage(ToolPage):
    TITLE = "File Renamer"
    ICON = "✎"
    DESCRIPTION = ("Renames all files in a folder with rules: add or remove a prefix/suffix, "
                   "insert or remove text before/after some text, replace text and more. "
                   "Rules run from top to bottom. Check the preview — nothing changes until you "
                   "click “Rename files”, and the last rename can be undone.")
    RUN_LABEL = "Rename files"
    KEY = "rename"
    confirm = True  # ask "Rename N files?" before renaming

    # ---------------------------------------------------------------- build

    def build(self):
        s = self.settings
        self.plans: list[rename.Plan] = []
        self.rules: list[Rule] = self._load_rules()
        self.log_box.setMaximumHeight(64)

        # 1. files
        self.sources = SourceSection(
            "1. Folder (or files)", "Drag & drop a folder (or single files) here",
            s, self.KEY, describe=self._describe, expand_folders=False, log=self.log, any_file=True,
        )
        self.sources.list.setMinimumHeight(48)
        self.sources.list.setMaximumHeight(64)
        row = QHBoxLayout()
        row.addWidget(QLabel("File types:"))
        self.types_edit = QLineEdit(s.value(f"{self.KEY}/types", "*"))
        self.types_edit.setMaximumWidth(220)
        row.addWidget(self.types_edit)
        hint = QLabel("e.g.  *.pdf   or   *.pdf; *.docx      ( * = all files )")
        hint.setStyleSheet("color: gray;")
        row.addWidget(hint)
        row.addStretch()
        self.sources.body.addLayout(row)
        self.sources.changed.connect(self.refresh_preview)
        self.types_edit.textChanged.connect(self.refresh_preview)
        self.root.addWidget(self.sources)

        # 2. rules
        box = QGroupBox("2. Rules — applied from top to bottom")
        v = QVBoxLayout(box)

        ed = QHBoxLayout()
        self.op_combo = QComboBox()
        for key, (label, *_rest) in OPERATIONS.items():
            self.op_combo.addItem(label, key)
        ed.addWidget(self.op_combo)
        self.a_label, self.a_edit = QLabel(), QLineEdit()
        self.b_label, self.b_edit = QLabel(), QLineEdit()
        for lbl, edit in ((self.a_label, self.a_edit), (self.b_label, self.b_edit)):
            ed.addWidget(lbl)
            ed.addWidget(edit, stretch=1)
            edit.returnPressed.connect(self._add_rule)
        self.case_cb = QCheckBox("Match case")
        ed.addWidget(self.case_cb)
        add_btn = QPushButton("Add rule")
        add_btn.setStyleSheet("font-weight: bold;")
        add_btn.clicked.connect(self._add_rule)
        ed.addWidget(add_btn)
        self.update_btn = QPushButton("Update selected")
        self.update_btn.clicked.connect(self._update_rule)
        ed.addWidget(self.update_btn)
        v.addLayout(ed)

        lst = QHBoxLayout()
        self.rule_list = QListWidget()
        self.rule_list.setMaximumHeight(110)
        self.rule_list.setMinimumHeight(70)
        self.rule_list.itemChanged.connect(self._rule_toggled)
        self.rule_list.currentRowChanged.connect(self._rule_selected)
        lst.addWidget(self.rule_list, stretch=1)
        btns = QVBoxLayout()
        for text, slot in (("▲  Up", lambda: self._move(-1)), ("▼  Down", lambda: self._move(1)),
                           ("Remove", self._remove_rule), ("Clear all", self._clear_rules)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch()
        lst.addLayout(btns)
        v.addLayout(lst)
        self.root.addWidget(box)

        self.op_combo.currentIndexChanged.connect(self._op_changed)
        self._int_validator = QIntValidator(1, 999, self)
        self._op_changed()

        # 3. preview
        box = QGroupBox("3. Preview")
        v = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Current name", "New name", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(120)
        v.addWidget(self.table)
        foot = QHBoxLayout()
        self.preview_summary = QLabel()
        foot.addWidget(self.preview_summary)
        foot.addStretch()
        self.only_changed_cb = QCheckBox("Show only changed")
        self.only_changed_cb.setChecked(s.value(f"{self.KEY}/only_changed", False, type=bool))
        self.only_changed_cb.toggled.connect(self.refresh_preview)
        foot.addWidget(self.only_changed_cb)
        self.undo_btn = QPushButton("↶  Undo last rename")
        self.undo_btn.clicked.connect(self._undo)
        foot.addWidget(self.undo_btn)
        v.addLayout(foot)
        self.root.addWidget(box, stretch=1)

        self._rebuild_rule_list()
        self._update_undo_btn()
        self.refresh_preview()

    # ---------------------------------------------------------------- sources

    @staticmethod
    def _describe(p: Path):
        if p.is_dir():
            n = sum(1 for f in p.iterdir() if f.is_file())
            return f"📁  {p}   —   {n} file(s)", None
        return f"📄  {p.name}", None

    # ---------------------------------------------------------------- rule editor

    def _op_changed(self):
        key = self.op_combo.currentData()
        _label, fa, fb, uses_case = OPERATIONS[key]
        for lbl, edit, field in ((self.a_label, self.a_edit, fa), (self.b_label, self.b_edit, fb)):
            lbl.setVisible(bool(field))
            edit.setVisible(bool(field))
            if field:
                lbl.setText(field + ":")
        self.case_cb.setVisible(uses_case)
        self.a_edit.setValidator(self._int_validator if key in NUMERIC_OPS else None)

    def _rule_from_editor(self) -> Rule | None:
        key = self.op_combo.currentData()
        _label, fa, fb, uses_case = OPERATIONS[key]
        rule = Rule(op=key, a=self.a_edit.text() if fa else "", b=self.b_edit.text() if fb else "",
                    case=self.case_cb.isChecked() if uses_case else False)
        if error := rule.validate():
            QMessageBox.warning(self, self.TITLE, error)
            return None
        return rule

    def _add_rule(self):
        rule = self._rule_from_editor()
        if rule:
            self.rules.append(rule)
            self._rules_changed(select=len(self.rules) - 1)
            self.a_edit.clear()
            self.b_edit.clear()

    def _update_rule(self):
        row = self.rule_list.currentRow()
        if row < 0:
            QMessageBox.information(self, self.TITLE, "Select a rule in the list first.")
            return
        rule = self._rule_from_editor()
        if rule:
            rule.enabled = self.rules[row].enabled
            self.rules[row] = rule
            self._rules_changed(select=row)

    def _rule_selected(self, row: int):
        self.update_btn.setEnabled(row >= 0)
        if 0 <= row < len(self.rules):
            r = self.rules[row]
            self.op_combo.setCurrentIndex(self.op_combo.findData(r.op))
            self.a_edit.setText(r.a)
            self.b_edit.setText(r.b)
            self.case_cb.setChecked(r.case)

    def _rule_toggled(self, item: QListWidgetItem):
        row = self.rule_list.row(item)
        if 0 <= row < len(self.rules):
            self.rules[row].enabled = item.checkState() == Qt.CheckState.Checked
            self._save_rules()
            self.refresh_preview()

    def _move(self, delta: int):
        row = self.rule_list.currentRow()
        new = row + delta
        if row < 0 or not 0 <= new < len(self.rules):
            return
        self.rules[row], self.rules[new] = self.rules[new], self.rules[row]
        self._rules_changed(select=new)

    def _remove_rule(self):
        row = self.rule_list.currentRow()
        if row >= 0:
            del self.rules[row]
            self._rules_changed(select=min(row, len(self.rules) - 1))

    def _clear_rules(self):
        if self.rules and QMessageBox.question(self, self.TITLE, "Remove all rules?") \
                == QMessageBox.StandardButton.Yes:
            self.rules.clear()
            self._rules_changed()

    def _rules_changed(self, select: int | None = None):
        self._rebuild_rule_list(select)
        self._save_rules()
        self.refresh_preview()

    def _rebuild_rule_list(self, select: int | None = None):
        self.rule_list.blockSignals(True)
        self.rule_list.clear()
        for i, r in enumerate(self.rules, start=1):
            item = QListWidgetItem(f"{i}.  {r.describe()}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if r.enabled else Qt.CheckState.Unchecked)
            self.rule_list.addItem(item)
        self.rule_list.blockSignals(False)
        if select is not None and select >= 0:
            self.rule_list.setCurrentRow(select)
        self.update_btn.setEnabled(self.rule_list.currentRow() >= 0)

    # ---------------------------------------------------------------- preview

    def refresh_preview(self):
        files = rename.list_files(self.sources.paths(), self.types_edit.text(), self.sources.recursive)
        self.plans = rename.plan_renames(files, [r for r in self.rules if r.enabled])
        only_changed = self.only_changed_cb.isChecked()
        rows = [p for p in self.plans if not (only_changed and p.status == "same")]

        bold = QFont()
        bold.setBold(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(rows))
        for r, plan in enumerate(rows):
            old = QTableWidgetItem(plan.src.name)
            old.setToolTip(str(plan.src))
            new = QTableWidgetItem(plan.new_name)
            status = QTableWidgetItem(rename.STATUS_TEXT[plan.status])
            if plan.status == "rename":
                new.setFont(bold)
                status.setForeground(OK_COLOR)
            elif plan.status == "same":
                new.setForeground(GRAY)
                status.setForeground(GRAY)
            else:
                status.setForeground(WARN_COLOR)
            for c, item in enumerate((old, new, status)):
                self.table.setItem(r, c, item)
        self.table.setUpdatesEnabled(True)

        n_ok = sum(p.ok for p in self.plans)
        n_same = sum(p.status == "same" for p in self.plans)
        n_bad = len(self.plans) - n_ok - n_same
        self.sources.set_summary(f"{len(files)} file(s) match" if self.sources.paths() else "Nothing added yet")
        if not self.plans:
            self.preview_summary.setText("No files")
        else:
            text = f"{n_ok} will be renamed,  {n_same} unchanged"
            if n_bad:
                text += f",  {n_bad} with problems (skipped)"
            self.preview_summary.setText(text)

    # ---------------------------------------------------------------- run / undo

    def start(self):
        self.refresh_preview()
        jobs = [p for p in self.plans if p.ok]
        if not jobs:
            QMessageBox.information(self, self.TITLE, "Nothing to rename — add a folder and some rules.")
            return
        n_bad = sum(p.status not in ("rename", "same") for p in self.plans)
        if self.confirm:
            msg = f"Rename {len(jobs)} file(s)?"
            if n_bad:
                msg += f"\n\n{n_bad} file(s) with problems will be skipped."
            msg += "\n\nYou can undo this with “Undo last rename”."
            if QMessageBox.question(self, self.TITLE, msg) != QMessageBox.StandardButton.Yes:
                return
        moves = [(p.src, p.target) for p in jobs]
        self.log(f"Renaming {len(moves)} file(s)…")
        self.run_task(self._make_task("rename", moves), len(moves))

    def _undo(self):
        log = self._load_undo()
        if not log:
            return
        moves = [(Path(new), Path(old)) for old, new in log]
        missing = [m for m in moves if not m[0].exists()]
        moves = [m for m in moves if m[0].exists()]
        msg = f"Undo the last rename ({len(moves)} file(s))?"
        if missing:
            msg += f"\n\n{len(missing)} file(s) no longer exist under the new name and will be skipped."
        if self.confirm and QMessageBox.question(self, self.TITLE, msg) != QMessageBox.StandardButton.Yes:
            return
        if not moves:
            self._save_undo([])
            self._update_undo_btn()
            return
        self.log(f"Undoing {len(moves)} rename(s)…")
        self.run_task(self._make_task("undo", moves), len(moves))

    @staticmethod
    def _make_task(kind: str, moves):
        def task(w: TaskWorker):
            done, errors = rename.rename_many(moves, on_step=w.step, should_stop=w.stopped)
            for e in errors:
                w.say(f"✖ {e}")
            return kind, done, errors
        return task

    def on_finished(self, result):
        if not result:
            return
        kind, done, errors = result
        if kind == "rename":
            self._save_undo([(str(src), str(dst)) for src, dst in done])
            msg = f"Done: {len(done)} file(s) renamed."
        else:
            self._save_undo([])
            msg = f"Undo done: {len(done)} file(s) got their old names back."
        if errors:
            msg += f" {len(errors)} problem(s) — see above."
        self.log(msg)
        self.sources.replace_paths({str(src): str(dst) for src, dst in done})
        self._update_undo_btn()
        self.refresh_preview()

    def _set_running(self, running: bool):
        super()._set_running(running)
        self.undo_btn.setEnabled(not running and bool(self._load_undo()))

    def _update_undo_btn(self):
        log = self._load_undo()
        self.undo_btn.setEnabled(bool(log))
        self.undo_btn.setToolTip(f"Last rename: {len(log)} file(s)" if log else "Nothing to undo")

    # ---------------------------------------------------------------- settings

    def _load_rules(self) -> list[Rule]:
        try:
            return [Rule.from_dict(d) for d in json.loads(self.settings.value(f"{self.KEY}/rules", "[]"))
                    if d.get("op") in OPERATIONS]
        except (ValueError, TypeError, KeyError):
            return []

    def _save_rules(self):
        self.settings.setValue(f"{self.KEY}/rules", json.dumps([r.to_dict() for r in self.rules]))

    def _load_undo(self) -> list[list[str]]:
        try:
            return json.loads(self.settings.value(f"{self.KEY}/undo", "[]"))
        except (ValueError, TypeError):
            return []

    def _save_undo(self, log):
        self.settings.setValue(f"{self.KEY}/undo", json.dumps(log))

    def save_settings(self):
        self.sources.save_settings()
        self.settings.setValue(f"{self.KEY}/types", self.types_edit.text())
        self.settings.setValue(f"{self.KEY}/only_changed", self.only_changed_cb.isChecked())
        self._save_rules()
