"""Опции очистки Linux."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from ..core import fs
from ..core.engine import CleanItem, Ctx, Found, Group, ItemResult
from ..core.i18n import T
from . import helpers as H

GROUPS = [
    Group("lsystem", T("System", "Система"), "system", "linux", 10),
    Group("lprivacy", T("Privacy traces", "Следы активности"), "system", "linux", 20),
    Group("ladvanced", T("Advanced (root)", "Дополнительно (root)"), "system", "linux", 40),
]

EMPTY_XBEL = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<xbel version="1.0" xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks" '
    'xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info"/>\n'
)


def xdg(ctx: Ctx, var: str, default: str) -> Path:
    return Path(ctx.env.get(var) or ctx.home / default)


def _trash(ctx: Ctx):
    base = xdg(ctx, "XDG_DATA_HOME", ".local/share") / "Trash"
    yield from ctx.files(base / "files", prune=True)
    yield from ctx.files(base / "info")
    yield from ctx.files(base / "directorysizes")


def _trash_clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    from ..core.engine import delete_found
    delete_found(ctx, found, res)
    if not ctx.dry_run:
        base = xdg(ctx, "XDG_DATA_HOME", ".local/share") / "Trash" / "files"
        if base.is_dir():
            fs.prune_tree(str(base))


def _tmp(ctx: Ctx):
    dirs = ctx.tmp_dirs if ctx.tmp_dirs is not None else ["/tmp", "/var/tmp"]
    uid = os.getuid() if hasattr(os, "getuid") else -1
    for d in dirs:
        if not os.path.isdir(d):
            continue
        # верхний уровень: пропускаем скрытые каталоги (.X11-unix, .ICE-unix ...) и systemd-private-*
        for name in os.listdir(d):
            if name.startswith(".") or name.startswith("systemd-private-") or name.startswith("snap-private-tmp"):
                continue
            p = os.path.join(d, name)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if st.st_uid != uid:
                continue
            if os.path.isdir(p) and not os.path.islink(p):
                for f in ctx.files(p, respect_age=True):
                    f.root = d          # пустые подкаталоги убираем вплоть до самого /tmp
                    yield f
            elif os.path.isfile(p) or os.path.islink(p):
                if ctx.excluded(p) or ctx.now - st.st_mtime < ctx.min_age:
                    continue
                yield Found(p, 0 if os.path.islink(p) else st.st_size)


def _recent(ctx: Ctx):
    p = xdg(ctx, "XDG_DATA_HOME", ".local/share") / "recently-used.xbel"
    yield from ctx.file(p)


def _recent_clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    for f in found:
        if ctx.dry_run:
            res.removed_count += 1
            continue
        try:
            Path(f.path).write_text(EMPTY_XBEL, encoding="utf-8")
            res.removed_count += 1
            res.removed_size += f.size
        except OSError as exc:
            res.errors.append(f"{f.path}: {exc.strerror}")


def _thumbs(ctx: Ctx):
    yield from ctx.files(xdg(ctx, "XDG_CACHE_HOME", ".cache") / "thumbnails", prune=True)
    yield from ctx.files(ctx.home / ".thumbnails", prune=True)


def _clip(ctx: Ctx):
    return H.action_found("Clipboard")


def _history(ctx: Ctx):
    for n in (".bash_history", ".zsh_history", ".python_history", ".lesshst", ".viminfo", ".psql_history",
              ".mysql_history", ".sqlite_history", ".node_repl_history"):
        yield from ctx.file(ctx.home / n)
    yield from ctx.file(ctx.home / ".local/share/fish/fish_history")


def _xsession(ctx: Ctx):
    yield from ctx.glob(ctx.home, ".xsession-errors*")


def _fontcache(ctx: Ctx):
    yield from ctx.files(xdg(ctx, "XDG_CACHE_HOME", ".cache") / "fontconfig", prune=True)


def _shaders(ctx: Ctx):
    cache = xdg(ctx, "XDG_CACHE_HOME", ".cache")
    for d in ("mesa_shader_cache", "nvidia/GLCache", "nvidia/ComputeCache", "radv_builtin_shaders64"):
        yield from ctx.files(cache / d, prune=True)
    yield from ctx.files(ctx.home / ".nv/GLCache", prune=True)


def _crash(ctx: Ctx):
    yield from ctx.files(xdg(ctx, "XDG_CACHE_HOME", ".cache") / "sentry", prune=True)
    for base in ("/var/crash",):
        for f in ctx.files(base, ["*.crash", "*.upload", "*.uploaded"], recursive=False):
            try:
                if os.stat(f.path).st_uid == os.getuid():
                    yield f
            except OSError:
                pass


def _dns(ctx: Ctx):
    return H.action_found("DNS")


# --- root ---------------------------------------------------------------
def _journal(ctx: Ctx):
    for d in ("/var/log/journal", "/run/log/journal"):
        yield from ctx.files(d, ["*.journal", "*.journal~"])


def _journal_clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    if ctx.dry_run:
        res.removed_count += len(found)
        return
    if shutil.which("journalctl"):
        try:
            if H.run_cmd(["journalctl", "--rotate"], 30).returncode == 0 and \
               H.run_cmd(["journalctl", "--vacuum-size=16M"], 60).returncode == 0:
                res.removed_count += len(found)
                res.removed_size += sum(f.size for f in found)
                return
        except Exception as exc:
            res.errors.append(str(exc))
    res.errors.append("journalctl failed")


def _apt(ctx: Ctx):
    yield from ctx.files("/var/cache/apt/archives", ["*.deb"], recursive=False)
    yield from ctx.files("/var/cache/apt", ["pkgcache.bin", "srcpkgcache.bin"], recursive=False)
    yield from ctx.files("/var/cache/dnf", ["*.rpm"])
    yield from ctx.files("/var/cache/pacman/pkg", ["*.pkg.tar*"], recursive=False)


def _oldlogs(ctx: Ctx):
    yield from ctx.files("/var/log", ["*.gz", "*.xz", "*.bz2", "*.old", "*.[0-9]", "*.[0-9][0-9]"])


def _coredumps(ctx: Ctx):
    yield from ctx.files("/var/lib/systemd/coredump")
    yield from ctx.files("/var/crash", ["*.crash"], recursive=False)


ITEMS: List[CleanItem] = [
    CleanItem("lin.trash", "lsystem", T("Empty Trash", "Очистить корзину"), _trash, True, "linux", clean=_trash_clean, easy="temp"),
    CleanItem("lin.tmp", "lsystem", T("Temporary Files (/tmp)", "Временные файлы (/tmp)"), _tmp, True, "linux", easy="temp",
              note=T("Only your files older than the age limit", "Только ваши файлы старше заданного возраста")),
    CleanItem("lin.thumbs", "lsystem", T("Thumbnail Cache", "Кэш эскизов"), _thumbs, True, "linux", easy="temp"),
    CleanItem("lin.fonts", "lsystem", T("Font Cache", "Кэш шрифтов"), _fontcache, False, "linux"),
    CleanItem("lin.shaders", "lsystem", T("GPU Shader Cache", "Кэш шейдеров GPU"), _shaders, False, "linux"),
    CleanItem("lin.crash", "lsystem", T("Crash Reports", "Отчёты о сбоях"), _crash, True, "linux", easy="logs"),
    CleanItem("lin.xsession", "lsystem", T("X Session Errors Log", "Журнал ошибок X-сессии"), _xsession, True, "linux", easy="logs"),
    CleanItem("lin.dns", "lsystem", T("DNS Cache", "Кэш DNS"), _dns, False, "linux", clean=H.flush_dns),

    CleanItem("lin.clipboard", "lprivacy", T("Clipboard", "Буфер обмена"), _clip, True, "linux", clean=H.clear_clipboard, easy="traces"),
    CleanItem("lin.recent", "lprivacy", T("Recent Documents", "Недавние документы"), _recent, False, "linux", clean=_recent_clean, easy="traces"),
    CleanItem("lin.history", "lprivacy", T("Shell & tool history", "История командной строки и утилит"), _history, False, "linux"),

    CleanItem("lin.journal", "ladvanced", T("systemd Journal", "Журнал systemd"), _journal, False, "linux", admin=True, clean=_journal_clean),
    CleanItem("lin.apt", "ladvanced", T("Package Manager Cache", "Кэш менеджера пакетов"), _apt, False, "linux", admin=True),
    CleanItem("lin.oldlogs", "ladvanced", T("Rotated Logs", "Ротированные логи (/var/log)"), _oldlogs, False, "linux", admin=True),
    CleanItem("lin.coredumps", "ladvanced", T("Core Dumps", "Дампы памяти (core)"), _coredumps, False, "linux", admin=True),
]
