"""Прочие приложения (кросс-платформенные кэши и логи)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator, List

from ..core.engine import CleanItem, Ctx, Found, Group
from ..core.i18n import T

GROUPS = [
    Group("devtools", T("Developer tools", "Инструменты разработчика"), "apps", "all", 300),
    Group("apps_misc", T("Applications", "Приложения"), "apps", "all", 310),
    Group("office", T("Microsoft Office", "Microsoft Office"), "apps", "windows", 320),
]


def _paths(ctx: Ctx, win: List[tuple], lin: List[str]) -> List[Path]:
    out: List[Path] = []
    if ctx.windows:
        for env, *parts in win:
            p = ctx.env_path(env, *parts)
            if p is not None:
                out.append(p)
    else:
        out.extend(ctx.home / x for x in lin)
    return out


def dirs_scan(win: List[tuple], lin: List[str], respect_age: bool = False) -> Callable[[Ctx], Iterator[Found]]:
    def scan(ctx: Ctx) -> Iterator[Found]:
        for p in _paths(ctx, win, lin):
            yield from ctx.files(p, prune=True, respect_age=respect_age)
    return scan


def glob_dirs_scan(base_lin: str, pattern_sub: str) -> Callable[[Ctx], Iterator[Found]]:
    """~/base/*/sub — например, кэши flatpak-приложений."""
    def scan(ctx: Ctx) -> Iterator[Found]:
        if ctx.windows:
            return
        for d in ctx.profiles(ctx.home / base_lin):
            yield from ctx.files(d / pattern_sub, prune=True)
    return scan


ITEMS: List[CleanItem] = [
    # --- dev tools
    CleanItem("app.pip", "devtools", T("pip cache", "Кэш pip"),
              dirs_scan([("LOCALAPPDATA", "pip", "Cache")], [".cache/pip"]), True),
    CleanItem("app.npm", "devtools", T("npm cache", "Кэш npm"),
              dirs_scan([("LOCALAPPDATA", "npm-cache", "_cacache"), ("APPDATA", "npm-cache", "_cacache")], [".npm/_cacache"]), True),
    CleanItem("app.yarn", "devtools", T("Yarn cache", "Кэш Yarn"),
              dirs_scan([("LOCALAPPDATA", "Yarn", "Cache")], [".cache/yarn"]), False),
    CleanItem("app.cargo", "devtools", T("Cargo registry cache", "Кэш Cargo (скачанные crate)"),
              dirs_scan([], [".cargo/registry/cache"]), False,
              note=T("Will be downloaded again on next build", "При следующей сборке будет скачано заново")),
    CleanItem("app.vscode", "devtools", T("VS Code cache & logs", "Кэш и логи VS Code"),
              dirs_scan([("APPDATA", "Code", "Cache"), ("APPDATA", "Code", "CachedData"), ("APPDATA", "Code", "logs"),
                         ("APPDATA", "Code", "Code Cache"), ("APPDATA", "Code", "GPUCache")],
                        [".config/Code/Cache", ".config/Code/CachedData", ".config/Code/logs",
                         ".config/Code/Code Cache", ".config/Code/GPUCache"]), True),
    # --- misc
    CleanItem("app.discord", "apps_misc", T("Discord cache", "Кэш Discord"),
              dirs_scan([("APPDATA", "discord", "Cache"), ("APPDATA", "discord", "Code Cache"), ("APPDATA", "discord", "GPUCache")],
                        [".config/discord/Cache", ".config/discord/Code Cache", ".config/discord/GPUCache"]), True),
    CleanItem("app.steam", "apps_misc", T("Steam logs & web cache", "Логи и веб-кэш Steam"),
              dirs_scan([("ProgramFiles(x86)", "Steam", "logs"), ("ProgramFiles(x86)", "Steam", "appcache", "httpcache"),
                         ("LOCALAPPDATA", "Steam", "htmlcache")],
                        [".local/share/Steam/logs", ".local/share/Steam/appcache/httpcache",
                         ".steam/steam/logs", ".steam/steam/appcache/httpcache"]), True),
    CleanItem("app.spotify", "apps_misc", T("Spotify cache", "Кэш Spotify"),
              dirs_scan([("LOCALAPPDATA", "Spotify", "Storage"), ("LOCALAPPDATA", "Spotify", "Data")],
                        [".cache/spotify"]), False),
    CleanItem("app.telegram", "apps_misc", T("Telegram cache", "Кэш Telegram"),
              dirs_scan([("APPDATA", "Telegram Desktop", "tdata", "user_data", "cache"),
                         ("APPDATA", "Telegram Desktop", "tdata", "user_data", "media_cache")],
                        [".local/share/TelegramDesktop/tdata/user_data/cache",
                         ".local/share/TelegramDesktop/tdata/user_data/media_cache"]), False),
    # --- office (Windows)
    CleanItem("app.office.recent", "office", T("Recent files list", "Список недавних файлов"),
              dirs_scan([("APPDATA", "Microsoft", "Office", "Recent")], []), False),
    CleanItem("app.office.cache", "office", T("Office file cache", "Кэш файлов Office"),
              dirs_scan([("LOCALAPPDATA", "Microsoft", "Office", "16.0", "OfficeFileCache")], []), False),
]
