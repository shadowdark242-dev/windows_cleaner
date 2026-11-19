"""Цветовые темы и таблица стилей."""
from __future__ import annotations

LIGHT = dict(
    bg="#f4f7f6", panel="#ffffff", ribbon="#ffffff", tabbar="#e9efec", text="#1d2b27", muted="#6b7a75",
    accent="#0e9f6e", accent_dark="#0b7a55", accent_text="#ffffff", border="#d5deda", hover="#e3f3ec",
    selected="#d3eee2", danger="#d64545", warn="#c98a0b", row_alt="#f8faf9", header="#eef3f1",
)
DARK = dict(
    bg="#14181a", panel="#1c2124", ribbon="#1c2124", tabbar="#101315", text="#e4ece8", muted="#8a9a94",
    accent="#22c08a", accent_dark="#18a074", accent_text="#06241a", border="#2c3438", hover="#243a32",
    selected="#1f4a3a", danger="#ef6b6b", warn="#e0a93a", row_alt="#20262a", header="#232a2e",
)


# ----------------------------------------------------------------------
# Акцентный цвет
# ----------------------------------------------------------------------
import colorsys
import re

from ..core.i18n import T

PRESETS = [
    ("cleanix", T("Cleanix (emerald)", "Cleanix (изумрудный)"), "#0e9f6e"),
    ("coral", T("Coral (Airbnb)", "Коралловый (Airbnb)"), "#ff5a5f"),
    ("wise", T("Green (Wise)", "Зелёный (Wise)"), "#9fe870"),
    ("terracotta", T("Terracotta (Claude)", "Терракота (Claude)"), "#d97757"),
    ("violet", T("Violet (Linear, Stripe)", "Фиолетовый (Linear, Stripe)"), "#635bff"),
    ("blue", T("Blue (Coinbase)", "Синий (Coinbase)"), "#0052ff"),
    ("yellow", T("Yellow (Binance)", "Жёлтый (Binance)"), "#f0b90b"),
    ("teal", T("Teal", "Бирюзовый"), "#14b8a6"),
    ("mono", T("Black & white (Uber)", "Чёрно-белый (Uber)"), "#000000"),
]
DEFAULT_ACCENT = "cleanix"
_accent = [DEFAULT_ACCENT, "#7c3aed"]       # [id пресета или "custom", свой цвет]


def valid_hex(s: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", s or ""))


def set_accent(preset_id: str, custom: str = "") -> None:
    ids = {p[0] for p in PRESETS}
    _accent[0] = preset_id if preset_id in ids or preset_id == "custom" else DEFAULT_ACCENT
    if valid_hex(custom):
        _accent[1] = custom.lower()


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in rgb)


def _lum(h: str) -> float:
    def f(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """t=0 → a, t=1 → b."""
    return _hex(tuple(x * (1 - t) + y * t for x, y in zip(_rgb(a), _rgb(b))))


def _shift_lightness(h: str, delta: float) -> str:
    r, g, b = _rgb(h)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return _hex(colorsys.hls_to_rgb(hh, max(0.0, min(1.0, ll + delta)), ss))


def derive_accent(base: str, theme: str) -> dict:
    """Все производные цвета акцента с гарантией читаемости (контраст ≥ 4.5 для текста на заливке, ≥ 4.5 для текста на панели)."""
    panel = (DARK if theme == "dark" else LIGHT)["panel"]
    fill = base
    if _accent[0] == "mono":
        fill = "#f2f2f2" if theme == "dark" else "#111111"
    text = "#ffffff" if contrast(fill, "#ffffff") >= contrast(fill, "#111111") else "#111111"
    fg = fill                                            # цвет текста/иконок на светлой/тёмной панели
    step = -0.03 if theme != "dark" else 0.03
    for _ in range(40):
        if contrast(fg, panel) >= 4.5:
            break
        fg = _shift_lightness(fg, step)
    hover = _shift_lightness(fill, -0.07 if _lum(fill) > 0.1 else 0.12)
    sel_t, hov_t = (0.28, 0.14) if theme == "dark" else (0.22, 0.10)
    return dict(accent=fill, accent_text=text, accent_dark=fg, accent_hover=hover,
                selected=mix(panel, fill, sel_t), hover=mix(panel, fill, hov_t))


def current_base() -> str:
    if _accent[0] == "custom":
        return _accent[1]
    return next(p[2] for p in PRESETS if p[0] == _accent[0])


def palette(name: str) -> dict:
    base = dict(DARK if name == "dark" else LIGHT)
    base.update(derive_accent(current_base(), "dark" if name == "dark" else "light"))
    return base


def stylesheet(name: str, check: str = "", chevron: str = "") -> str:
    c = palette(name)
    chk = f"image: url({check});" if check else ""
    chev = f"image: url({chevron});" if chevron else ""
    return f"""
* {{ font-family: "Segoe UI", "Noto Sans", "Ubuntu", "DejaVu Sans", sans-serif; font-size: 13px; color: {c['text']}; }}
QMainWindow, QDialog, QWidget#root {{ background: {c['bg']}; }}
QWidget#page {{ background: {c['bg']}; }}
QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}

/* ---- верхняя панель вкладок (как в проводнике) ---- */
QWidget#titlebar {{ background: {c['tabbar']}; }}
QLabel#brand {{ font-size: 14px; font-weight: 600; color: {c['accent_dark']}; padding: 0 14px 0 8px; }}
QTabBar#maintabs {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar#maintabs::tab {{ padding: 7px 20px 8px 20px; margin: 4px 1px 0 1px; border: 1px solid transparent;
    border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; color: {c['muted']}; font-size: 13px; }}
QTabBar#maintabs::tab:hover {{ background: {c['hover']}; color: {c['text']}; }}
QTabBar#maintabs::tab:selected {{ background: {c['ribbon']}; color: {c['accent_dark']}; font-weight: 600;
    border-color: {c['border']}; }}
QFrame#ribbon {{ background: {c['ribbon']}; border-top: 1px solid {c['border']}; border-bottom: 1px solid {c['border']}; }}
QLabel#groupTitle {{ color: {c['muted']}; font-size: 11px; padding-bottom: 2px; }}
QFrame#sep {{ background: {c['border']}; max-width: 1px; min-width: 1px; }}
QToolButton#ribbonBtn {{ border: 1px solid transparent; border-radius: 6px; padding: 4px 8px 3px 8px; min-width: 58px;
    background: transparent; font-size: 12px; }}
QToolButton#ribbonBtn:hover {{ background: {c['hover']}; border-color: {c['border']}; }}
QToolButton#ribbonBtn:checked {{ background: {c['selected']}; border-color: {c['accent']}; }}
QToolButton#ribbonBtn:disabled {{ color: {c['muted']}; }}
QToolButton#ribbonBtn[primary="true"] {{ background: {c['accent']}; color: {c['accent_text']}; }}
QToolButton#ribbonBtn[primary="true"]:hover {{ background: {c['accent_hover']}; }}

/* ---- контент ---- */
QFrame#card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QLabel#h1 {{ font-size: 20px; font-weight: 600; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted {{ color: {c['muted']}; }}
QLabel#big {{ font-size: 26px; font-weight: 600; color: {c['accent_dark']}; }}
QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 16px; }}
QPushButton:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
QPushButton:disabled {{ color: {c['muted']}; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent']}; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {c['border']}; color: {c['muted']}; border-color: {c['border']}; }}
QPushButton#primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#danger {{ color: {c['danger']}; }}
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QPlainTextEdit, QTextEdit {{ background: {c['panel']}; border: 1px solid {c['border']};
    border-radius: 6px; padding: 5px 8px; selection-background-color: {c['accent']}; selection-color: {c['accent_text']}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ {chev} width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {c['panel']}; selection-background-color: {c['selected']}; selection-color: {c['text']}; }}
QTreeWidget, QTableWidget, QListWidget, QTreeView, QTableView {{ background: {c['panel']}; border: 1px solid {c['border']};
    border-radius: 8px; alternate-background-color: {c['row_alt']}; outline: 0; gridline-color: {c['border']}; }}
QTreeWidget::item, QListWidget::item {{ padding: 3px 2px; }}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['hover']}; }}
QHeaderView::section {{ background: {c['header']}; border: none; border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']}; padding: 6px 8px; font-weight: 600; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator {{ border: 1px solid {c['muted']}; border-radius: 4px; background: {c['panel']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; {chk} }}
QCheckBox::indicator:indeterminate {{ background: {c['accent']}; border-color: {c['accent']}; }}
QTreeView::indicator, QTableView::indicator, QListView::indicator {{ width: 16px; height: 16px; border: 1px solid {c['muted']}; border-radius: 4px; background: {c['panel']}; }}
QTreeView::indicator:checked, QTableView::indicator:checked, QListView::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; {chk} }}
QTreeView::indicator:indeterminate {{ background: {c['accent']}; border-color: {c['accent']}; }}
QProgressBar {{ border: 1px solid {c['border']}; border-radius: 6px; background: {c['panel']}; text-align: center; height: 16px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {c['tabbar']}; color: {c['muted']}; }}
QStatusBar::item {{ border: none; }}
QTabBar#subtabs::tab {{ padding: 6px 16px; border: none; border-bottom: 2px solid transparent; color: {c['muted']}; }}
QTabBar#subtabs::tab:selected {{ color: {c['accent_dark']}; border-bottom-color: {c['accent']}; font-weight: 600; }}
QTabBar#subtabs::tab:hover {{ color: {c['text']}; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {c['border']}; }}
QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 12px; padding: 12px 10px 8px 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {c['muted']}; }}
QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['selected']}; }}
"""
