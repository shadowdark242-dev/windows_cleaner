"""Встроенные SVG-иконки (24×24, штриховые) без внешних файлов."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_P = {
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
    "checkall": '<path d="M3 12l4 4 8-9"/><path d="M13 16l1.5 1.5L21 9"/>',
    "uncheck": '<rect x="4" y="4" width="16" height="16" rx="3"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 3-6.2"/><path d="M4 4v5h5"/>',
    "system": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "apps": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    "save": '<path d="M5 3h11l3 3v15H5z"/><path d="M8 3v6h7V3M8 21v-7h8v7"/>',
    "registry": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "tools": '<path d="M14.5 6.5a4 4 0 0 0-5 5L3.5 17.5a2 2 0 0 0 3 3l6-6a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z"/>',
    "settings": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
    "folder": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H10l2 2.5h7.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/>',
    "uninstall": '<path d="M4 8l8-4 8 4v8l-8 4-8-4z"/><path d="M4 8l8 4 8-4M12 12v8"/><path d="M9 6l6 3" />',
    "startup": '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
    "plugin": '<path d="M9 4h4v3a2 2 0 1 1 0 4v3h-3a2 2 0 1 0-4 0H4V8h3a2 2 0 1 1 2-4z"/><path d="M13 14v6h7v-6"/>',
    "disk": '<circle cx="12" cy="12" r="9"/><path d="M12 3v9h9"/><path d="M12 12l-6.4 6.4"/>',
    "duplicate": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "restore": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4v5h5"/><path d="M12 8v4.5l3 1.5"/>',
    "wiper": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.5-5.8"/><path d="M20 4v5h-5"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "remove": '<path d="M5 12h14"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "cookie": '<path d="M20.5 12.5A8.5 8.5 0 1 1 11.5 3.5a3.5 3.5 0 0 0 4 4 3.5 3.5 0 0 0 5 5z"/><path d="M9 10v.5M14 15v.5M8.5 15v.5"/>',
    "include": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H10l2 2.5h7.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/><path d="M12 11v6M9 14h6"/>',
    "exclude": '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "advanced": '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    "general": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 9h8M8 13h8M8 17h5"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5L16 9.5"/>',
    "open": '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "power": '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
    "tasks": '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9l2 2 3-3M8 16h8"/>',
    "services": '<circle cx="12" cy="12" r="3"/><path d="M12 3l1.5 2.5 3-.5.5 3 2.5 1.5-1.5 2.5 1.5 2.5-2.5 1.5-.5 3-3-.5L12 21l-1.5-2.5-3 .5-.5-3-2.5-1.5L6 12 4.5 9.5 7 8l.5-3 3 .5z"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "scan": '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M4 12h16"/>',
    "fix": '<path d="M14.5 6.5a4 4 0 0 0-5 5L3.5 17.5a2 2 0 0 0 3 3l6-6a4 4 0 0 0 5-5l-2.5 2.5-2.5-.5-.5-2.5z"/>',
}


def svg(name: str, color: str = "#1d2b27", size: int = 24) -> bytes:
    body = _P.get(name, _P["info"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


# Иконка метлы — Phosphor Icons ("broom", fill), лицензия MIT, см. THIRD_PARTY_NOTICES.md
_BROOM_PATH = (
    "M235.29,216.7C212.86,205.69,200,182.12,200,152V134.69a15.94,15.94,0,0,0-10.09-14.87l-28.65-11.46A8,8,0,0,1,156.79,98l22.32-56.67C184,28.79,178,14.21,165.34,9.51a24,24,0,0,0-30.7,13.71L112.25,80.08a8,8,0,0,1-10.41,4.5L73.11,73.08a15.91,15.91,0,0,0-17.38,3.66C34.68,98.4,24,123.71,24,152a111.53,111.53,0,0,0,31.15,77.53A8.06,8.06,0,0,0,61,232H232a8,8,0,0,0,8-7.51A8.21,8.21,0,0,0,235.29,216.7ZM115.11,216a87.52,87.52,0,0,1-24.26-41.71,8.21,8.21,0,0,0-9.25-6.18A8,8,0,0,0,75.28,178a105.33,105.33,0,0,0,18.36,38H64.44A95.62,95.62,0,0,1,40,152a85.92,85.92,0,0,1,7.73-36.3l137.8,55.13c3,18.06,10.55,33.5,21.89,45.19Z")


def broom_pixmap(color: str, size: int) -> QPixmap:
    """Метла нужного цвета и размера (прозрачный фон)."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="{size}" height="{size}">'
           f'<path fill="{color}" d="{_BROOM_PATH}"/></svg>')
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


def icon(name: str, color: str = "#1d2b27", size: int = 32) -> QIcon:
    ic = QIcon()
    if name == "broom":
        for c, mode in ((color, QIcon.Mode.Normal), ("#9aa7a2", QIcon.Mode.Disabled)):
            pm = broom_pixmap(c, size * 2)
            pm.setDevicePixelRatio(2)
            ic.addPixmap(pm, mode)
        return ic
    for scale_color, mode in ((color, QIcon.Mode.Normal), ("#9aa7a2", QIcon.Mode.Disabled)):
        r = QSvgRenderer(QByteArray(svg(name, scale_color)))
        img = QImage(size * 2, size * 2, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        r.render(p, QRectF(0, 0, size * 2, size * 2))
        p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(2)
        ic.addPixmap(pm, mode)
    return ic


def app_icon_pixmap(bg: str, fg: str = "#ffffff", size: int = 256) -> QPixmap:
    """Скруглённый квадрат цвета bg с метлой цвета fg."""
    out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.25, size * 0.25)
    inner = int(size * 0.62)
    off = (size - inner) // 2
    p.drawPixmap(off, off, broom_pixmap(fg, inner))
    p.end()
    return QPixmap.fromImage(out)


def app_icon() -> QIcon:
    """Иконка приложения: скруглённый квадрат цвета акцента с белой искрой."""
    from .theme import palette
    c = palette("light")
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon_pixmap(c["accent"], c["accent_text"], size))
    return ic
