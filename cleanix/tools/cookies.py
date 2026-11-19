"""Список доменов с куками (для настройки «Cookies to keep»)."""
from __future__ import annotations

import sqlite3
from typing import Dict, List

from ..catalog import browsers
from ..core.engine import Ctx


def _read_hosts(path: str, table: str, col: str) -> List[str]:
    try:
        uri = "file:" + path.replace("?", "%3f").replace("#", "%23") + "?mode=ro&immutable=1"
        con = sqlite3.connect(uri, uri=True, timeout=1)
        try:
            return [r[0] for r in con.execute(f"SELECT DISTINCT {col} FROM {table}") if r[0]]
        finally:
            con.close()
    except sqlite3.Error:
        return []


def list_cookie_domains(ctx: Ctx) -> Dict[str, int]:
    """{домен: число кук} по всем браузерам и профилям."""
    counts: Dict[str, int] = {}

    def add(hosts):
        for h in hosts:
            d = h.lstrip(".").lower()
            counts[d] = counts.get(d, 0) + 1

    for spec in browsers.CHROMIUM:
        profs, _c, _f = browsers.chromium_roots(ctx, spec)
        for prof in profs:
            for rel in ("Network/Cookies", "Cookies"):
                p = prof / rel
                if p.is_file():
                    add(_read_hosts(str(p), "cookies", "host_key"))
                    break
    for prof, _c in browsers.firefox_profiles(ctx):
        p = prof / "cookies.sqlite"
        if p.is_file():
            add(_read_hosts(str(p), "moz_cookies", "host"))
    return counts
