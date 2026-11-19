"""Вкладка «Реестр» (Windows) / «Система» (Linux): поиск и исправление проблем."""
from __future__ import annotations

import time
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSplitter, QVBoxLayout, QWidget

from ..core.config import backup_dir
from ..core.i18n import L
from ..core.platform import NAME
from ..tools import linux_issues, registry_cleaner
from ..tools.issues import RISK_CAUTION, RISK_RISKY, Issue, IssueCtx, recommended_ids, scan_all
from . import common
from .common import ProgressRow, ask, cell, info, label, make_table
from .ribbon import Ribbon
from .theme import palette
from .workers import TaskRunner


class IssuesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        self.runner = TaskRunner(self)
        self.windows = NAME == "windows"
        self.categories = registry_cleaner.CATEGORIES if self.windows else linux_issues.CATEGORIES
        self.issues: List[Issue] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 10)
        split = QSplitter()
        outer.addWidget(split, 1)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(label(L("Registry cleaner", "Чистильщик реестра") if self.windows
                           else L("System issues", "Системные проблемы"), "h2"))
        self.cats = QListWidget()
        tags = {RISK_CAUTION: L("caution", "осторожно"), RISK_RISKY: L("risky", "риск")}
        tips = {RISK_CAUTION: L("Can affect file associations or leave leftovers. Review the results before fixing.",
                                "Может затронуть ассоциации файлов. Проверьте результаты перед исправлением."),
                RISK_RISKY: L("Removing these entries can break working programs or services. Not recommended.",
                              "Удаление этих записей может сломать работающие программы или службы. Не рекомендуется.")}
        for c in self.categories:
            it = QListWidgetItem(str(c.name) + (f"   · {tags[c.risk]}" if c.risk in tags else ""))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if c.recommended else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            if c.risk in tips:
                it.setToolTip(tips[c.risk])
                it.setForeground(QBrush(QColor(palette(win.theme)["danger" if c.risk == RISK_RISKY else "warn"])))
            self.cats.addItem(it)
        ll.addWidget(self.cats)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.summary = label(L("Press “Scan” to look for problems.", "Нажмите «Сканировать», чтобы найти проблемы."), "muted")
        rl.addWidget(self.summary)
        self.table = make_table(["", L("Problem", "Проблема"), L("Data", "Данные"),
                                 L("Registry key", "Ключ реестра") if self.windows else L("Location", "Расположение")], 2)
        self.table.horizontalHeader().setSectionResizeMode(1, common.QHeaderView.ResizeMode.ResizeToContents)
        rl.addWidget(self.table, 1)
        split.addWidget(right)
        split.setSizes([280, 720])
        self.progress = ProgressRow()
        outer.addWidget(self.progress)

    def build_ribbon(self) -> Ribbon:
        r = Ribbon(self.win.theme)
        r.add_group(L("Scan", "Проверка"), [
            r.button("scan", L("Scan for issues", "Сканировать"), "scan", self.scan),
            r.button("fix", L("Fix selected", "Исправить"), "fix", self.fix, primary=True),
            r.button("stop", L("Stop", "Стоп"), "stop", self.runner.stop),
        ])
        r.add_group(L("Categories", "Категории"), [
            r.button("rec", L("Recommended", "Рекомендуемые"), "shield", self._select_recommended,
                     tip=L("Tick only the safe categories", "Отметить только безопасные категории")),
            r.button("cat_all", L("All", "Все"), "checkall", lambda: self._set_cats(None)),
            r.button("cat_none", L("None", "Ничего"), "uncheck", lambda: self._set_cats(set())),
        ])
        r.add_group(L("Results", "Результаты"), [
            r.button("all", L("Select all", "Выбрать всё"), "checkall", lambda: self._check_rows(True)),
            r.button("none", L("Select none", "Снять всё"), "uncheck", lambda: self._check_rows(False)),
        ])
        r.add_group(L("Backups", "Резервные копии"), [
            r.button("backups", L("Open backups", "Папка копий"), "folder", lambda: common.open_path(str(backup_dir()))),
        ])
        self.rb = r.buttons
        self.rb["fix"].setEnabled(False)
        self.rb["stop"].setEnabled(False)
        return r

    def _set_cats(self, ids) -> None:
        """ids=None — все категории; иначе только перечисленные."""
        for i in range(self.cats.count()):
            it = self.cats.item(i)
            on = ids is None or it.data(Qt.ItemDataRole.UserRole) in ids
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _select_recommended(self) -> None:
        self._set_cats(recommended_ids(self.categories))

    def _check_rows(self, on: bool) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _selected_cats(self) -> set:
        return {self.cats.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.cats.count())
                if self.cats.item(i).checkState() == Qt.CheckState.Checked}

    def scan(self) -> None:
        if self.runner.busy:
            return
        sel = self._selected_cats()
        self.rb["scan"].setEnabled(False)
        self.rb["fix"].setEnabled(False)
        self.rb["stop"].setEnabled(True)

        def work(w):
            ctx = self.win.make_ctx()
            ictx = IssueCtx(ctx.registry, ctx.env, ctx.home, ctx.platform, w.cancel_event)
            return scan_all(self.categories, ictx, sel, lambda t, i, n: w.report(t, i, n))

        def done(issues):
            self.rb["scan"].setEnabled(True)
            self.rb["stop"].setEnabled(False)
            self.progress.finish("")
            if issues is None:
                return
            self.issues = issues
            self._fill()

        self.runner.start(work, done, self._fail, lambda t, i, n: self.progress.update_progress(t, i, n))

    def _fill(self) -> None:
        self.table.setRowCount(0)
        names = {c.id: str(c.name) for c in self.categories}
        safe = recommended_ids(self.categories)
        for n, i in enumerate(self.issues):
            self.table.insertRow(n)
            # проблемы из «осторожных/рискованных» категорий по умолчанию не отмечаются
            self.table.setItem(n, 0, cell("", checkable=True, checked=i.checked and i.category in safe, data=n))
            self.table.setItem(n, 1, cell(i.problem, tooltip=names.get(i.category, "")))
            self.table.setItem(n, 2, cell(i.data))
            self.table.setItem(n, 3, cell(i.location + (f"  [{i.value_name}]" if i.value_name else "")))
        count = len(self.issues)
        self.summary.setText(L("Found {n} problems.", "Найдено проблем: {n}.").format(n=count) if count
                             else L("No problems found.", "Проблем не найдено."))
        self.rb["fix"].setEnabled(bool(count))

    def fix(self) -> None:
        todo = [self.issues[self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        todo = [i for i in todo if i.kind != "error"]
        if not todo:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        risky = {c.id for c in self.categories if not c.recommended}
        warn = L("\n\nWARNING: the selection includes non-recommended categories. Removing these entries can break programs.",
                 "\n\nВНИМАНИЕ: выбраны нерекомендуемые категории. Удаление этих записей может сломать программы.") \
            if any(i.category in risky for i in todo) else ""
        if self.windows:
            backup = str(backup_dir() / f"registry-{stamp}.reg")
            msg = L("A backup of the affected keys will be saved to:\n{p}\n\nFix {n} problems?",
                    "Резервная копия затронутых ключей будет сохранена в:\n{p}\n\nИсправить проблем: {n}?").format(p=backup, n=len(todo))
        else:
            backup = str(backup_dir() / f"system-{stamp}")
            msg = L("Changed files will be copied to:\n{p}\n\nFix {n} problems?",
                    "Изменяемые файлы будут скопированы в:\n{p}\n\nИсправить проблем: {n}?").format(p=backup, n=len(todo))
        if not ask(self, L("Fix selected", "Исправление"), msg + warn, L("Fix", "Исправить")):
            return
        ctx = self.win.make_ctx()
        if self.windows:
            fixed, errors = registry_cleaner.fix(todo, ctx.registry, backup) if ctx.registry else (0, ["registry unavailable"])
        else:
            fixed, errors = linux_issues.fix(todo, backup)
        text = L("Fixed: {n}.", "Исправлено: {n}.").format(n=fixed)
        if errors:
            text += "\n" + L("Errors:", "Ошибки:") + "\n" + "\n".join(errors[:10])
        info(self, L("Done", "Готово"), text, bool(errors))
        self.win.set_status(text.splitlines()[0])
        self.scan()

    def _fail(self, msg: str) -> None:
        self.rb["scan"].setEnabled(True)
        self.rb["stop"].setEnabled(False)
        self.progress.finish(msg)
        info(self, L("Error", "Ошибка"), msg, True)
