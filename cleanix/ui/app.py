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
from .theme import palette, set_accent, stylesheet


def _write_assets(check_color: str) -> tuple[str, str]:
    """Галочка и стрелка для QSS (он сам их не рисует). Цвет галочки зависит от акцента."""
    d = Path(config_dir())
    chk, chev = d / "check.svg", d / "chevron.svg"
    try:
        chk.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" '
            f'stroke="{check_color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8.5l3 3 6-7"/></svg>')
        chev.write_bytes(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12" fill="none" '
            b'stroke="#6b7a75" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4.5l3.5 3.5 3.5-3.5"/></svg>')
    except OSError:
        return "", ""
    return chk.as_posix(), chev.as_posix()


class Controller:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = Config.load()
        self.win = None

    def show(self, tab: str = "") -> None:
        set_language(self.cfg.language)
        set_accent(self.cfg.accent, self.cfg.accent_custom)
        chk, chev = _write_assets(palette(self.cfg.theme)["accent_text"])
        self.app.setStyleSheet(stylesheet(self.cfg.theme, chk, chev))
        self.app.setWindowIcon(icons.app_icon())
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
