"""Браузеры (Chromium-семейство и Firefox) — Windows и Linux."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator, List, Optional

from ..core.engine import CleanItem, Ctx, Found, Group
from ..core.i18n import T
from . import helpers as H

# id, имя, (Windows: env-переменная, подпуть), Linux: (config, cache), плоский ли профиль
CHROMIUM = [
    ("chrome", "Google Chrome", ("LOCALAPPDATA", "Google/Chrome/User Data"),
     (".config/google-chrome", ".cache/google-chrome"), False),
    ("chromium", "Chromium", ("LOCALAPPDATA", "Chromium/User Data"),
     (".config/chromium", ".cache/chromium"), False),
    ("edge", "Microsoft Edge", ("LOCALAPPDATA", "Microsoft/Edge/User Data"),
     (".config/microsoft-edge", ".cache/microsoft-edge"), False),
    ("brave", "Brave", ("LOCALAPPDATA", "BraveSoftware/Brave-Browser/User Data"),
     (".config/BraveSoftware/Brave-Browser", ".cache/BraveSoftware/Brave-Browser"), False),
    ("vivaldi", "Vivaldi", ("LOCALAPPDATA", "Vivaldi/User Data"),
     (".config/vivaldi", ".cache/vivaldi"), False),
    ("opera", "Opera", ("APPDATA", "Opera Software/Opera Stable"),
     (".config/opera", ".cache/opera"), True),
]

CACHE_DIRS = ["Cache", "Code Cache", "GPUCache", "Media Cache", "Service Worker/CacheStorage",
              "Service Worker/ScriptCache", "DawnCache", "GrShaderCache"]
HISTORY_FILES = ["History", "History-journal", "Visited Links", "Top Sites", "Top Sites-journal",
                 "Shortcuts", "Shortcuts-journal", "Network Action Predictor"]
COOKIE_FILES = ["Cookies", "Cookies-journal", "Network/Cookies", "Network/Cookies-journal"]
SESSION_FILES = ["Current Session", "Current Tabs", "Last Session", "Last Tabs"]
FORM_FILES = ["Web Data", "Web Data-journal"]
PASSWORD_FILES = ["Login Data", "Login Data-journal", "Login Data For Account", "Login Data For Account-journal"]


def chromium_roots(ctx: Ctx, spec) -> tuple[List[Path], List[Path], bool]:
    """(каталоги профилей, каталоги кэша, flat)."""
    _id, _name, win, lin, flat = spec
    if ctx.windows:
        base = ctx.env_path(win[0], *win[1].split("/"))
        cache_base = base
    else:
        base = ctx.home / lin[0]
        cache_base = ctx.home / lin[1]
        # snap
        if _id == "chromium" and not base.is_dir():
            snap = ctx.home / "snap/chromium/common/chromium"
            if snap.is_dir():
                base = cache_base = snap
    if base is None or not base.is_dir():
        return [], [], flat
    if flat:
        return [base], [cache_base], flat
    profs = [p for p in ctx.profiles(base) if p.name == "Default" or p.name.startswith("Profile ") or p.name == "Guest Profile"]
    cprofs = [cache_base / p.name for p in profs]
    return profs, cprofs, flat


def _chromium_scan(spec, kind: str) -> Callable[[Ctx], Iterator[Found]]:
    def scan(ctx: Ctx) -> Iterator[Found]:
        profs, cprofs, flat = chromium_roots(ctx, spec)
        if not profs:
            return
        for prof, cprof in zip(profs, cprofs):
            if kind == "cache":
                seen = set()
                for root in (prof, cprof):
                    for d in CACHE_DIRS:
                        p = root / d
                        if str(p) not in seen and p.is_dir():
                            seen.add(str(p))
                            yield from ctx.files(p, prune=True)
                if flat is False and prof != cprof:
                    for extra in ("ShaderCache", "GrShaderCache", "GraphiteDawnCache"):
                        yield from ctx.files(cprof.parent / extra, prune=True)
            elif kind == "history":
                for f in HISTORY_FILES:
                    yield from ctx.file(prof / f)
            elif kind == "cookies":
                for f in COOKIE_FILES:
                    yield from ctx.file(prof / f)
            elif kind == "session":
                for f in SESSION_FILES:
                    yield from ctx.file(prof / f)
                yield from ctx.files(prof / "Sessions", prune=True)
            elif kind == "forms":
                for f in FORM_FILES:
                    yield from ctx.file(prof / f)
            elif kind == "passwords":
                for f in PASSWORD_FILES:
                    yield from ctx.file(prof / f)
    return scan


def firefox_profiles(ctx: Ctx) -> List[tuple[Path, Optional[Path]]]:
    """[(каталог профиля, каталог кэша)]"""
    pairs: List[tuple[Path, Optional[Path]]] = []
    if ctx.windows:
        base = ctx.env_path("APPDATA", "Mozilla", "Firefox", "Profiles")
        cbase = ctx.env_path("LOCALAPPDATA", "Mozilla", "Firefox", "Profiles")
        for p in ctx.profiles(base):
            pairs.append((p, cbase / p.name if cbase else None))
    else:
        for base, cbase in (
            (ctx.home / ".mozilla/firefox", ctx.home / ".cache/mozilla/firefox"),
            (ctx.home / "snap/firefox/common/.mozilla/firefox", ctx.home / "snap/firefox/common/.cache/mozilla/firefox"),
            (ctx.home / ".var/app/org.mozilla.firefox/.mozilla/firefox", ctx.home / ".var/app/org.mozilla.firefox/cache/mozilla/firefox"),
        ):
            for p in ctx.profiles(base):
                if (p / "prefs.js").exists() or (p / "places.sqlite").exists():
                    pairs.append((p, cbase / p.name))
    return pairs


def _ff_scan(kind: str) -> Callable[[Ctx], Iterator[Found]]:
    def scan(ctx: Ctx) -> Iterator[Found]:
        for prof, cprof in firefox_profiles(ctx):
            if kind == "cache":
                for root in {str(prof), str(cprof) if cprof else ""}:
                    if not root:
                        continue
                    for d in ("cache2", "startupCache", "thumbnails", "OfflineCache", "jumpListCache"):
                        yield from ctx.files(Path(root) / d, prune=True)
            elif kind == "history":
                yield from ctx.file(prof / "places.sqlite")
            elif kind == "cookies":
                yield from ctx.file(prof / "cookies.sqlite")
            elif kind == "session":
                yield from ctx.file(prof / "sessionstore.jsonlz4")
                yield from ctx.files(prof / "sessionstore-backups", prune=True)
                yield from ctx.glob(prof, "recovery.*")
            elif kind == "forms":
                yield from ctx.file(prof / "formhistory.sqlite")
            elif kind == "passwords":
                yield from ctx.file(prof / "logins.json")
                yield from ctx.file(prof / "logins-backup.json")
    return scan


KINDS = [
    ("cache", T("Internet Cache", "Кэш браузера"), True, "browsers"),
    ("history", T("Internet History", "История посещений"), True, "traces"),
    ("cookies", T("Cookies", "Cookies"), True, ""),
    ("session", T("Session", "Сессия (открытые вкладки)"), True, "traces"),
    ("forms", T("Saved Form Information", "Сохранённые данные форм"), False, ""),
    ("passwords", T("Saved Passwords", "Сохранённые пароли"), False, ""),
]


def build(platform_filter: str = "all"):
    groups: List[Group] = []
    items: List[CleanItem] = []
    order = 100
    for spec in CHROMIUM:
        bid, bname = spec[0], spec[1]
        groups.append(Group(bid, T(bname), "apps", "all", order))
        order += 1
        for kind, label, default, easy in KINDS:
            items.append(CleanItem(
                f"br.{bid}.{kind}", bid, label, _chromium_scan(spec, kind), default,
                clean=H.clean_cookie_dbs if kind == "cookies" else None, easy=easy))
    groups.append(Group("firefox", T("Mozilla Firefox"), "apps", "all", order))
    for kind, label, default, easy in KINDS:
        clean = None
        if kind == "cookies":
            clean = H.clean_cookie_dbs
        elif kind == "history":
            clean = H.clean_firefox_history
        items.append(CleanItem(f"br.firefox.{kind}", "firefox", label, _ff_scan(kind), default, clean=clean, easy=easy))
    return groups, items


GROUPS, ITEMS = build()
