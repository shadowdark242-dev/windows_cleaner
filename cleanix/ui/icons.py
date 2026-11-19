"""Встроенные SVG-иконки (24×24, штриховые) без внешних файлов."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_BROOM = (
    '<path d="M21.1 .5c.8-.3 1.8 0 2.2.8.3.6.2 1.2-.1 1.8L19.6 9.3 16.9 8.1z"/>'
    '<path d="M13.1 10.3c.9-1.9 2.9-2.7 4.7-1.9l3.9 1.7c1.6.7 2.2 2.1 1.7 3.8l-.2.6z"/>'
    '<path d="M13.3 11.9 23 15.9c-.7 2.8-2.3 5.4-4.3 7.4-.4.4-1 .5-1.5.4-.7-.1-1.2-.1-1.9-.3l1.8-4.2-3.4 3.6c-1 .1-2-.1-3-.3L10.1 19 6.4 21.3C4.7 20.8 3.2 19.9 2 18.7c-.7-.7-.5-1.7.2-2.1 4.7-.4 8.4-1.5 11.1-4.7z"/>'
    '<circle cx="2.6" cy="4.6" r="2.2"/><circle cx="7.4" cy="5.6" r="1.5"/><circle cx="6.1" cy="11.3" r="2.5"/>')

_FILL = {"broom"}        # иконки-силуэты: заливка вместо контура

_P = {
    "broom": _BROOM,
    "sparkle": '<path d="M10 3C10.7 8.5 12.5 10.3 18 11C12.5 11.7 10.7 13.5 10 19C9.3 13.5 7.5 11.7 2 11C7.5 10.3 9.3 8.5 10 3Z"/><path d="M19 14C19.2 16 20 16.8 22 17C20 17.2 19.2 18 19 20C18.8 18 18 17.2 16 17C18 16.8 18.8 16 19 14Z"/>',
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
    if name in _FILL:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
                f'fill="{color}">{body}</svg>').encode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').encode()


def icon(name: str, color: str = "#1d2b27", size: int = 32) -> QIcon:
    ic = QIcon()
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


APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="8" fill="{bg}"/>'
    '<g transform="translate(6.6 6.2) scale(0.8)" fill="{fg}">' + _BROOM + '</g>'
    '</svg>')


def app_icon_pixmap(bg: str, fg: str = "#ffffff", size: int = 256) -> QPixmap:
    r = QSvgRenderer(QByteArray(APP_ICON_SVG.format(bg=bg, fg=fg).encode()))
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    return QPixmap.fromImage(img)


def app_icon() -> QIcon:
    """Иконка приложения: скруглённый квадрат цвета акцента с белой искрой."""
    from .theme import palette
    c = palette("light")
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon_pixmap(c["accent"], c["accent_text"], size))
    return ic
