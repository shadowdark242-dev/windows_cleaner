"""Минимальная двуязычная локализация (ru / en)."""
from __future__ import annotations

import locale
from typing import Dict, Tuple

_lang = "en"


def detect_language() -> str:
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""  # type: ignore[attr-defined]
    except Exception:
        loc = ""
    return "ru" if loc.lower().startswith(("ru", "russian")) else "en"


def set_language(lang: str) -> None:
    global _lang
    _lang = detect_language() if lang == "auto" else (lang if lang in ("ru", "en") else "en")


def get_language() -> str:
    return _lang


class Text:
    """Лениво локализуемая строка: str(Text) зависит от текущего языка."""

    __slots__ = ("en", "ru")

    def __init__(self, en: str, ru: str | None = None):
        self.en = en
        self.ru = ru if ru is not None else en

    def __str__(self) -> str:
        return self.ru if _lang == "ru" else self.en

    def __repr__(self) -> str:
        return f"Text({self.en!r})"

    def __eq__(self, other) -> bool:
        return str(self) == str(other)

    def __hash__(self) -> int:
        return hash(self.en)


T = Text

_STRINGS: Dict[str, Tuple[str, str]] = {}


def register(strings: Dict[str, Tuple[str, str]]) -> None:
    _STRINGS.update(strings)


def tr(key: str, *args, **kwargs) -> str:
    pair = _STRINGS.get(key)
    if pair is None:
        text = key
    else:
        text = pair[1] if _lang == "ru" else pair[0]
    if args or kwargs:
        try:
            return text.format(*args, **kwargs)
        except Exception:
            return text
    return text


def human_size(n: float) -> str:
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ") if _lang == "ru" else ("B", "KB", "MB", "GB", "TB")
    n = float(n)
    for u in units:
        if abs(n) < 1024 or u == units[-1]:
            return f"{int(n)} {u}" if u == units[0] else f"{n:.1f} {u}".replace(".", "," if _lang == "ru" else ".")
        n /= 1024
    return str(n)


def L(en: str, ru: str) -> str:
    """Сразу разрешённая строка (для интерфейса, пересоздаваемого при смене языка)."""
    return ru if _lang == "ru" else en


register({
    "total": ("Total found", "Всего найдено"),
    "removed": ("Removed", "Удалено"),
    "errors": ("errors", "ошибок"),
})
