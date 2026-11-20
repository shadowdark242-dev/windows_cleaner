"""Вкладка «Инструменты»: деинсталляция, автозагрузка, диск, дубликаты, восстановление, стирание."""
from __future__ import annotations

import os
import time
from typing import Dict, List

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QSpinBox,
                               QSplitter, QStackedWidget, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..core.config import backup_dir
from ..core.i18n import L, T, human_size
from ..core.platform import NAME
from ..tools import diskanalyzer, duplicates, plugins, restore, startup, trash, uninstall, wiper
from . import common
from .appicons import icon_for
from .common import ProgressRow, ask, button, cell, choose_dir, info, label, make_table
from .ribbon import Ribbon
from .theme import palette
from .workers import TaskRunner


class Panel(QWidget):
    """Базовый класс подстраницы инструмента."""
    title = ""
    icon = "tools"

    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        self.runner = TaskRunner(self)
        self.loaded = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 12, 14, 10)
        self.progress = ProgressRow()

    def activate(self) -> None:
        if not self.loaded:
            self.loaded = True
            self.refresh()

    def refresh(self) -> None:
        pass

    def fail(self, msg: str) -> None:
        self.progress.finish(msg)
        info(self, L("Error", "Ошибка"), msg, True)

    def toolbar(self, *widgets) -> QHBoxLayout:
        row = QHBoxLayout()
        for w in widgets:
            if w is None:
                row.addStretch(1)
            else:
                row.addWidget(w)
        return row


# ======================================================================
class UninstallPanel(Panel):
    title = T("Uninstall", "Удаление программ")
    icon = "uninstall"

    def __init__(self, win):
        super().__init__(win)
        self.programs: List[uninstall.Program] = []
        self._icon_gen = 0
        self._icon_queue: list = []
        self.search = QLineEdit()
        self.search.setPlaceholderText(L("Search…", "Поиск…"))
        self.search.textChanged.connect(self._filter)
        self.table = make_table([L("Name", "Название"), L("Publisher", "Издатель"), L("Version", "Версия"),
                                 L("Size", "Размер"), L("Installed", "Установлено")], 0)
        self.table.setIconSize(QSize(18, 18))
        self.btn_un = button(L("Uninstall", "Удалить"), self.do_uninstall, "danger")
        self.btn_rm = button(L("Remove entry", "Удалить запись"), self.do_remove_entry)
        self.btn_rm.setToolTip(L("Removes only the program's entry from the installed list (registry). Files stay on disk. "
                                 "Use it when the uninstaller is broken or missing.",
                                 "Удаляет только запись о программе из списка установленных (реестр). Файлы остаются на диске. "
                                 "Нужно, когда деинсталлятор сломан или отсутствует."))
        self.btn_rm.setVisible(NAME == "windows")
        self.lay.addLayout(self.toolbar(self.search, None, button(L("Refresh", "Обновить"), self.refresh), self.btn_rm, self.btn_un))
        self.lay.addWidget(self.table, 1)
        self.count = label("", "muted")
        self.lay.addWidget(self.count)
        self.lay.addWidget(self.progress)

    def refresh(self) -> None:
        if self.runner.busy:
            return
        self.progress.update_progress(L("Reading installed programs…", "Чтение списка программ…"))
        self.runner.start(lambda w: uninstall.list_programs(self.win.make_ctx()), self._loaded, self.fail)

    def _loaded(self, progs) -> None:
        self.progress.finish("")
        self.programs = progs or []
        self._filter()

    def _filter(self) -> None:
        q = self.search.text().lower().strip()
        self.table.setRowCount(0)
        shown = [p for p in self.programs if not q or q in p.name.lower() or q in p.publisher.lower()]
        for p in shown:
            r = self.table.rowCount()
            self.table.insertRow(r)
            name_cell = cell(p.name, data=self.programs.index(p))
            name_cell.setIcon(icon_for("", self.win.theme))          # заглушка; настоящая иконка подгрузится
            self.table.setItem(r, 0, name_cell)
            self.table.setItem(r, 1, cell(p.publisher))
            self.table.setItem(r, 2, cell(p.version))
            self.table.setItem(r, 3, cell(human_size(p.size) if p.size else "", True))
            self.table.setItem(r, 4, cell(p.date))
        self.count.setText(L("Programs: {n}", "Программ: {n}").format(n=len(shown)))
        self._icon_gen += 1
        self._icon_queue = [(r, p.icon_path or p.ident) for r, p in enumerate(shown)]
        QTimer.singleShot(0, lambda g=self._icon_gen: self._load_icons(g))

    def _load_icons(self, gen: int) -> None:
        """Иконки извлекаются из exe по несколько штук за раз, чтобы окно не подвисало."""
        if gen != self._icon_gen:
            return
        for _ in range(3):
            if not self._icon_queue:
                return
            row, src = self._icon_queue.pop(0)
            it = self.table.item(row, 0)
            if it is not None:
                it.setIcon(icon_for(src, self.win.theme))
        QTimer.singleShot(0, lambda: self._load_icons(gen))

    def do_uninstall(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        p = self.programs[self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)]
        if ask(self, L("Uninstall", "Удаление"), L("Uninstall “{n}”?", "Удалить «{n}»?").format(n=p.name), L("Uninstall", "Удалить")):
            try:
                uninstall.run_uninstall(p)
                self.win.set_status(L("Uninstaller started: {n}", "Запущен деинсталлятор: {n}").format(n=p.name))
            except OSError as exc:
                self.fail(str(exc))


    def do_remove_entry(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        p = self.programs[self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)]
        if p.kind != "reg":
            return
        reg = self.win.make_ctx().registry
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = str(backup_dir() / f"uninstall-entry-{stamp}.reg")
        msg = L("Remove the registry entry of “{n}”?\n\nThe program's files are NOT deleted; it will only disappear from "
                "this list and from Windows “Apps”. A backup will be saved to:\n{p}",
                "Удалить запись о программе «{n}» из реестра?\n\nФайлы программы НЕ удаляются: она лишь исчезнет из этого "
                "списка и из «Приложений» Windows. Резервная копия будет сохранена в:\n{p}").format(n=p.name, p=backup)
        if not ask(self, L("Remove entry", "Удаление записи"), msg, L("Remove", "Удалить")):
            return
        try:
            uninstall.remove_registry_entry(p, reg, backup)
        except PermissionError:
            self.fail(L("Access denied: this entry is protected by Windows.", "Доступ запрещён: запись защищена Windows."))
            return
        except OSError as exc:
            self.fail(str(exc))
            return
        self.win.set_status(L("Entry removed: {n}", "Запись удалена: {n}").format(n=p.name))
        self.refresh()


# ======================================================================
class StartupPanel(Panel):
    title = T("Startup", "Автозагрузка")
    icon = "startup"
    TAB_NAMES = {"run": T("Startup", "Автозагрузка"), "tasks": T("Scheduled Tasks", "Планировщик"),
                 "context": T("Context Menu", "Контекстное меню"), "services": T("Services", "Службы")}

    def __init__(self, win):
        super().__init__(win)
        self.ctx = win.make_ctx()
        self.tabs = startup.tabs_for(self.ctx)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("subtabs")
        for t in self.tabs:
            self.tabbar.addTab(str(self.TAB_NAMES[t]))
        self.tabbar.currentChanged.connect(lambda _: self.refresh())
        self.lay.addWidget(self.tabbar)
        self.entries: List[startup.Entry] = []
        self.table = make_table([L("Enabled", "Включено"), L("Key", "Ключ"), L("Name", "Название"),
                                 L("Command", "Команда"), L("Publisher", "Издатель")], 3)
        self.table.setIconSize(QSize(18, 18))
        self.b_en = button(L("Enable", "Включить"), lambda: self._toggle(True))
        self.b_dis = button(L("Disable", "Отключить"), lambda: self._toggle(False))
        self.b_del = button(L("Delete", "Удалить"), self._delete, "danger")
        self.lay.addLayout(self.toolbar(button(L("Refresh", "Обновить"), self.refresh), None, self.b_en, self.b_dis, self.b_del))
        self.lay.addWidget(self.table, 1)
        self.lay.addWidget(self.progress)

    @property
    def tab(self) -> str:
        return self.tabs[self.tabbar.currentIndex()]

    def refresh(self) -> None:
        if self.runner.busy:
            return
        tab = self.tab
        self.progress.update_progress(L("Loading…", "Загрузка…"))
        self.runner.start(lambda w: startup.list_entries(self.win.make_ctx(), tab), self._loaded, self.fail)

    def _loaded(self, entries) -> None:
        self.progress.finish("")
        self.entries = entries or []
        c = palette(self.win.theme)
        self.table.setRowCount(0)
        for n, e in enumerate(self.entries):
            self.table.insertRow(n)
            yn = L("Yes", "Да") if e.enabled else L("No", "Нет")
            name_cell = cell(e.name)
            if e.tab == "run":
                name_cell.setIcon(icon_for(e.icon_path, self.win.theme))
            items = [cell(yn, data=n), cell(e.location), name_cell, cell(e.command, tooltip=e.command), cell(e.publisher)]
            for i, it in enumerate(items):
                if not e.enabled:
                    it.setForeground(QBrush(QColor(c["muted"])))
                self.table.setItem(n, i, it)

    def _current(self):
        rows = self.table.selectionModel().selectedRows()
        return [self.entries[self.table.item(r.row(), 0).data(Qt.ItemDataRole.UserRole)] for r in rows]

    def _toggle(self, enable: bool) -> None:
        errs = []
        for e in self._current():
            if not e.can_toggle:
                continue
            try:
                startup.set_enabled(self.win.make_ctx(), e, enable)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{e.name}: {exc}")
        if errs:
            info(self, L("Error", "Ошибка"), "\n".join(errs) + "\n\n" + L("Administrator rights may be required.", "Возможно, нужны права администратора."), True)
        self.refresh()

    def _delete(self) -> None:
        sel = [e for e in self._current() if e.can_delete]
        if not sel or not ask(self, L("Delete", "Удаление"), L("Delete {n} entries? This cannot be undone.", "Удалить записей: {n}? Отменить нельзя.").format(n=len(sel)), L("Delete", "Удалить")):
            return
        errs = []
        for e in sel:
            try:
                startup.delete_entry(self.win.make_ctx(), e)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{e.name}: {exc}")
        if errs:
            info(self, L("Error", "Ошибка"), "\n".join(errs), True)
        self.refresh()


# ======================================================================
class PluginsPanel(Panel):
    title = T("Browser Plugins", "Расширения браузеров")
    icon = "plugin"

    def __init__(self, win):
        super().__init__(win)
        self.items: List[plugins.Plugin] = []
        self.table = make_table([L("Browser", "Браузер"), L("Name", "Название"), L("Version", "Версия"), "ID"], 1)
        self.lay.addLayout(self.toolbar(button(L("Refresh", "Обновить"), self.refresh), None,
                                        button(L("Open folder", "Открыть папку"), self._open)))
        self.lay.addWidget(self.table, 1)
        self.lay.addWidget(self.progress)

    def refresh(self) -> None:
        if self.runner.busy:
            return
        self.runner.start(lambda w: plugins.list_plugins(self.win.make_ctx()), self._loaded, self.fail)

    def _loaded(self, items) -> None:
        self.items = items or []
        self.table.setRowCount(0)
        for n, p in enumerate(self.items):
            self.table.insertRow(n)
            for i, v in enumerate((p.browser, p.name, p.version, p.ident)):
                self.table.setItem(n, i, cell(v, data=n if i == 0 else None))

    def _open(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            common.open_path(self.items[rows[0].row()].path)


# ======================================================================
class DiskPanel(Panel):
    title = T("Disk Analyzer", "Анализатор диска")
    icon = "disk"

    def __init__(self, win):
        super().__init__(win)
        self.report = None
        self.path = QComboBox()
        self.path.setEditable(True)
        self.path.setMinimumWidth(320)
        for d in wiper.list_drives():
            self.path.addItem(d.path)
        self.path.addItem(str(self.win.make_ctx().home))
        self.b_go = button(L("Analyze", "Анализ"), self.start, "primary")
        self.b_stop = button(L("Stop", "Стоп"), self.runner.stop)
        self.b_stop.setEnabled(False)
        self.lay.addLayout(self.toolbar(self.path, button(L("Browse…", "Обзор…"), self._browse), self.b_go, self.b_stop, None))
        split = QSplitter()
        self.cats = make_table([L("Type", "Тип"), L("Files", "Файлов"), L("Size", "Размер"), "%"], 0)
        self.cats.itemSelectionChanged.connect(self._show_files)
        self.files = make_table([L("File", "Файл"), L("Size", "Размер")], 0)
        split.addWidget(self.cats)
        split.addWidget(self.files)
        split.setSizes([380, 620])
        common.remember_splitter(split, win.cfg, "disk.h")
        self.lay.addWidget(split, 1)
        self.lay.addLayout(self.toolbar(None, button(L("Show in folder", "Показать в папке"), self._reveal)))
        self.lay.addWidget(self.progress)

    def _browse(self) -> None:
        d = choose_dir(self)
        if d:
            self.path.setEditText(d)

    def start(self) -> None:
        if self.runner.busy:
            return
        root = self.path.currentText().strip()
        if not os.path.isdir(root):
            return
        self.b_go.setEnabled(False)
        self.b_stop.setEnabled(True)

        def work(w):
            return diskanalyzer.analyze(root, w.cancel_event, lambda n, cur: w.report(f"{n} {L('files', 'файлов')}: {cur}"))

        def done(rep):
            self.b_go.setEnabled(True)
            self.b_stop.setEnabled(False)
            self.progress.finish("")
            if rep:
                self.report = rep
                self._fill()

        self.runner.start(work, done, self.fail, lambda t, i, n: self.progress.update_progress(t, 0, 0))

    def _fill(self) -> None:
        rep = self.report
        self.cats.setRowCount(0)
        total = rep.total_size or 1
        rows = [("", L("All", "Все"), rep.total_count, rep.total_size)] + [
            (k, str(diskanalyzer.CATEGORIES[k][0]), rep.count[k], rep.size[k])
            for k in sorted(diskanalyzer.CATEGORIES, key=lambda k: -rep.size[k])]
        for n, (key, name, cnt, size) in enumerate(rows):
            self.cats.insertRow(n)
            self.cats.setItem(n, 0, cell(name, data=key))
            self.cats.setItem(n, 1, cell(str(cnt), True))
            self.cats.setItem(n, 2, cell(human_size(size), True))
            self.cats.setItem(n, 3, cell(f"{size * 100 / total:.1f}", True))
        self.cats.selectRow(0)

    def _show_files(self) -> None:
        rows = self.cats.selectionModel().selectedRows()
        if not rows or not self.report:
            return
        key = self.cats.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole) or None
        self.files.setRowCount(0)
        for n, (size, path) in enumerate(self.report.largest(key, 500)):
            self.files.insertRow(n)
            self.files.setItem(n, 0, cell(path, data=path, tooltip=path))
            self.files.setItem(n, 1, cell(human_size(size), True))

    def _reveal(self) -> None:
        rows = self.files.selectionModel().selectedRows()
        if rows:
            common.reveal(self.files.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole))


# ======================================================================
class DuplicatesPanel(Panel):
    title = T("Duplicate Finder", "Поиск дубликатов")
    icon = "duplicate"

    def __init__(self, win):
        super().__init__(win)
        self.groups: List[duplicates.DupGroup] = []
        self.folders = QListWidget()
        self.folders.setMaximumHeight(90)
        for f in win.cfg.dup_folders:
            self.folders.addItem(f)
        self.min_kb = QSpinBox()
        self.min_kb.setRange(0, 10_000_000)
        self.min_kb.setValue(1)
        self.min_kb.setSuffix(" " + L("KB min", "КБ мин."))
        self.same_name = QCheckBox(L("Same name only", "Только с одинаковым именем"))
        self.skip_hidden = QCheckBox(L("Skip hidden", "Пропускать скрытые"))
        side = QVBoxLayout()
        side.addWidget(button(L("Add folder…", "Добавить папку…"), self._add))
        side.addWidget(button(L("Remove", "Убрать"), self._rm))
        top = QHBoxLayout()
        top.addWidget(self.folders, 1)
        top.addLayout(side)
        self.lay.addWidget(label(L("Search in folders (content is compared byte by byte via hashes):",
                                   "Папки для поиска (содержимое сравнивается по хэшам):"), "muted"))
        self.lay.addLayout(top)
        self.b_go = button(L("Search", "Найти"), self.start, "primary")
        self.b_stop = button(L("Stop", "Стоп"), self.runner.stop)
        self.b_stop.setEnabled(False)
        self.lay.addLayout(self.toolbar(self.min_kb, self.same_name, self.skip_hidden, None, self.b_go, self.b_stop))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([L("File", "Файл"), L("Size", "Размер")])
        self.tree.setColumnWidth(0, 640)
        self.lay.addWidget(self.tree, 1)
        self.lay.addLayout(self.toolbar(
            button(L("Keep first in each group", "Оставить первый в группе"), self._auto),
            button(L("Clear marks", "Снять отметки"), lambda: self._mark(False)),
            None,
            button(L("Move to trash", "В корзину"), lambda: self._delete(False)),
            button(L("Delete permanently", "Удалить навсегда"), lambda: self._delete(True), "danger")))
        self.summary = label("", "muted")
        self.lay.addWidget(self.summary)
        self.lay.addWidget(self.progress)

    def _add(self) -> None:
        d = choose_dir(self)
        if d:
            self.folders.addItem(d)
            self._save()

    def _rm(self) -> None:
        for it in self.folders.selectedItems():
            self.folders.takeItem(self.folders.row(it))
        self._save()

    def _save(self) -> None:
        self.win.cfg.dup_folders = [self.folders.item(i).text() for i in range(self.folders.count())]
        self.win.cfg.save()

    def start(self) -> None:
        if self.runner.busy or not self.folders.count():
            return
        roots = [self.folders.item(i).text() for i in range(self.folders.count())]
        mn, same, hid = self.min_kb.value() * 1024, self.same_name.isChecked(), self.skip_hidden.isChecked()
        excl = self.win.make_ctx().excluded
        self.b_go.setEnabled(False)
        self.b_stop.setEnabled(True)

        def work(w):
            return duplicates.find_duplicates(roots, mn, same, excl, w.cancel_event,
                                              lambda ph, i, n: w.report(f"{L('Scanning' if ph == 'scan' else 'Comparing', 'Просмотр' if ph == 'scan' else 'Сравнение')}: {i}", i, n), hid)

        def done(groups):
            self.b_go.setEnabled(True)
            self.b_stop.setEnabled(False)
            self.progress.finish("")
            self.groups = groups or []
            self._fill()

        self.runner.start(work, done, self.fail, lambda t, i, n: self.progress.update_progress(t, i, n))

    def _fill(self) -> None:
        self.tree.clear()
        wasted = 0
        for g in self.groups:
            top = QTreeWidgetItem([L("{n} identical files", "Одинаковых файлов: {n}").format(n=len(g.paths)), human_size(g.size)])
            self.tree.addTopLevelItem(top)
            for p in g.paths:
                ch = QTreeWidgetItem([p, human_size(g.size)])
                ch.setFlags(ch.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                ch.setCheckState(0, Qt.CheckState.Unchecked)
                ch.setData(0, Qt.ItemDataRole.UserRole, p)
                top.addChild(ch)
            top.setExpanded(True)
            wasted += g.size * (len(g.paths) - 1)
        self.summary.setText(L("Groups: {g}. Wasted space: {s}.", "Групп: {g}. Занято впустую: {s}.").format(g=len(self.groups), s=human_size(wasted)))

    def _leaves(self):
        for i in range(self.tree.topLevelItemCount()):
            t = self.tree.topLevelItem(i)
            for j in range(t.childCount()):
                yield t, t.child(j)

    def _auto(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            t = self.tree.topLevelItem(i)
            for j in range(t.childCount()):
                t.child(j).setCheckState(0, Qt.CheckState.Unchecked if j == 0 else Qt.CheckState.Checked)

    def _mark(self, on: bool) -> None:
        for _t, c in self._leaves():
            c.setCheckState(0, Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def _delete(self, permanent: bool) -> None:
        marked = [c for _t, c in self._leaves() if c.checkState(0) == Qt.CheckState.Checked]
        if not marked:
            return
        # никогда не удаляем ВСЕ копии группы
        for i in range(self.tree.topLevelItemCount()):
            t = self.tree.topLevelItem(i)
            if all(t.child(j).checkState(0) == Qt.CheckState.Checked for j in range(t.childCount())):
                info(self, L("Duplicate Finder", "Поиск дубликатов"),
                     L("At least one copy in every group must stay unchecked.", "В каждой группе должна остаться хотя бы одна неотмеченная копия."), True)
                return
        txt = (L("Permanently delete {n} files?", "Удалить навсегда файлов: {n}?") if permanent
               else L("Move {n} files to trash?", "Переместить файлов в корзину: {n}?")).format(n=len(marked))
        if not ask(self, L("Delete", "Удаление"), txt, L("Delete", "Удалить")):
            return
        errs, ok = [], 0
        for c in marked:
            p = c.data(0, Qt.ItemDataRole.UserRole)
            try:
                if permanent:
                    from ..core import fs
                    fs.delete_file(p, self.win.cfg.secure_passes)
                else:
                    trash.move_to_trash(p)
                ok += 1
                c.parent().removeChild(c)
            except OSError as exc:
                errs.append(f"{p}: {exc.strerror or exc}")
        self.win.set_status(L("Deleted: {n}", "Удалено: {n}").format(n=ok))
        if errs:
            info(self, L("Errors", "Ошибки"), "\n".join(errs[:15]), True)


# ======================================================================
class RestorePanel(Panel):
    title = T("System Restore", "Восстановление системы")
    icon = "restore"

    def __init__(self, win):
        super().__init__(win)
        self.table = make_table([L("Date", "Дата"), L("Description", "Описание"), L("Type", "Тип")], 1)
        self.msg = label("", "muted")
        self.lay.addLayout(self.toolbar(button(L("Refresh", "Обновить"), self.refresh), None,
                                        button(L("Create restore point", "Создать точку"), self.create, "primary"),
                                        button(L("Open restore tool", "Открыть средство восстановления"), self.open_ui)))
        self.lay.addWidget(self.msg)
        self.lay.addWidget(self.table, 1)
        self.lay.addWidget(self.progress)

    def activate(self) -> None:
        if not self.loaded and restore.backend_name(self.win.make_ctx()) == "timeshift":
            self.loaded = True        # timeshift --list требует root (pkexec) — не спрашиваем пароль без клика
            self.msg.setText(L("Backend: Timeshift. Press “Refresh” to list snapshots (asks for the password).",
                               "Средство: Timeshift. Нажмите «Обновить», чтобы показать снимки (спросит пароль)."))
            return
        super().activate()

    def refresh(self) -> None:
        ctx = self.win.make_ctx()
        b = restore.backend_name(ctx)
        if b is None:
            self.msg.setText(L("No supported snapshot tool found. Install Timeshift or Snapper to use restore points.",
                               "Не найдено поддерживаемое средство снимков. Установите Timeshift или Snapper."))
            return
        self.msg.setText(L("Backend: {b}", "Средство: {b}").format(b=b))
        if self.runner.busy:
            return
        self.progress.update_progress(L("Loading…", "Загрузка…"))
        self.runner.start(lambda w: restore.list_points(self.win.make_ctx()), self._loaded, self.fail)

    def _loaded(self, pts) -> None:
        self.progress.finish("")
        self.table.setRowCount(0)
        for n, p in enumerate(pts or []):
            self.table.insertRow(n)
            for i, v in enumerate((p.date, p.description, p.kind)):
                self.table.setItem(n, i, cell(v))

    def create(self) -> None:
        if self.runner.busy or restore.backend_name(self.win.make_ctx()) is None:
            return
        if not ask(self, L("Restore point", "Точка восстановления"), L("Create a restore point now? It may take a while.", "Создать точку восстановления сейчас? Это может занять время."), L("Create", "Создать")):
            return
        self.progress.update_progress(L("Creating restore point…", "Создание точки…"))
        self.runner.start(lambda w: restore.create_point(self.win.make_ctx(), "Cleanix"), lambda _: (self.progress.finish(""), self.refresh_force()), self.fail)

    def refresh_force(self) -> None:
        self.loaded = True
        self.refresh()

    def open_ui(self) -> None:
        try:
            restore.open_restore_ui(self.win.make_ctx())
        except OSError as exc:
            self.fail(str(exc))


# ======================================================================
class WiperPanel(Panel):
    title = T("Drive Wiper", "Стирание диска")
    icon = "wiper"

    def __init__(self, win):
        super().__init__(win)
        self.drives = wiper.list_drives()
        self.lay.addWidget(label(L("Wipe free space", "Стирание свободного места"), "h2"))
        self.lay.addWidget(label(L("Overwrites the free space so that deleted files cannot be recovered. "
                                   "Existing files are not touched. The drive is never filled completely (a safety reserve is kept).",
                                   "Перезаписывает свободное место, чтобы удалённые файлы нельзя было восстановить. "
                                   "Существующие файлы не затрагиваются. Диск никогда не заполняется целиком — остаётся запас."), "muted"))
        self.table = make_table(["", L("Drive", "Диск"), L("File system", "ФС"), L("Total", "Всего"), L("Free", "Свободно")], 1)
        for n, d in enumerate(self.drives):
            self.table.insertRow(n)
            self.table.setItem(n, 0, cell("", checkable=True, checked=False, data=n))
            for i, v in enumerate((d.path, d.fs, human_size(d.total), human_size(d.free)), 1):
                self.table.setItem(n, i, cell(v, i >= 3))
        self.table.setMaximumHeight(170)
        self.lay.addWidget(self.table)
        self.passes = QComboBox()
        for n, name in wiper.PASS_PRESETS.items():
            self.passes.addItem(name, n)
        self.reserve = QSpinBox()
        self.reserve.setRange(16, 100000)
        self.reserve.setValue(256)
        self.reserve.setSuffix(" " + L("MB reserve", "МБ запас"))
        self.b_go = button(L("Wipe free space", "Стереть свободное место"), self.start, "primary")
        self.b_stop = button(L("Stop", "Стоп"), self.runner.stop)
        self.b_stop.setEnabled(False)
        self.lay.addLayout(self.toolbar(self.passes, self.reserve, None, self.b_go, self.b_stop))
        self.lay.addWidget(label(L("Secure delete files", "Надёжное удаление файлов"), "h2"))
        self.lay.addLayout(self.toolbar(button(L("Choose files…", "Выбрать файлы…"), self._shred_files),
                                        button(L("Choose folder…", "Выбрать папку…"), self._shred_dir), None))
        self.lay.addStretch(1)
        self.lay.addWidget(self.progress)

    def _checked(self):
        return [self.drives[self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]

    def start(self) -> None:
        sel = self._checked()
        if self.runner.busy or not sel:
            return
        passes = self.passes.currentData()
        if not ask(self, L("Drive Wiper", "Стирание диска"),
                   L("Free space on {n} drive(s) will be overwritten ({p} pass(es)). This can take hours and wears SSDs. Continue?",
                     "Свободное место на дисках ({n}) будет перезаписано (проходов: {p}). Это может занять часы и изнашивает SSD. Продолжить?")
                   .format(n=len(sel), p=passes), L("Start", "Начать")):
            return
        reserve = self.reserve.value() * 1024 * 1024
        self.b_go.setEnabled(False)
        self.b_stop.setEnabled(True)

        def work(w):
            for d in sel:
                wiper.wipe_free_space(d.path, passes, reserve, None, w.cancel_event,
                                      lambda p, tp, written: w.report(f"{d.path}: {L('pass', 'проход')} {p}/{tp} — {human_size(written)}"))
            return True

        def done(_):
            self.b_go.setEnabled(True)
            self.b_stop.setEnabled(False)
            self.progress.finish(L("Finished.", "Готово."))

        self.runner.start(work, done, lambda m: (self.b_go.setEnabled(True), self.b_stop.setEnabled(False), self.fail(m)),
                          lambda t, i, n: self.progress.update_progress(t, 0, 0))

    def _shred(self, paths: List[str]) -> None:
        if not paths:
            return
        if not ask(self, L("Secure delete", "Надёжное удаление"),
                   L("Permanently destroy {n} item(s)? This cannot be undone.", "Безвозвратно уничтожить объектов: {n}? Отменить нельзя.").format(n=len(paths)), L("Destroy", "Уничтожить")):
            return
        passes = self.passes.currentData()
        errs = wiper.shred_paths(paths, passes)
        info(self, L("Secure delete", "Надёжное удаление"), "\n".join(errs[:10]) if errs else L("Done.", "Готово."), bool(errs))

    def _shred_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, L("Choose files", "Выберите файлы"))
        self._shred(files)

    def _shred_dir(self) -> None:
        d = choose_dir(self)
        if d:
            self._shred([d])


# ======================================================================
class ToolsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.panels: Dict[str, Panel] = {}
        for key, cls in (("uninstall", UninstallPanel), ("startup", StartupPanel), ("plugins", PluginsPanel),
                         ("disk", DiskPanel), ("dups", DuplicatesPanel), ("restore", RestorePanel), ("wiper", WiperPanel)):
            p = cls(win)
            self.panels[key] = p
            self.stack.addWidget(p)

    def build_ribbon(self) -> Ribbon:
        r = Ribbon(self.win.theme)
        btns = {}
        for key, p in self.panels.items():
            btns[key] = r.button(key, str(p.title), p.icon, lambda k=key: self.show_panel(k))
        r.exclusive(list(btns.values()))
        r.add_group(L("Programs", "Программы"), [btns["uninstall"], btns["startup"], btns["plugins"]])
        r.add_group(L("Disk", "Диск"), [btns["disk"], btns["dups"]])
        r.add_group(L("System", "Система"), [btns["restore"], btns["wiper"]])
        btns["uninstall"].setChecked(True)
        return r

    def show_panel(self, key: str) -> None:
        p = self.panels[key]
        self.stack.setCurrentWidget(p)
        p.activate()
