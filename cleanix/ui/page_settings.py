"""Вкладка «Настройки»: общие, куки, включения, исключения, расписание, дополнительно, о программе."""
from __future__ import annotations

import platform
from typing import Dict

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QSpinBox, QStackedWidget, QTimeEdit, QVBoxLayout,
                               QWidget)

from .. import APP_NAME, __version__, scheduler
from ..core import platform as plat
from ..core.config import Config, config_dir
from ..core.i18n import L
from ..tools import cookies
from . import common
from .common import ask, button, cell, choose_dir, info, label, make_table
from .ribbon import Ribbon
from .workers import TaskRunner


class SubPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 18, 24, 12)

    def save(self) -> None:
        self.win.cfg.save()


class GeneralPage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        cfg = win.cfg
        self.lay.addWidget(label(L("General", "Общие"), "h1"))
        form = QFormLayout()
        form.setSpacing(12)
        self.lang = QComboBox()
        for code, name in (("auto", L("Automatic", "Автоматически")), ("ru", "Русский"), ("en", "English")):
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg.language)))
        self.lang.currentIndexChanged.connect(self._lang)
        form.addRow(L("Language", "Язык"), self.lang)
        self.theme = QComboBox()
        self.theme.addItem(L("Light", "Светлая"), "light")
        self.theme.addItem(L("Dark", "Тёмная"), "dark")
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg.theme)))
        self.theme.currentIndexChanged.connect(self._theme)
        form.addRow(L("Theme", "Тема"), self.theme)
        self.secure = QComboBox()
        self.secure.addItem(L("Normal file deletion (faster)", "Обычное удаление (быстрее)"), 0)
        for n, name in ((1, L("Secure: 1 pass", "Надёжное: 1 проход")), (3, L("Secure: 3 passes", "Надёжное: 3 прохода")),
                        (7, L("Secure: 7 passes", "Надёжное: 7 проходов")), (35, L("Secure: 35 passes", "Надёжное: 35 проходов"))):
            self.secure.addItem(name, n)
        self.secure.setCurrentIndex(max(0, self.secure.findData(cfg.secure_passes)))
        self.secure.currentIndexChanged.connect(self._secure)
        form.addRow(L("Deletion method", "Способ удаления"), self.secure)
        self.lay.addLayout(form)
        self.confirm = QCheckBox(L("Ask for confirmation before cleaning", "Спрашивать подтверждение перед очисткой"))
        self.confirm.setChecked(cfg.confirm_clean)
        self.confirm.toggled.connect(self._confirm)
        self.lay.addWidget(self.confirm)
        self.paths = QCheckBox(L("Show file paths in analysis results", "Показывать пути файлов в результатах анализа"))
        self.paths.setChecked(cfg.show_paths)
        self.paths.toggled.connect(self._paths)
        self.lay.addWidget(self.paths)
        self.lay.addWidget(label(L("Secure deletion overwrites file contents before removing them. It is slower and is not "
                                   "effective on SSDs with wear-levelling.",
                                   "Надёжное удаление перезаписывает содержимое файла перед удалением. Оно медленнее и "
                                   "не гарантирует результат на SSD с выравниванием износа."), "muted"))
        self.lay.addStretch(1)

    def _lang(self) -> None:
        self.win.cfg.language = self.lang.currentData()
        self.save()
        self.win.reload_ui("settings")

    def _theme(self) -> None:
        self.win.cfg.theme = self.theme.currentData()
        self.save()
        self.win.reload_ui("settings")

    def _secure(self) -> None:
        self.win.cfg.secure_passes = self.secure.currentData()
        self.save()

    def _paths(self, on: bool) -> None:
        self.win.cfg.show_paths = on
        self.save()

    def _confirm(self, on: bool) -> None:
        self.win.cfg.confirm_clean = on
        self.save()


class CookiesPage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        self.runner = TaskRunner(self)
        self.lay.addWidget(label(L("Cookies to keep", "Cookies, которые нужно оставить"), "h1"))
        self.lay.addWidget(label(L("Cookies of these domains survive cleaning (subdomains included). "
                                   "Close the browser before cleaning cookies.",
                                   "Cookies этих доменов сохраняются при очистке (включая поддомены). "
                                   "Перед очисткой закройте браузер."), "muted"))
        row = QHBoxLayout()
        self.found = QListWidget()
        self.found.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.keep = QListWidget()
        self.keep.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        mid = QVBoxLayout()
        mid.addStretch(1)
        mid.addWidget(button("→", self._to_keep))
        mid.addWidget(button("←", self._from_keep))
        mid.addStretch(1)
        left = QVBoxLayout()
        left.addWidget(label(L("Cookies on this computer", "Cookies на компьютере"), "h2"))
        left.addWidget(self.found, 1)
        left.addWidget(button(L("Scan browsers", "Найти в браузерах"), self.scan))
        right = QVBoxLayout()
        right.addWidget(label(L("Cookies to keep", "Оставить"), "h2"))
        right.addWidget(self.keep, 1)
        add = QHBoxLayout()
        self.manual = QLineEdit()
        self.manual.setPlaceholderText("example.com")
        self.manual.returnPressed.connect(self._add_manual)
        add.addWidget(self.manual, 1)
        add.addWidget(button(L("Add", "Добавить"), self._add_manual))
        right.addLayout(add)
        row.addLayout(left, 1)
        row.addLayout(mid)
        row.addLayout(right, 1)
        self.lay.addLayout(row, 1)
        for d in win.cfg.cookies_keep:
            self.keep.addItem(d)

    def scan(self) -> None:
        if self.runner.busy:
            return
        self.runner.start(lambda w: cookies.list_cookie_domains(self.win.make_ctx()), self._loaded,
                          lambda m: info(self, L("Error", "Ошибка"), m, True))

    def _loaded(self, counts: Dict[str, int]) -> None:
        self.found.clear()
        for d in sorted(counts or {}):
            self.found.addItem(d)

    def _sync(self) -> None:
        self.win.cfg.cookies_keep = [self.keep.item(i).text() for i in range(self.keep.count())]
        self.save()

    def _has(self, d: str) -> bool:
        return any(self.keep.item(i).text() == d for i in range(self.keep.count()))

    def _to_keep(self) -> None:
        for it in self.found.selectedItems():
            if not self._has(it.text()):
                self.keep.addItem(it.text())
        self._sync()

    def _from_keep(self) -> None:
        for it in self.keep.selectedItems():
            self.keep.takeItem(self.keep.row(it))
        self._sync()

    def _add_manual(self) -> None:
        d = self.manual.text().strip().lower().lstrip(".")
        if d and not self._has(d):
            self.keep.addItem(d)
            self._sync()
        self.manual.clear()


class IncludeDialog(QDialog):
    def __init__(self, parent, path: str):
        super().__init__(parent)
        self.setWindowTitle(L("Include", "Включение"))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(path))
        form = QFormLayout()
        self.mode = QComboBox()
        self.mode.addItem(L("Files and empty folders", "Файлы и пустые папки"), "all")
        self.mode.addItem(L("Files only", "Только файлы"), "files")
        self.pattern = QLineEdit("*")
        self.pattern.setToolTip(L("Masks separated by ';', e.g. *.tmp;*.log", "Маски через «;», например *.tmp;*.log"))
        self.rec = QCheckBox(L("Include subfolders", "Включая вложенные папки"))
        self.rec.setChecked(True)
        form.addRow(L("Remove", "Удалять"), self.mode)
        form.addRow(L("Mask", "Маска"), self.pattern)
        lay.addLayout(form)
        lay.addWidget(self.rec)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_entry(self, path: str) -> dict:
        return {"path": path, "mode": self.mode.currentData(), "pattern": self.pattern.text().strip() or "*",
                "recursive": self.rec.isChecked()}


class IncludePage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        self.lay.addWidget(label(L("Include", "Включения"), "h1"))
        self.lay.addWidget(label(L("Extra folders and files to clean. Enable the option “Custom Files and Folders” "
                                   "on the “Custom Clean” tab to use them.",
                                   "Дополнительные папки и файлы для очистки. Включите опцию «Пользовательские файлы и папки» "
                                   "на вкладке «Выбор опций»."), "muted"))
        self.table = make_table([L("Path", "Путь"), L("Mask", "Маска"), L("Mode", "Режим"), L("Subfolders", "Вложенные")], 0)
        self.lay.addWidget(self.table, 1)
        self.lay.addLayout(self._buttons())
        self._fill()

    def _buttons(self):
        row = QHBoxLayout()
        row.addWidget(button(L("Add folder…", "Добавить папку…"), self._add_dir))
        row.addWidget(button(L("Add file…", "Добавить файл…"), self._add_file))
        row.addStretch(1)
        row.addWidget(button(L("Remove", "Убрать"), self._rm, "danger"))
        return row

    def _fill(self) -> None:
        self.table.setRowCount(0)
        for n, e in enumerate(self.win.cfg.include):
            self.table.insertRow(n)
            self.table.setItem(n, 0, cell(e["path"]))
            self.table.setItem(n, 1, cell(e.get("pattern", "*")))
            self.table.setItem(n, 2, cell(L("Files only", "Только файлы") if e.get("mode") == "files" else L("Files and folders", "Файлы и папки")))
            self.table.setItem(n, 3, cell(L("Yes", "Да") if e.get("recursive", True) else L("No", "Нет")))

    def _add_dir(self) -> None:
        d = choose_dir(self)
        if d:
            dlg = IncludeDialog(self, d)
            if dlg.exec():
                self.win.cfg.include.append(dlg.result_entry(d))
                self.save()
                self._fill()

    def _add_file(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, L("Choose file", "Выберите файл"))
        if f:
            self.win.cfg.include.append({"path": f, "mode": "files", "pattern": "*", "recursive": False})
            self.save()
            self._fill()

    def _rm(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.win.cfg.include[r]
        self.save()
        self._fill()


class ExcludePage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        self.lay.addWidget(label(L("Exclude", "Исключения"), "h1"))
        self.lay.addWidget(label(L("Files and folders listed here are never deleted by any cleaning option.",
                                   "Перечисленные файлы и папки не удаляются ни одной опцией очистки."), "muted"))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        for p in win.cfg.exclude:
            self.list.addItem(p)
        self.lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(button(L("Add folder…", "Добавить папку…"), self._add_dir))
        row.addWidget(button(L("Add file…", "Добавить файл…"), self._add_file))
        row.addStretch(1)
        row.addWidget(button(L("Remove", "Убрать"), self._rm, "danger"))
        self.lay.addLayout(row)

    def _sync(self) -> None:
        self.win.cfg.exclude = [self.list.item(i).text() for i in range(self.list.count())]
        self.save()

    def _add(self, p: str) -> None:
        if p and not any(self.list.item(i).text() == p for i in range(self.list.count())):
            self.list.addItem(p)
            self._sync()

    def _add_dir(self) -> None:
        self._add(choose_dir(self))

    def _add_file(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, L("Choose file", "Выберите файл"))
        self._add(f)

    def _rm(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._sync()


class SchedulePage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        s = win.cfg.schedule
        self.lay.addWidget(label(L("Scheduling", "Расписание"), "h1"))
        self.lay.addWidget(label(L("Runs the cleaner silently with the options currently ticked in “Custom Clean”. "
                                   "Uses Task Scheduler on Windows and cron on Linux.",
                                   "Запускает очистку без окна с опциями, отмеченными в «Выборе опций». "
                                   "Используется Планировщик заданий Windows или cron в Linux."), "muted"))
        self.enable = QCheckBox(L("Run cleaning on a schedule", "Запускать очистку по расписанию"))
        self.enable.setChecked(bool(s.get("enabled")))
        self.lay.addWidget(self.enable)
        form = QFormLayout()
        self.freq = QComboBox()
        self.freq.addItem(L("Every day", "Каждый день"), "daily")
        self.freq.addItem(L("Every week (Monday)", "Каждую неделю (понедельник)"), "weekly")
        self.freq.addItem(L("At logon / boot", "При входе / загрузке"), "logon")
        self.freq.setCurrentIndex(max(0, self.freq.findData(s.get("freq", "daily"))))
        self.time = QTimeEdit(QTime.fromString(s.get("time", "09:00"), "HH:mm"))
        self.time.setDisplayFormat("HH:mm")
        form.addRow(L("Frequency", "Периодичность"), self.freq)
        form.addRow(L("Time", "Время"), self.time)
        self.lay.addLayout(form)
        self.lay.addWidget(button(L("Apply", "Применить"), self.apply, "primary"), 0, Qt.AlignmentFlag.AlignLeft)
        self.status = label("", "muted")
        self.lay.addWidget(self.status)
        self.lay.addStretch(1)

    def apply(self) -> None:
        sched = {"enabled": self.enable.isChecked(), "freq": self.freq.currentData(), "time": self.time.time().toString("HH:mm")}
        try:
            scheduler.apply(sched, plat.IS_WINDOWS)
        except OSError as exc:
            self.status.setText(L("Failed: {e}", "Не удалось: {e}").format(e=exc))
            return
        self.win.cfg.schedule = sched
        self.save()
        self.status.setText(L("Schedule saved.", "Расписание сохранено.") if sched["enabled"] else L("Schedule removed.", "Расписание удалено."))


class AdvancedPage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        self.lay.addWidget(label(L("Advanced", "Дополнительно"), "h1"))
        form = QFormLayout()
        self.age = QSpinBox()
        self.age.setRange(0, 24 * 365)
        self.age.setValue(win.cfg.min_age_hours)
        self.age.setSuffix(" " + L("h", "ч"))
        self.age.valueChanged.connect(self._age)
        form.addRow(L("Skip temporary files newer than", "Не трогать временные файлы моложе"), self.age)
        self.lay.addLayout(form)
        self.lay.addWidget(button(L("Open settings folder", "Открыть папку настроек"), lambda: common.open_path(str(config_dir()))), 0, Qt.AlignmentFlag.AlignLeft)
        if plat.IS_WINDOWS and not plat.is_admin():
            self.lay.addWidget(button(L("Restart as administrator", "Перезапустить от имени администратора"), self._admin),
                               0, Qt.AlignmentFlag.AlignLeft)
            self.lay.addWidget(label(L("Needed for Prefetch, system Temp, event logs, services and HKLM registry changes.",
                                       "Нужно для Prefetch, системного Temp, журналов событий, служб и изменений HKLM."), "muted"))
        elif plat.IS_LINUX and not plat.is_admin():
            self.lay.addWidget(label(L("Root-only options (journal, package cache, /var/log) need: sudo -E python -m cleanix",
                                       "Опции, требующие root (журнал, кэш пакетов, /var/log): sudo -E python -m cleanix"), "muted"))
        self.lay.addWidget(button(L("Reset all settings", "Сбросить все настройки"), self._reset, "danger"), 0, Qt.AlignmentFlag.AlignLeft)
        self.lay.addStretch(1)

    def _admin(self) -> None:
        if plat.relaunch_as_admin():
            from PySide6.QtWidgets import QApplication
            QApplication.quit()

    def _age(self, v: int) -> None:
        self.win.cfg.min_age_hours = v
        self.save()

    def _reset(self) -> None:
        if ask(self, L("Reset", "Сброс"), L("Reset all settings to defaults?", "Сбросить все настройки по умолчанию?"), L("Reset", "Сбросить")):
            fresh = Config()
            self.win.cfg.__dict__.update(fresh.__dict__)
            self.save()
            self.win.reload_ui("settings")


class AboutPage(SubPage):
    def __init__(self, win):
        super().__init__(win)
        self.lay.addWidget(label(f"{APP_NAME} {__version__}", "h1"))
        self.lay.addWidget(label(L("Cross-platform system cleaner for Windows and Linux: junk files, privacy traces, "
                                   "registry / system issues, startup manager, duplicate finder and more.",
                                   "Кроссплатформенный чистильщик для Windows и Linux: мусор, следы активности, "
                                   "реестр / системные проблемы, автозагрузка, поиск дубликатов и другое."), "muted"))
        rows = [
            (L("System", "Система"), plat.os_description()),
            (L("Privileges", "Права"), L("Administrator / root", "Администратор / root") if plat.is_admin() else L("Standard user", "Обычный пользователь")),
            ("Python", platform.python_version()),
            ("PySide6", pyside_version),
            (L("Settings", "Настройки"), str(config_dir())),
        ]
        form = QFormLayout()
        for k, v in rows:
            val = QLabel(v)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(k + ":", val)
        self.lay.addLayout(form)
        self.lay.addWidget(label(L("Cleaning permanently deletes files. Review the “Analyze” results before cleaning. "
                                   "Registry fixes are backed up to a .reg file first.",
                                   "Очистка удаляет файлы безвозвратно. Перед очисткой смотрите результаты «Анализа». "
                                   "Исправления реестра предварительно сохраняются в .reg-файл."), "muted"))
        self.lay.addStretch(1)


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.setObjectName("page")
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)
        self.pages = {}
        for key, cls in (("general", GeneralPage), ("cookies", CookiesPage), ("include", IncludePage),
                         ("exclude", ExcludePage), ("schedule", SchedulePage), ("advanced", AdvancedPage), ("about", AboutPage)):
            p = cls(win)
            self.pages[key] = p
            self.stack.addWidget(p)

    def build_ribbon(self) -> Ribbon:
        r = Ribbon(self.win.theme)
        defs = [("general", L("General", "Общие"), "general"), ("cookies", "Cookies", "cookie"),
                ("include", L("Include", "Включения"), "include"), ("exclude", L("Exclude", "Исключения"), "exclude"),
                ("schedule", L("Scheduling", "Расписание"), "calendar"), ("advanced", L("Advanced", "Дополнительно"), "advanced"),
                ("about", L("About", "О программе"), "info")]
        btns = {k: r.button(k, name, ic, lambda kk=k: self.show_page(kk)) for k, name, ic in defs}
        r.exclusive(list(btns.values()))
        r.add_group(L("Basic", "Основные"), [btns["general"], btns["advanced"], btns["schedule"]])
        r.add_group(L("Rules", "Правила"), [btns["cookies"], btns["include"], btns["exclude"]])
        r.add_group(L("Help", "Справка"), [btns["about"]])
        btns["general"].setChecked(True)
        self.buttons = btns
        return r

    def show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key])
        if key in self.buttons:
            self.buttons[key].setChecked(True)
