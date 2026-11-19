"""Запуск графического приложения."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from .. import APP_NAME
from ..core.config import Config, config_dir
from ..core.i18n import set_language
from . import icons
from .main_window import MainWindow
from .theme import stylesheet


def _check_icon() -> str:
    """Галочка для чекбоксов (QSS не умеет рисовать сам)."""
    p = Path(config_dir()) / "check.svg"
    try:
        p.write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" '
            b'stroke="white" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>')
    except OSError:
        return ""
    c = Path(config_dir()) / "chevron.svg"
    try:
        c.write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12" fill="none" '
            b'stroke="#6b7a75" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5l3.5 3.5 3.5-3.5"/></svg>')
    except OSError:
        pass
    return p.as_posix()


class Controller:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = Config.load()
        self.win = None
        self.check = _check_icon()

    def show(self, tab: str = "") -> None:
        set_language(self.cfg.language)
        self.app.setStyleSheet(stylesheet(self.cfg.theme, self.check, (Path(config_dir()) / "chevron.svg").as_posix()))
        old = self.win
        self.win = MainWindow(self.cfg, tab, self.show)
        self.win.show()
        if old is not None:
            old.hide()
            old.deleteLater()


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(icons.app_icon())
    ctl = Controller(app)
    ctl.show()
    return app.exec()
