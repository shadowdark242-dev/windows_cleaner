"""Генерирует assets/cleanix.ico (иконка .exe) из векторной иконки приложения.

    QT_QPA_PLATFORM=offscreen python make_icon.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv)
from cleanix.ui.icons import app_icon_pixmap

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(out, exist_ok=True)
pm = app_icon_pixmap("#0a855c", "#ffffff", 256)
ok = pm.save(os.path.join(out, "cleanix.ico"), "ICO")
pm.save(os.path.join(out, "cleanix.png"), "PNG")
sys.exit(0 if ok else 1)
