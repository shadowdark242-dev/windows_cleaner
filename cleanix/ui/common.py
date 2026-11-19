"""Общие виджеты и вспомогательные функции интерфейса."""
from __future__ import annotations

from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QMenu, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.i18n import L


def card(layout: Optional[QVBoxLayout] = None) -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    if layout is not None:
        f.setLayout(layout)
    return f


def label(text: str, kind: str = "") -> QLabel:
    lb = QLabel(text)
    if kind:
        lb.setObjectName(kind)
    lb.setWordWrap(kind in ("muted", ""))
    return lb


def button(text: str, cb: Optional[Callable] = None, kind: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if cb:
        b.clicked.connect(lambda _=False: cb())
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class CopyTable(QTableWidget):
    """Таблица с копированием: Ctrl+C — выбранные строки, правый клик — ячейка / строка."""

    def _row_text(self, row: int) -> str:
        parts = []
        for c in range(self.columnCount()):
            it = self.item(row, c)
            parts.append(it.text() if it else "")
        return "\t".join(parts)

    def copy_rows(self) -> None:
        rows = sorted({i.row() for i in self.selectedIndexes()})
        if rows:
            QApplication.clipboard().setText("\n".join(self._row_text(r) for r in rows))

    def copy_cell(self, row: int, col: int) -> None:
        it = self.item(row, col)
        if it:
            QApplication.clipboard().setText(it.text())

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.matches(QKeySequence.StandardKey.Copy):
            self.copy_rows()
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e) -> None:  # noqa: N802
        idx = self.indexAt(e.pos())
        if not idx.isValid():
            return
        if not self.selectionModel().isRowSelected(idx.row(), idx.parent()):
            self.selectRow(idx.row())
        menu = QMenu(self)
        a_cell = menu.addAction(L("Copy cell", "Копировать ячейку"))
        a_row = menu.addAction(L("Copy row", "Копировать строку"))
        chosen = menu.exec(e.globalPos())
        if chosen is a_cell:
            self.copy_cell(idx.row(), idx.column())
        elif chosen is a_row:
            self.copy_rows()


def make_table(headers: List[str], stretch_col: int = 0, checkable: bool = False) -> QTableWidget:
    t = CopyTable(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setShowGrid(False)
    t.setWordWrap(False)
    t.horizontalHeader().setStretchLastSection(False)
    for i in range(len(headers)):
        t.horizontalHeader().setSectionResizeMode(
            i, QHeaderView.ResizeMode.Stretch if i == stretch_col else QHeaderView.ResizeMode.ResizeToContents)
    return t


def cell(text: str, align_right: bool = False, data=None, checkable: bool = False, checked: bool = False,
         tooltip: str = "") -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if data is not None:
        it.setData(Qt.ItemDataRole.UserRole, data)
    if checkable:
        it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
    if tooltip:
        it.setToolTip(tooltip)
    return it


class ProgressRow(QWidget):
    """Строка «текст + прогресс» внизу страницы."""

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.text = QLabel("")
        self.text.setObjectName("muted")
        self.bar = QProgressBar()
        self.bar.setFixedWidth(260)
        self.bar.setTextVisible(False)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.bar)
        self.bar.hide()

    def update_progress(self, text: str, i: int = 0, n: int = 0) -> None:
        self.text.setText(text)
        self.bar.show()
        if n:
            self.bar.setRange(0, n)
            self.bar.setValue(i)
        else:
            self.bar.setRange(0, 0)

    def finish(self, text: str = "") -> None:
        self.bar.hide()
        self.text.setText(text)


def ask(parent, title: str, text: str, yes: str = "", no: str = "") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    y = box.addButton(yes or L("Yes", "Да"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(no or L("Cancel", "Отмена"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is y


def info(parent, title: str, text: str, warn: bool = False) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if warn else QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(text)
    box.exec()


def choose_dir(parent, title: str = "") -> str:
    return QFileDialog.getExistingDirectory(parent, title or L("Choose folder", "Выберите папку"))


def open_path(path: str) -> None:
    import os
    import subprocess
    import sys
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def reveal(path: str) -> None:
    import os
    import subprocess
    import sys
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            open_path(os.path.dirname(path))
    except Exception:
        pass
