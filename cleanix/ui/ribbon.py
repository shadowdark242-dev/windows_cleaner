"""Верхняя панель: вкладки (как в проводнике) + лента с подменю под ними."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget)

from . import icons
from .theme import palette


class Ribbon(QFrame):
    """Горизонтальная лента с группами крупных кнопок."""

    def __init__(self, theme: str = "light"):
        super().__init__()
        self.setObjectName("ribbon")
        self.theme = theme
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(10, 6, 10, 4)
        self._lay.setSpacing(4)
        self._lay.addStretch(1)
        self._groups = 0
        self.setFixedHeight(92)
        self.buttons: dict = {}

    def add_group(self, title: str, buttons: List[QToolButton]) -> None:
        if self._groups:
            sep = QFrame()
            sep.setObjectName("sep")
            self._lay.insertWidget(self._lay.count() - 1, sep)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 0, 6, 0)
        v.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(2)
        for b in buttons:
            row.addWidget(b)
        v.addLayout(row, 1)
        label = QLabel(title)
        label.setObjectName("groupTitle")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(label)
        self._lay.insertWidget(self._lay.count() - 1, box)
        self._groups += 1

    def button(self, key: str, text: str, icon_name: str, callback: Optional[Callable] = None, *,
               checkable: bool = False, primary: bool = False, tip: str = "") -> QToolButton:
        c = palette(self.theme)
        b = QToolButton()
        b.setObjectName("ribbonBtn")
        b.setText(text)
        b.setIcon(icons.icon(icon_name, c["accent_text"] if primary else c["accent_dark"], 30))
        b.setIconSize(QSize(30, 30))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setCheckable(checkable)
        b.setProperty("primary", "true" if primary else "false")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        if callback:
            b.clicked.connect(lambda _=False, cb=callback: cb())
        self.buttons[key] = b
        return b

    def exclusive(self, buttons: List[QToolButton]) -> QButtonGroup:
        g = QButtonGroup(self)
        g.setExclusive(True)
        for b in buttons:
            b.setCheckable(True)
            g.addButton(b)
        return g
