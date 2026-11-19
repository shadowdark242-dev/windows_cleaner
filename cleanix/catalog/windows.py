"""Опции очистки Windows."""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Iterator, List, Optional

from ..core.engine import CleanItem, Ctx, Found, Group, ItemResult, delete_found
from ..core.i18n import T
from . import helpers as H

HKCU = "HKEY_CURRENT_USER"
EXPLORER = HKCU + r"\Software\Microsoft\Windows\CurrentVersion\Explorer"

GROUPS = [
    Group("ie", T("Internet Explorer / Legacy Edge", "Internet Explorer / Edge Legacy"), "system", "windows", 10),
    Group("explorer", T("Windows Explorer", "Проводник Windows"), "system", "windows", 20),
    Group("system", T("System", "Система"), "system", "windows", 30),
    Group("advanced", T("Advanced", "Дополнительно"), "system", "windows", 40),
]


# ----------------------------------------------------------------------
# .lnk: цель ярлыка (для поиска «битых» ярлыков)
# ----------------------------------------------------------------------
def lnk_target(path: str) -> Optional[str]:
    """Локальный путь цели ярлыка или None, если определить нельзя."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(64 * 1024)
    except OSError:
        return None
    if len(data) < 0x4C or struct.unpack_from("<I", data, 0)[0] != 0x4C:
        return None
    flags = struct.unpack_from("<I", data, 0x14)[0]
    pos = 0x4C
    if flags & 0x1:  # HasLinkTargetIDList
        if pos + 2 > len(data):
            return None
        pos += 2 + struct.unpack_from("<H", data, pos)[0]
    if not flags & 0x2 or pos + 28 > len(data):  # HasLinkInfo
        return None
    info_flags = struct.unpack_from("<I", data, pos + 8)[0]
    if not info_flags & 0x1:
        return None
    off = struct.unpack_from("<I", data, pos + 16)[0]
    end = data.find(b"\0", pos + off)
    if end < 0:
        return None
    return data[pos + off:end].decode("mbcs" if os.name == "nt" else "latin-1", errors="replace")


def _broken_shortcuts(ctx: Ctx, roots: List[Optional[Path]]) -> Iterator[Found]:
    for root in roots:
        for f in ctx.files(root, ["*.lnk"]):
            target = lnk_target(f.path)
            if target and not target.startswith("\\\\") and not os.path.exists(target):
                yield f


# ----------------------------------------------------------------------
# Сканеры
# ----------------------------------------------------------------------
def _ie_cache(ctx: Ctx):
    local = "LOCALAPPDATA"
    for sub in (("Microsoft", "Windows", "INetCache"), ("Microsoft", "Windows", "Temporary Internet Files")):
        yield from ctx.files(ctx.env_path(local, *sub), prune=True)


def _ie_history(ctx: Ctx):
    yield from ctx.files(ctx.env_path("LOCALAPPDATA", "Microsoft", "Windows", "History"), prune=True)


def _ie_cookies(ctx: Ctx):
    yield from ctx.files(ctx.env_path("APPDATA", "Microsoft", "Windows", "Cookies"), prune=True)
    yield from ctx.files(ctx.env_path("LOCALAPPDATA", "Microsoft", "Windows", "INetCookies"), prune=True)


def _ie_typed(ctx: Ctx):
    yield from H.reg_values(ctx, HKCU + r"\Software\Microsoft\Internet Explorer\TypedURLs")
    yield from H.reg_values(ctx, HKCU + r"\Software\Microsoft\Internet Explorer\TypedURLsTime")


def _ie_index(ctx: Ctx):
    yield from ctx.files(ctx.env_path("LOCALAPPDATA", "Microsoft", "Windows"), ["index.dat"])
    yield from ctx.files(ctx.env_path("APPDATA", "Microsoft", "Windows", "Cookies"), ["index.dat"])


def _ie_lastdl(ctx: Ctx):
    reg = ctx.registry
    key = HKCU + r"\Software\Microsoft\Internet Explorer\Main"
    if reg and reg.get_value(key, "Download Directory"):
        yield Found(key, 0, "regvalue", extra="Download Directory")


def _ie_forms(ctx: Ctx):
    yield from H.reg_values(ctx, HKCU + r"\Software\Microsoft\Internet Explorer\IntelliForms\Storage2")


def _recent_docs(ctx: Ctx):
    yield from ctx.files(ctx.env_path("APPDATA", "Microsoft", "Windows", "Recent"), recursive=False)


def _run_mru(ctx: Ctx):
    yield from H.reg_values(ctx, EXPLORER + r"\RunMRU")


def _other_mru(ctx: Ctx):
    base = EXPLORER + r"\ComDlg32"
    yield from H.reg_values(ctx, base + r"\OpenSavePidlMRU", recursive=True)
    yield from H.reg_values(ctx, base + r"\LastVisitedPidlMRU", recursive=True)
    yield from H.reg_values(ctx, base + r"\LastVisitedMRU", recursive=True)
    yield from H.reg_values(ctx, EXPLORER + r"\TypedPaths")


def _thumbs(ctx: Ctx):
    base = ctx.env_path("LOCALAPPDATA", "Microsoft", "Windows", "Explorer")
    yield from ctx.files(base, ["thumbcache_*.db", "iconcache_*.db"], recursive=False)
    yield from ctx.file(ctx.env_path("LOCALAPPDATA", "IconCache.db"))


def _jumplists(ctx: Ctx):
    rec = ("Microsoft", "Windows", "Recent")
    yield from ctx.files(ctx.env_path("APPDATA", *rec, "AutomaticDestinations"))
    yield from ctx.files(ctx.env_path("APPDATA", *rec, "CustomDestinations"))


def _recycle_dirs(ctx: Ctx) -> List[Path]:
    drive = ctx.env.get("SystemDrive", "C:")
    out = [Path(drive + os.sep) / "$Recycle.Bin"]
    return out


def _recycle(ctx: Ctx):
    for d in _recycle_dirs(ctx):
        yield from ctx.files(d)


def _recycle_clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    if ctx.dry_run:
        res.removed_count += len(found)
        res.removed_size += sum(f.size for f in found)
        return
    try:
        import ctypes
        # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        rc = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)  # type: ignore[attr-defined]
        if rc in (0, 1):  # S_OK / S_FALSE (корзина уже пуста)
            res.removed_count += len(found)
            res.removed_size += sum(f.size for f in found)
            return
        res.errors.append(f"SHEmptyRecycleBin: 0x{rc & 0xFFFFFFFF:08x}")
    except Exception:
        delete_found(ctx, found, res)


def _temp(ctx: Ctx):
    seen = set()
    for key in ("TEMP", "TMP"):
        t = ctx.env.get(key)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            yield from ctx.files(t, respect_age=True, prune=True)
    yield from ctx.files(ctx.env_path("WINDIR", "Temp"), respect_age=True, prune=True)


def _memdumps(ctx: Ctx):
    yield from ctx.file(ctx.env_path("WINDIR", "MEMORY.DMP"))
    yield from ctx.files(ctx.env_path("WINDIR", "Minidump"))
    yield from ctx.files(ctx.env_path("WINDIR", "LiveKernelReports"), ["*.dmp"])
    yield from ctx.files(ctx.env_path("LOCALAPPDATA", "CrashDumps"))


def _chkdsk(ctx: Ctx):
    drive = Path(ctx.env.get("SystemDrive", "C:") + os.sep)
    yield from ctx.glob(drive, "*.chk")
    if drive.is_dir():
        for name in os.listdir(drive):
            if name.lower().startswith("found."):
                yield from ctx.files(drive / name, prune=True)


def _winlogs(ctx: Ctx):
    yield from ctx.files(ctx.env_path("WINDIR", "Logs"), ["*.log", "*.etl", "*.cab"])
    yield from ctx.files(ctx.env_path("WINDIR", "Panther"), ["*.log", "*.xml"])
    yield from ctx.files(ctx.env_path("WINDIR", "debug"), ["*.log"])
    yield from ctx.glob(ctx.env_path("WINDIR"), "*.log")


def _wer(ctx: Ctx):
    yield from ctx.files(ctx.env_path("PROGRAMDATA", "Microsoft", "Windows", "WER"), prune=True)
    yield from ctx.files(ctx.env_path("LOCALAPPDATA", "Microsoft", "Windows", "WER"), prune=True)


def _dns_scan(ctx: Ctx):
    return H.action_found("DNS")


def _clip_scan(ctx: Ctx):
    return H.action_found("Clipboard")


def _start_shortcuts(ctx: Ctx):
    yield from _broken_shortcuts(ctx, [
        ctx.env_path("APPDATA", "Microsoft", "Windows", "Start Menu"),
        ctx.env_path("PROGRAMDATA", "Microsoft", "Windows", "Start Menu"),
    ])


def _desktop_shortcuts(ctx: Ctx):
    yield from _broken_shortcuts(ctx, [ctx.home / "Desktop", ctx.env_path("PUBLIC", "Desktop")])


# --- advanced ---------------------------------------------------------
def _eventlogs_scan(ctx: Ctx):
    if os.name == "nt" and ctx.windows:
        try:
            out = H.run_cmd(["wevtutil", "el"], 30).stdout.splitlines()
        except Exception:
            out = []
        for name in out:
            if name.strip():
                yield Found(name.strip(), 0, "action")


def _eventlogs_clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    for f in found:
        ctx.check_cancel()
        if ctx.dry_run:
            res.removed_count += 1
            continue
        try:
            if H.run_cmd(["wevtutil", "cl", f.path], 30).returncode == 0:
                res.removed_count += 1
        except Exception as exc:
            res.errors.append(str(exc))


def _prefetch(ctx: Ctx):
    yield from ctx.files(ctx.env_path("WINDIR", "Prefetch"), ["*.pf"])


def _menuorder(ctx: Ctx):
    yield from H.reg_subkeys(ctx, EXPLORER + r"\MenuOrder")


def _tray(ctx: Ctx):
    key = HKCU + r"\Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\TrayNotify"
    reg = ctx.registry
    for name in ("IconStreams", "PastIconsStream"):
        if reg and reg.get_value(key, name):
            yield Found(key, 0, "regvalue", extra=name)


def _winsize(ctx: Ctx):
    base = HKCU + r"\Software\Microsoft\Windows"
    for key in (base + r"\Shell\Bags", base + r"\Shell\BagMRU",
                HKCU + r"\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\Bags",
                HKCU + r"\Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\BagMRU"):
        yield from H.reg_subkeys(ctx, key)


def _userassist(ctx: Ctx):
    base = EXPLORER + r"\UserAssist"
    reg = ctx.registry
    if reg is None:
        return
    for guid in reg.enum_keys(base):
        yield from H.reg_values(ctx, f"{base}\\{guid}\\Count")


# ----------------------------------------------------------------------
ITEMS: List[CleanItem] = [
    CleanItem("win.ie.cache", "ie", T("Temporary Internet Files", "Временные файлы Интернета"), _ie_cache, True, "windows", easy="browsers"),
    CleanItem("win.ie.history", "ie", T("History", "История"), _ie_history, True, "windows", easy="traces"),
    CleanItem("win.ie.cookies", "ie", T("Cookies", "Cookies"), _ie_cookies, True, "windows"),
    CleanItem("win.ie.typed", "ie", T("Recently Typed URLs", "Недавно введённые адреса"), _ie_typed, True, "windows", easy="traces"),
    CleanItem("win.ie.index", "ie", T("Index.dat files", "Файлы Index.dat"), _ie_index, True, "windows"),
    CleanItem("win.ie.lastdl", "ie", T("Last Download Location", "Последняя папка загрузки"), _ie_lastdl, True, "windows", easy="traces"),
    CleanItem("win.ie.forms", "ie", T("Autocomplete Form History", "История автозаполнения форм"), _ie_forms, False, "windows"),

    CleanItem("win.exp.recent", "explorer", T("Recent Documents", "Недавние документы"), _recent_docs, False, "windows"),
    CleanItem("win.exp.runmru", "explorer", T("Run (in Start Menu)", "Выполнить (в меню «Пуск»)"), _run_mru, True, "windows", easy="traces"),
    CleanItem("win.exp.mru", "explorer", T("Other Explorer MRUs", "Прочие списки Проводника"), _other_mru, False, "windows"),
    CleanItem("win.exp.thumbs", "explorer", T("Thumbnail Cache", "Кэш эскизов"), _thumbs, True, "windows", easy="temp"),
    CleanItem("win.exp.jump", "explorer", T("Taskbar Jump Lists", "Списки переходов панели задач"), _jumplists, True, "windows", easy="traces"),

    CleanItem("win.sys.recycle", "system", T("Empty Recycle Bin", "Очистить корзину"), _recycle, True, "windows", clean=_recycle_clean, easy="temp"),
    CleanItem("win.sys.temp", "system", T("Temporary Files", "Временные файлы"), _temp, True, "windows", easy="temp",
              note=T("Files younger than the age limit are skipped", "Файлы моложе заданного возраста пропускаются")),
    CleanItem("win.sys.clipboard", "system", T("Clipboard", "Буфер обмена"), _clip_scan, True, "windows", clean=H.clear_clipboard, easy="traces"),
    CleanItem("win.sys.dumps", "system", T("Memory Dumps", "Дампы памяти"), _memdumps, True, "windows", easy="logs"),
    CleanItem("win.sys.chkdsk", "system", T("Chkdsk File Fragments", "Фрагменты файлов Chkdsk"), _chkdsk, True, "windows", easy="temp"),
    CleanItem("win.sys.logs", "system", T("Windows Log Files", "Журналы Windows (файлы)"), _winlogs, True, "windows", easy="logs"),
    CleanItem("win.sys.wer", "system", T("Windows Error Reporting", "Отчёты об ошибках Windows"), _wer, False, "windows", easy="logs"),
    CleanItem("win.sys.dns", "system", T("DNS Cache", "Кэш DNS"), _dns_scan, False, "windows", clean=H.flush_dns),
    CleanItem("win.sys.startlnk", "system", T("Start Menu Shortcuts (broken)", "Ярлыки меню «Пуск» (битые)"), _start_shortcuts, False, "windows"),
    CleanItem("win.sys.desklnk", "system", T("Desktop Shortcuts (broken)", "Ярлыки рабочего стола (битые)"), _desktop_shortcuts, False, "windows"),

    CleanItem("win.adv.evtlogs", "advanced", T("Windows Event Logs", "Журналы событий Windows"), _eventlogs_scan, False, "windows", admin=True, clean=_eventlogs_clean),
    CleanItem("win.adv.prefetch", "advanced", T("Old Prefetch data", "Старые данные Prefetch"), _prefetch, False, "windows", admin=True),
    CleanItem("win.adv.menuorder", "advanced", T("Menu Order Cache", "Кэш порядка меню"), _menuorder, False, "windows"),
    CleanItem("win.adv.tray", "advanced", T("Tray Notifications Cache", "Кэш значков в трее"), _tray, False, "windows"),
    CleanItem("win.adv.winsize", "advanced", T("Window Size/Location Cache", "Кэш размеров и положения окон"), _winsize, False, "windows"),
    CleanItem("win.adv.userassist", "advanced", T("User Assist History", "История UserAssist"), _userassist, False, "windows"),
]
