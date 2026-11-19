"""Вкладки «Очистка» (простая) и «Выбор опций» (подробная)."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QSplitter, QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..catalog import for_platform, is_checked
from ..core import engine
from ..core.engine import CleanItem, ItemResult
from ..core.i18n import L, T, human_size
from ..core.platform import NAME
from . import icons
from .common import ProgressRow, ask, card, cell, info, label, make_table
from .ribbon import Ribbon
from .theme import palette
from .workers import TaskRunner

ADMIN_TAG = lambda: L("admin", "админ")  # noqa: E731


def results_text(results: List[ItemResult]) -> str:
    lines = []
    for r in results:
        if not r.count and not r.errors:
            continue
        lines.append(f"{r.item.name}: {r.count} / {human_size(r.size)}  ->  {r.removed_count} / {human_size(r.removed_size)}")
        for e in r.errors[:20]:
            lines.append(f"    ! {e}")
    return "\n".join(lines)


# ======================================================================
class CustomPage(QWidget):
    """Дерево опций слева, результаты анализа справа."""

    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        self.runner = TaskRunner(self)
        self.results: List[ItemResult] = []
        self.cleaned = False
        self.groups, self.items = for_platform(NAME)
        self.by_id: Dict[str, CleanItem] = {i.id: i for i in self.items}
        self.view = "system"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 10)
        split = QSplitter()
        outer.addWidget(split, 1)

        # --- левая часть: деревья
        self.stack = QStackedWidget()
        self.trees = {tab: self._build_tree(tab) for tab in ("system", "apps")}
        for t in self.trees.values():
            self.stack.addWidget(t)
        split.addWidget(self.stack)

        # --- правая часть: результаты
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.summary = label(L("Choose options on the left and press “Analyze”.",
                               "Отметьте опции слева и нажмите «Анализ»."), "muted")
        rl.addWidget(self.summary)
        self.table = make_table([L("Option", "Опция"), L("Files", "Файлов"), L("Size", "Размер"), L("Status", "Статус")], 0)
        self.table.itemSelectionChanged.connect(self._show_details)
        rl.addWidget(self.table, 3)
        self.details = QListWidget()
        self.details.setAlternatingRowColors(True)
        rl.addWidget(self.details, 2)
        split.addWidget(right)
        split.setSizes([360, 640])

        self.progress = ProgressRow()
        outer.addWidget(self.progress)

    # -------------------------------------------------------------- UI
    def _build_tree(self, tab: str) -> QTreeWidget:
        t = QTreeWidget()
        t.setHeaderHidden(True)
        t.setIndentation(14)
        t.setUniformRowHeights(True)
        t.setRootIsDecorated(False)
        ctx = self.win.make_ctx()
        t.blockSignals(True)
        for g in (g for g in self.groups if g.tab == tab):
            gi = QTreeWidgetItem([str(g.name)])
            font = gi.font(0)
            font.setBold(True)
            gi.setFont(0, font)
            gi.setFlags(gi.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            gi.setData(0, Qt.ItemDataRole.UserRole, "group:" + g.id)
            t.addTopLevelItem(gi)
            for it in (i for i in self.items if i.group == g.id):
                text = str(it.name)
                if it.admin:
                    text += "   · " + ADMIN_TAG()
                li = QTreeWidgetItem([text])
                li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                li.setCheckState(0, Qt.CheckState.Checked if is_checked(it, ctx) else Qt.CheckState.Unchecked)
                li.setData(0, Qt.ItemDataRole.UserRole, it.id)
                if it.note:
                    li.setToolTip(0, str(it.note))
                if it.admin and not ctx.admin:
                    li.setForeground(0, QBrush(QColor(palette(self.win.theme)["muted"])))
                gi.addChild(li)
            gi.setExpanded(True)
        t.blockSignals(False)
        t.itemChanged.connect(self._on_changed)
        return t

    def _on_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        iid = item.data(0, Qt.ItemDataRole.UserRole)
        if iid and not str(iid).startswith("group:"):
            self.win.cfg.selected[iid] = item.checkState(0) == Qt.CheckState.Checked
            self.win.cfg.save()
            self.results = []

    def build_ribbon(self) -> Ribbon:
        r = Ribbon(self.win.theme)
        a = r.button("analyze", L("Analyze", "Анализ"), "search", self.analyze, tip=L("Find what can be removed", "Найти, что можно удалить"))
        run = r.button("run", L("Run Cleaner", "Очистить"), "broom", self.run_clean, primary=True)
        stop = r.button("stop", L("Stop", "Стоп"), "stop", self.stop)
        r.add_group(L("Cleaning", "Очистка"), [a, run, stop])
        r.add_group(L("Selection", "Выбор"), [
            r.button("all", L("Select all", "Выбрать всё"), "checkall", lambda: self._set_all(True)),
            r.button("none", L("Select none", "Снять всё"), "uncheck", lambda: self._set_all(False)),
            r.button("def", L("Defaults", "По умолчанию"), "reset", self._defaults),
        ])
        sys_name = L("Windows", "Windows") if NAME == "windows" else L("System", "Система")
        vs = r.button("v_sys", sys_name, "system", lambda: self.set_view("system"))
        va = r.button("v_apps", L("Applications", "Приложения"), "apps", lambda: self.set_view("apps"))
        r.exclusive([vs, va])
        vs.setChecked(True)
        r.add_group(L("View", "Вид"), [vs, va])
        r.add_group(L("Report", "Отчёт"), [r.button("save", L("Save report", "Сохранить отчёт"), "save", self.save_report)])
        self.ribbon_buttons = r.buttons
        self._busy_ui(False)
        return r

    # --------------------------------------------------------- actions
    def set_view(self, tab: str) -> None:
        self.view = tab
        self.stack.setCurrentWidget(self.trees[tab])

    def _iter_leaves(self):
        for t in self.trees.values():
            for i in range(t.topLevelItemCount()):
                g = t.topLevelItem(i)
                for j in range(g.childCount()):
                    yield g.child(j)

    def _set_all(self, on: bool) -> None:
        t = self.trees[self.view]
        t.blockSignals(True)
        for i in range(t.topLevelItemCount()):
            g = t.topLevelItem(i)
            for j in range(g.childCount()):
                c = g.child(j)
                iid = c.data(0, Qt.ItemDataRole.UserRole)
                c.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
                self.win.cfg.selected[iid] = on
            g.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        t.blockSignals(False)
        self.win.cfg.save()
        self.results = []

    def _defaults(self) -> None:
        t = self.trees[self.view]
        t.blockSignals(True)
        for i in range(t.topLevelItemCount()):
            g = t.topLevelItem(i)
            for j in range(g.childCount()):
                c = g.child(j)
                iid = c.data(0, Qt.ItemDataRole.UserRole)
                c.setCheckState(0, Qt.CheckState.Checked if self.by_id[iid].default else Qt.CheckState.Unchecked)
                self.win.cfg.selected.pop(iid, None)
        t.blockSignals(False)
        t.update()
        for i in range(t.topLevelItemCount()):   # пересчитать состояние групп
            t.topLevelItem(i).setCheckState(0, t.topLevelItem(i).checkState(0))
        self.win.cfg.save()
        self.results = []

    def checked_items(self) -> List[CleanItem]:
        ids = [l.data(0, Qt.ItemDataRole.UserRole) for l in self._iter_leaves() if l.checkState(0) == Qt.CheckState.Checked]
        return [i for i in self.items if i.id in ids]

    def _busy_ui(self, busy: bool) -> None:
        b = getattr(self, "ribbon_buttons", {})
        for k in ("analyze", "run", "all", "none", "def"):
            if k in b:
                b[k].setEnabled(not busy)
        if "stop" in b:
            b["stop"].setEnabled(busy)

    def analyze(self, then_clean: bool = False) -> None:
        if self.runner.busy:
            return
        items = self.checked_items()
        if not items:
            self.summary.setText(L("Nothing selected.", "Ничего не выбрано."))
            return
        self._busy_ui(True)
        self.summary.setText(L("Analyzing…", "Анализ…"))

        def work(w):
            ctx = self.win.make_ctx()
            ctx.cancel = w.cancel_event
            return engine.analyze(items, ctx, lambda t, i, n: w.report(t, i, n))

        self.runner.start(work, lambda res: self._analyzed(res, then_clean),
                          self._failed, lambda t, i, n: self.progress.update_progress(t, i, n))

    def _analyzed(self, results, then_clean: bool) -> None:
        self._busy_ui(False)
        if results is None:
            self.progress.finish(L("Stopped.", "Остановлено."))
            return
        self.results = results
        self.cleaned = False
        self._fill(results)
        s = engine.summarize(results)
        self.progress.finish("")
        self.summary.setText(L("Found {n} files, {s} can be freed.", "Найдено файлов: {n}. Можно освободить: {s}.")
                             .format(n=s["count"], s=human_size(s["size"])))
        if then_clean:
            self._confirm_and_clean()

    def run_clean(self) -> None:
        if self.runner.busy:
            return
        if self.results and not self.cleaned:
            self._confirm_and_clean()
        else:
            self.analyze(then_clean=True)

    def _confirm_and_clean(self) -> None:
        s = engine.summarize(self.results)
        if not s["count"]:
            self.summary.setText(L("Nothing to clean.", "Нечего очищать."))
            return
        if self.win.cfg.confirm_clean and not ask(
                self, L("Run Cleaner", "Очистка"),
                L("{n} files ({s}) will be permanently deleted.\nThis cannot be undone. Continue?",
                  "Будет безвозвратно удалено файлов: {n} ({s}).\nОтменить это нельзя. Продолжить?")
                .format(n=s["count"], s=human_size(s["size"])), L("Delete", "Удалить")):
            return
        self._busy_ui(True)
        results = self.results

        def work(w):
            ctx = self.win.make_ctx()
            ctx.cancel = w.cancel_event
            return engine.clean(results, ctx, lambda t, i, n: w.report(t, i, n))

        self.runner.start(work, self._cleaned, self._failed, lambda t, i, n: self.progress.update_progress(t, i, n))

    def _cleaned(self, results) -> None:
        self._busy_ui(False)
        self.progress.finish("")
        if results is None:
            results = self.results
        self.cleaned = True
        self._fill(self.results, cleaned=True)
        s = engine.summarize(self.results)
        self.summary.setText(L("Done: removed {n} files, freed {s}. Errors: {e}.",
                               "Готово: удалено файлов — {n}, освобождено — {s}. Ошибок: {e}.")
                             .format(n=s["removed_count"], s=human_size(s["removed_size"]), e=s["errors"]))
        self.win.set_status(self.summary.text())

    def stop(self) -> None:
        self.runner.stop()

    def _failed(self, msg: str) -> None:
        self._busy_ui(False)
        self.progress.finish(msg)
        info(self, L("Error", "Ошибка"), msg, True)

    def _fill(self, results: List[ItemResult], cleaned: bool = False) -> None:
        c = palette(self.win.theme)
        self.table.setRowCount(0)
        for r in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            if r.skipped == "admin":
                status = ADMIN_TAG()
            elif r.errors:
                status = L("{n} errors", "ошибок: {n}").format(n=len(r.errors))
            elif cleaned and r.count:
                status = L("Cleaned", "Очищено")
            elif r.count:
                status = L("Ready", "Готово к очистке")
            else:
                status = L("Nothing found", "Ничего нет")
            size = r.removed_size if cleaned else r.size
            count = r.removed_count if cleaned else r.count
            it0 = cell(str(r.item.name), data=row)
            self.table.setItem(row, 0, it0)
            self.table.setItem(row, 1, cell(str(count), True))
            self.table.setItem(row, 2, cell(human_size(size), True))
            st = cell(status)
            if r.errors or r.skipped:
                st.setForeground(QBrush(QColor(c["warn"])))
            elif not r.count:
                st.setForeground(QBrush(QColor(c["muted"])))
            self.table.setItem(row, 3, st)
        self.details.clear()

    def _show_details(self) -> None:
        self.details.clear()
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = self.results[rows[0].row()]
        if not self.win.cfg.show_paths:
            self.details.addItem(L("File paths are hidden. Enable “Show file paths” in Settings → General.",
                                   "Пути файлов скрыты. Включите «Показывать пути файлов» в Настройки → Общие."))
            if r.errors:
                self.details.addItem(L("Errors: {n}", "Ошибок: {n}").format(n=len(r.errors)))
            return
        for e in r.errors[:100]:
            it = QListWidgetItem("! " + e)
            it.setForeground(QBrush(QColor(palette(self.win.theme)["warn"])))
            self.details.addItem(it)
        for f in r.found[:1500]:
            self.details.addItem(f"{f.path}" + (f"   ({human_size(f.size)})" if f.size else ""))
        if len(r.found) > 1500:
            self.details.addItem(L("… and {n} more", "… и ещё {n}").format(n=len(r.found) - 1500))

    def save_report(self) -> None:
        if not self.results:
            return
        path, _ = QFileDialog.getSaveFileName(self, L("Save report", "Сохранить отчёт"), "cleanix-report.txt", "Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(results_text(self.results) + "\n")


# ======================================================================
EASY_CATS = [
    ("temp", T("Temporary files & caches", "Временные файлы и кэши"), T("Temp folders, thumbnails, trash", "Временные папки, эскизы, корзина"), "broom"),
    ("browsers", T("Browser caches", "Кэш браузеров"), T("Chrome, Edge, Firefox, Brave, Opera…", "Chrome, Edge, Firefox, Brave, Opera…"), "apps"),
    ("traces", T("Activity traces", "Следы активности"), T("History, recent files, clipboard, sessions", "История, недавние файлы, буфер обмена, сессии"), "shield"),
    ("logs", T("Logs & crash dumps", "Журналы и дампы сбоев"), T("Log files, error reports, memory dumps", "Лог-файлы, отчёты об ошибках, дампы памяти"), "tasks"),
]


class EasyPage(QWidget):
    """Простая очистка в один клик по четырём категориям."""

    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        self.runner = TaskRunner(self)
        _, items = for_platform(NAME)
        self.cat_items: Dict[str, List[CleanItem]] = {k: [i for i in items if i.easy == k] for k, *_ in EASY_CATS}
        self.results: Dict[str, List[ItemResult]] = {}
        self.checks: Dict[str, QCheckBox] = {}
        self.sizes: Dict[str, QLabel] = {}
        self.flat = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 12)
        lay.addWidget(label(L("Quick clean", "Быстрая очистка"), "h1"))
        lay.addWidget(label(L("Pick what to clean, press Analyze to see the size, then Clean. "
                              "Safe defaults only — use “Custom Clean” for fine control.",
                              "Выберите, что чистить, нажмите «Анализ», чтобы увидеть размер, затем «Очистить». "
                              "Только безопасные настройки — тонкая настройка на вкладке «Выбор опций»."), "muted"))
        grid = QGridLayout()
        grid.setSpacing(14)
        c = palette(win.theme)
        for n, (key, title, sub, ic) in enumerate(EASY_CATS):
            box = QVBoxLayout()
            top = QHBoxLayout()
            pic = QLabel()
            pic.setPixmap(icons.icon(ic, c["accent_dark"], 36).pixmap(36, 36))
            top.addWidget(pic)
            chk = QCheckBox(str(title))
            chk.setChecked(True)
            chk.setStyleSheet("font-size:15px;font-weight:600;")
            self.checks[key] = chk
            chk.toggled.connect(lambda _=False: setattr(self, "flat", None))
            top.addWidget(chk, 1)
            box.addLayout(top)
            box.addWidget(label(str(sub), "muted"))
            sz = QLabel("—")
            sz.setObjectName("big")
            self.sizes[key] = sz
            box.addWidget(sz)
            f = card(box)
            f.setMinimumHeight(140)
            grid.addWidget(f, n // 2, n % 2)
        lay.addLayout(grid)
        self.summary = label("", "h2")
        lay.addWidget(self.summary)
        lay.addStretch(1)
        self.progress = ProgressRow()
        lay.addWidget(self.progress)

    def build_ribbon(self) -> Ribbon:
        r = Ribbon(self.win.theme)
        r.add_group(L("Quick clean", "Быстрая очистка"), [
            r.button("analyze", L("Analyze", "Анализ"), "search", self.analyze),
            r.button("clean", L("Clean", "Очистить"), "broom", self.clean, primary=True),
            r.button("stop", L("Stop", "Стоп"), "stop", lambda: self.runner.stop()),
        ])
        self.rb = r.buttons
        self.rb["stop"].setEnabled(False)
        return r

    def _selected(self) -> List[CleanItem]:
        out: List[CleanItem] = []
        for k, chk in self.checks.items():
            if chk.isChecked():
                out += self.cat_items[k]
        return out

    def _busy(self, b: bool) -> None:
        self.rb["analyze"].setEnabled(not b)
        self.rb["clean"].setEnabled(not b)
        self.rb["stop"].setEnabled(b)

    def analyze(self, then_clean: bool = False) -> None:
        if self.runner.busy:
            return
        items = self._selected()
        if not items:
            return
        self._busy(True)

        def work(w):
            ctx = self.win.make_ctx()
            ctx.cancel = w.cancel_event
            return engine.analyze(items, ctx, lambda t, i, n: w.report(t, i, n))

        def done(res):
            self._busy(False)
            self.progress.finish("")
            if res is None:
                return
            self.flat = res
            for k in self.checks:
                rs = [r for r in res if r.item.easy == k]
                self.sizes[k].setText(human_size(sum(r.size for r in rs)) if rs else "—")
            s = engine.summarize(res)
            self.summary.setText(L("Can free {s} ({n} files)", "Можно освободить {s} ({n} файлов)")
                                 .format(s=human_size(s["size"]), n=s["count"]))
            if then_clean:
                self._do_clean()

        self.runner.start(work, done, self._fail, lambda t, i, n: self.progress.update_progress(t, i, n))

    def clean(self) -> None:
        if self.runner.busy:
            return
        if getattr(self, "flat", None):
            self._do_clean()
        else:
            self.analyze(True)

    def _do_clean(self) -> None:
        res = self.flat
        s = engine.summarize(res)
        if not s["count"]:
            self.summary.setText(L("Nothing to clean.", "Нечего очищать."))
            return
        if self.win.cfg.confirm_clean and not ask(
                self, L("Clean", "Очистка"),
                L("{n} files ({s}) will be permanently deleted. Continue?",
                  "Будет безвозвратно удалено файлов: {n} ({s}). Продолжить?").format(n=s["count"], s=human_size(s["size"])),
                L("Delete", "Удалить")):
            return
        self._busy(True)

        def work(w):
            ctx = self.win.make_ctx()
            ctx.cancel = w.cancel_event
            return engine.clean(res, ctx, lambda t, i, n: w.report(t, i, n))

        def done(_):
            self._busy(False)
            self.progress.finish("")
            s2 = engine.summarize(res)
            self.summary.setText(L("Done: freed {s}, removed {n} files. Errors: {e}.",
                                   "Готово: освобождено {s}, удалено файлов — {n}. Ошибок: {e}.")
                                 .format(s=human_size(s2["removed_size"]), n=s2["removed_count"], e=s2["errors"]))
            for k in self.sizes:
                self.sizes[k].setText("0 " + L("B", "Б"))
            self.flat = None
            self.win.set_status(self.summary.text())

        self.runner.start(work, done, self._fail, lambda t, i, n: self.progress.update_progress(t, i, n))

    def _fail(self, msg: str) -> None:
        self._busy(False)
        self.progress.finish(msg)
        info(self, L("Error", "Ошибка"), msg, True)
