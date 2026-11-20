"""Главное окно: вкладки сверху (как в проводнике), под ними лента-подменю, ниже страница."""
from __future__ import annotations

from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QTabBar, QVBoxLayout, QWidget)

from .. import APP_NAME
from ..core.config import Config
from ..core.engine import Ctx
from ..core.i18n import L
from ..core.platform import NAME, is_admin
from . import icons
from .page_clean import CustomPage, EasyPage
from .page_registry import IssuesPage
from .page_settings import SettingsPage
from .page_tools import ToolsPage


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, start_tab: str = "", on_reload=None):
        super().__init__()
        self.cfg = cfg
        self.theme = cfg.theme
        self._on_reload = on_reload
        self.setWindowTitle(APP_NAME + (" — " + L("Administrator", "Администратор") if is_admin() else ""))
        self.setWindowIcon(icons.app_icon())
        size = cfg.layout.get("window")
        if isinstance(size, list) and len(size) == 2 and all(isinstance(x, int) and 600 <= x <= 10000 for x in size):
            self.resize(size[0], size[1])
        else:
            self.resize(1100, 720)
        if cfg.layout.get("maximized"):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        self.setMinimumSize(900, 600)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # --- верхняя полоса: бренд + вкладки
        bar = QWidget()
        bar.setObjectName("titlebar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 2, 8, 0)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(22, 22))
        brand = QLabel(APP_NAME)
        brand.setObjectName("brand")
        h.addWidget(logo)
        h.addWidget(brand)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("maintabs")
        self.tabbar.setDrawBase(False)
        self.tabbar.setExpanding(False)
        self.tabbar.setUsesScrollButtons(False)
        h.addWidget(self.tabbar)
        h.addStretch(1)
        v.addWidget(bar)

        # --- лента + страницы
        self.ribbons = QStackedWidget()
        self.ribbons.setFixedHeight(92)
        v.addWidget(self.ribbons)
        self.pages = QStackedWidget()
        v.addWidget(self.pages, 1)

        issues_title = L("Registry", "Реестр") if NAME == "windows" else L("System issues", "Системные проблемы")
        defs = [
            ("easy", L("Clean", "Очистка"), EasyPage),
            ("custom", L("Options", "Выбор опций"), CustomPage),
            ("issues", issues_title, IssuesPage),
            ("tools", L("Tools", "Инструменты"), ToolsPage),
            ("settings", L("Settings", "Настройки"), SettingsPage),
        ]
        self.keys = []
        self.page_by_key: Dict[str, QWidget] = {}
        for key, title, cls in defs:
            page = cls(self)
            self.page_by_key[key] = page
            self.keys.append(key)
            self.tabbar.addTab(title)
            self.pages.addWidget(page)
            self.ribbons.addWidget(page.build_ribbon())
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.statusBar().showMessage(L("Ready", "Готово"))
        self.show_tab(start_tab if start_tab in self.keys else "easy")      # главный экран — «Очистка»

    # ------------------------------------------------------------------
    @property
    def tabs(self):
        return self.keys

    def make_ctx(self) -> Ctx:
        return Ctx(config=self.cfg)

    def set_status(self, text: str) -> None:
        self.statusBar().showMessage(text.replace("\n", " "), 20000)

    def show_tab(self, key: str) -> None:
        self.tabbar.setCurrentIndex(self.keys.index(key))
        self._tab_changed(self.keys.index(key))

    def _tab_changed(self, idx: int) -> None:
        self.pages.setCurrentIndex(idx)
        self.ribbons.setCurrentIndex(idx)
        key = self.keys[idx]
        self.cfg.last_tab = key
        page = self.page_by_key[key]
        if key == "tools":
            cur = page.stack.currentWidget()
            if cur is not None and hasattr(cur, "activate"):
                cur.activate()

    def reload_ui(self, tab: str = "") -> None:
        """Пересоздать окно (смена языка/темы)."""
        if self._on_reload:
            self._on_reload(tab or self.keys[self.tabbar.currentIndex()])

    def closeEvent(self, e) -> None:  # noqa: N802
        for page in self.page_by_key.values():
            for obj in [page] + list(getattr(page, "panels", {}).values()):
                r = getattr(obj, "runner", None)
                if r is not None and r.busy:
                    r.stop()
                    r.wait(3000)
        if not self.isMaximized():
            self.cfg.layout["window"] = [self.width(), self.height()]
        self.cfg.layout["maximized"] = self.isMaximized()
        self.cfg.save()
        super().closeEvent(e)
