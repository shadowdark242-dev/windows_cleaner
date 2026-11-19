"""Маленькие иконки программ: из exe/ico (Windows) или из темы значков (Linux)."""
from __future__ import annotations

import os
from typing import Dict

from PySide6.QtCore import QFileInfo
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider

from . import icons

_cache: Dict[str, QIcon] = {}
_provider = None


def _fallback(theme: str) -> QIcon:
    key = "__fallback__" + theme
    if key not in _cache:
        from .theme import palette
        _cache[key] = icons.icon("apps", palette(theme)["muted"], 16)
    return _cache[key]


def icon_for(source: str, theme: str = "light") -> QIcon:
    """source — путь к файлу (exe/ico/lnk) или имя иконки из темы. Всегда возвращает непустую иконку."""
    global _provider
    if not source:
        return _fallback(theme)
    if source in _cache:
        return _cache[source]
    ic = QIcon()
    try:
        if os.path.isabs(source) or "\\" in source or "/" in source:
            if os.path.isfile(source):
                if source.lower().endswith((".ico", ".png", ".svg", ".xpm")):
                    ic = QIcon(source)
                else:
                    if _provider is None:
                        _provider = QFileIconProvider()
                    ic = _provider.icon(QFileInfo(source))
        else:
            ic = QIcon.fromTheme(source)
    except Exception:
        ic = QIcon()
    if ic.isNull():
        ic = _fallback(theme)
    _cache[source] = ic
    return ic
