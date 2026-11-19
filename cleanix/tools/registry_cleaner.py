"""Чистильщик реестра Windows: поиск и исправление проблем с резервной копией."""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from ..core import registry as R
from ..core.i18n import T
from .issues import RISK_CAUTION, RISK_RISKY, Category, Issue, IssueCtx

HKLM, HKCU, HKCR = "HKEY_LOCAL_MACHINE", "HKEY_CURRENT_USER", "HKEY_CLASSES_ROOT"
CV = r"SOFTWARE\Microsoft\Windows\CurrentVersion"

_ENV_RE = re.compile(r"%([^%]+)%")


def expand(ctx: IssueCtx, s: str) -> str:
    env = {k.upper(): v for k, v in ctx.env.items()}
    return _ENV_RE.sub(lambda m: env.get(m.group(1).upper(), m.group(0)), s)


def extract_path(ctx: IssueCtx, raw) -> Optional[str]:
    """Достаёт путь к файлу из командной строки/значения. None — не похоже на файловый путь."""
    if not isinstance(raw, str):
        return None
    s = expand(ctx, raw.strip())
    if not s:
        return None
    if s.startswith('"'):
        end = s.find('"', 1)
        s = s[1:end] if end > 0 else s[1:]
    else:
        # c:\dir with spaces\app.exe /arg  — берём самый длинный существующий префикс или до первого .exe/.dll
        m = re.match(r"(.+?\.(?:exe|dll|ocx|sys|tlb|hlp|chm|ttf|otf|ttc|fon|wav|mp3|cpl|scr|bat|cmd|com|msc|ax))(?:[ ,/\"].*)?$", s, re.I)
        if m:
            s = m.group(1)
    s = s.strip().rstrip(",")
    if s.startswith("\\??\\"):
        s = s[4:]
    # ресурсы вида file.dll,-123 / file.exe,0
    s = re.sub(r",\s*-?\d+$", "", s)
    is_abs = bool(re.match(r"^[A-Za-z]:[\\/]", s)) or (os.sep == "/" and s.startswith("/"))  # posix — для тестов
    if not is_abs:
        return None
    if s.startswith("\\\\"):
        return None   # сетевые пути не проверяем
    return s


def missing(ctx: IssueCtx, raw) -> Optional[str]:
    """Путь, если он явно отсутствует; иначе None."""
    p = extract_path(ctx, raw)
    if p is None:
        return None
    return None if os.path.exists(p) else p


def _vals(ctx: IssueCtx, key: str):
    return ctx.reg.enum_values(key) if ctx.reg else []


# ----------------------------------------------------------------------
def scan_shared_dlls(ctx: IssueCtx) -> List[Issue]:
    key = rf"{HKLM}\{CV}\SharedDLLs"
    out = []
    for name, data, _t in _vals(ctx, key):
        ctx.check_cancel()
        p = missing(ctx, name)
        if p:
            out.append(Issue("shared_dlls", "Missing shared DLL", p, key, name, "regvalue"))
    return out


def scan_extensions(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\SOFTWARE\Classes", rf"{HKCU}\SOFTWARE\Classes"):
        for sub in ctx.reg.enum_keys(root):
            if not sub.startswith("."):
                continue
            ctx.check_cancel()
            key = rf"{root}\{sub}"
            prog = ctx.reg.get_value(key, "")
            if not prog or not isinstance(prog[0], str) or not prog[0]:
                continue
            progid = prog[0]
            if ctx.reg.key_exists(rf"{HKLM}\SOFTWARE\Classes\{progid}") or ctx.reg.key_exists(rf"{HKCU}\SOFTWARE\Classes\{progid}"):
                continue
            # есть другие сведения об ассоциации — не трогаем
            if ctx.reg.enum_keys(key):
                continue
            out.append(Issue("extensions", "Unused file extension", f"{sub} → {progid}", key, None, "regkey"))
    return out


def scan_activex(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\SOFTWARE\Classes\CLSID", rf"{HKCU}\SOFTWARE\Classes\CLSID"):
        for guid in ctx.reg.enum_keys(root):
            ctx.check_cancel()
            key = rf"{root}\{guid}"
            subs = [s for s in ctx.reg.enum_keys(key)]
            servers = [s for s in subs if s.lower() in ("inprocserver32", "localserver32")]
            if not servers:
                continue
            bad = []
            for s in servers:
                val = ctx.reg.get_value(rf"{key}\{s}", "")
                p = missing(ctx, val[0]) if val else None
                bad.append(p)
            # проблема, только если ВСЕ серверы указывают в никуда
            if all(bad):
                out.append(Issue("activex", "Invalid COM/ActiveX class", bad[0] or "", key, None, "regkey"))
    return out


def scan_typelibs(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\SOFTWARE\Classes\TypeLib", rf"{HKCU}\SOFTWARE\Classes\TypeLib"):
        for guid in ctx.reg.enum_keys(root):
            ctx.check_cancel()
            for ver in ctx.reg.enum_keys(rf"{root}\{guid}"):
                for lcid in ctx.reg.enum_keys(rf"{root}\{guid}\{ver}"):
                    for arch in ("win32", "win64"):
                        k = rf"{root}\{guid}\{ver}\{lcid}\{arch}"
                        val = ctx.reg.get_value(k, "")
                        p = missing(ctx, val[0]) if val else None
                        if p:
                            out.append(Issue("typelibs", "Missing type library", p, k, None, "regkey"))
    return out


def scan_applications(ctx: IssueCtx) -> List[Issue]:
    out = []
    root = rf"{HKLM}\SOFTWARE\Classes\Applications"
    for app in ctx.reg.enum_keys(root):
        ctx.check_cancel()
        k = rf"{root}\{app}\shell\open\command"
        val = ctx.reg.get_value(k, "")
        p = missing(ctx, val[0]) if val else None
        if p:
            out.append(Issue("applications", "Missing application", p, rf"{root}\{app}", None, "regkey"))
    return out


def scan_fonts(ctx: IssueCtx) -> List[Issue]:
    key = rf"{HKLM}\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    fonts_dir = os.path.join(ctx.env.get("WINDIR") or ctx.env.get("SystemRoot") or "C:\\Windows", "Fonts")
    out = []
    for name, data, _t in _vals(ctx, key):
        if not isinstance(data, str) or not data:
            continue
        path = data if re.match(r"^[A-Za-z]:", data) else os.path.join(fonts_dir, data)
        if not os.path.exists(expand(ctx, path)):
            out.append(Issue("fonts", "Missing font file", path, key, name, "regvalue"))
    return out


def scan_app_paths(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\{CV}\App Paths", rf"{HKCU}\{CV}\App Paths"):
        for app in ctx.reg.enum_keys(root):
            ctx.check_cancel()
            val = ctx.reg.get_value(rf"{root}\{app}", "")
            p = missing(ctx, val[0]) if val else None
            if p:
                out.append(Issue("app_paths", "Invalid application path", p, rf"{root}\{app}", None, "regkey"))
    return out


def scan_help(ctx: IssueCtx) -> List[Issue]:
    out = []
    for key in (rf"{HKLM}\{CV}\Help", rf"{HKLM}\{CV}\Controls Folder\Help"):
        for name, data, _t in _vals(ctx, key):
            if isinstance(data, str) and re.match(r"^[A-Za-z]:", data):
                full = os.path.join(expand(ctx, data), name) if not name.lower().endswith((".hlp", ".chm")) else os.path.join(expand(ctx, data), name)
                if not os.path.isdir(expand(ctx, data)):
                    out.append(Issue("help", "Missing help file", full, key, name, "regvalue"))
    return out


def scan_installer(ctx: IssueCtx) -> List[Issue]:
    key = rf"{HKLM}\{CV}\Installer\Folders"
    out = []
    for name, data, _t in _vals(ctx, key):
        if re.match(r"^[A-Za-z]:[\\/]", name) and not os.path.isdir(expand(ctx, name)):
            out.append(Issue("installer", "Missing installer folder", name, key, name, "regvalue"))
    return out


def scan_obsolete(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\{CV}\Uninstall", rf"{HKLM}\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                 rf"{HKCU}\{CV}\Uninstall"):
        for app in ctx.reg.enum_keys(root):
            ctx.check_cancel()
            key = rf"{root}\{app}"
            vals = {n.lower(): d for n, d, _t in ctx.reg.enum_values(key)}
            if vals.get("systemcomponent") == 1 or vals.get("windowsinstaller") == 1 or not vals.get("displayname"):
                continue
            us = vals.get("uninstallstring")
            if not isinstance(us, str) or not us or us.lower().startswith("msiexec"):
                continue
            p = missing(ctx, us)
            if p:
                out.append(Issue("obsolete", "Obsolete software entry", f"{vals.get('displayname')}  ({p})", key, None, "regkey"))
    return out


def scan_startup(ctx: IssueCtx) -> List[Issue]:
    out = []
    for root in (rf"{HKLM}\{CV}\Run", rf"{HKCU}\{CV}\Run", rf"{HKLM}\{CV}\RunOnce", rf"{HKCU}\{CV}\RunOnce",
                 rf"{HKLM}\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"):
        for name, data, _t in _vals(ctx, root):
            p = missing(ctx, data)
            if p:
                out.append(Issue("startup", "Startup entry points to missing file", p, root, name, "regvalue"))
    return out


def scan_menu_order(ctx: IssueCtx) -> List[Issue]:
    out = []
    base = rf"{HKCU}\{CV}\Explorer\MenuOrder\Start Menu2"
    starts = [os.path.join(expand(ctx, ctx.env.get("APPDATA", "")), "Microsoft", "Windows", "Start Menu"),
              os.path.join(expand(ctx, ctx.env.get("PROGRAMDATA", "")), "Microsoft", "Windows", "Start Menu")]
    if not ctx.env.get("APPDATA") and not ctx.env.get("PROGRAMDATA"):
        return out

    def walk(key: str, rel: str):
        for sub in ctx.reg.enum_keys(key):
            r = os.path.join(rel, sub) if rel else sub
            if not any(os.path.isdir(os.path.join(s, r)) for s in starts):
                out.append(Issue("menu_order", "Stale Start menu ordering", r, f"{key}\\{sub}", None, "regkey"))
            else:
                walk(f"{key}\\{sub}", r)

    walk(base, "")
    return out


def scan_mui(ctx: IssueCtx) -> List[Issue]:
    key = rf"{HKCU}\SOFTWARE\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache"
    out = []
    for name, data, _t in _vals(ctx, key):
        base = re.sub(r"\.(FriendlyAppName|ApplicationCompany)$", "", name)
        p = missing(ctx, base)
        if p:
            out.append(Issue("mui", "Stale MUI cache entry", p, key, name, "regvalue"))
    return out


def scan_sounds(ctx: IssueCtx) -> List[Issue]:
    out = []
    root = rf"{HKCU}\AppEvents\Schemes\Apps"
    for app in ctx.reg.enum_keys(root):
        for ev in ctx.reg.enum_keys(rf"{root}\{app}"):
            for scheme in ctx.reg.enum_keys(rf"{root}\{app}\{ev}"):
                k = rf"{root}\{app}\{ev}\{scheme}"
                val = ctx.reg.get_value(k, "")
                if val and isinstance(val[0], str) and val[0]:
                    p = missing(ctx, val[0])
                    if p:
                        out.append(Issue("sounds", "Missing sound file", p, k, "", "regvalue"))
    return out


def scan_services(ctx: IssueCtx) -> List[Issue]:
    out = []
    root = rf"{HKLM}\SYSTEM\CurrentControlSet\Services"
    for svc in ctx.reg.enum_keys(root):
        ctx.check_cancel()
        vals = {n.lower(): d for n, d, _t in ctx.reg.enum_values(rf"{root}\{svc}")}
        typ = vals.get("type")
        img = vals.get("imagepath")
        if typ not in (0x10, 0x20) or not isinstance(img, str):   # только пользовательские Win32-службы
            continue
        p = missing(ctx, img)
        win = (ctx.env.get("WINDIR") or "C:\\Windows").lower()
        if p and not p.lower().startswith(win):
            out.append(Issue("services", "Service executable is missing", f"{svc} → {p}", rf"{root}\{svc}", None, "regkey"))
    return out


CATEGORIES: List[Category] = [
    Category("shared_dlls", T("Missing Shared DLLs", "Отсутствующие общие DLL"), scan_shared_dlls),
    Category("extensions", T("Unused File Extensions", "Неиспользуемые расширения файлов"), scan_extensions, RISK_CAUTION),
    Category("activex", T("ActiveX and Class Issues", "ActiveX и классы COM"), scan_activex, RISK_RISKY),
    Category("typelibs", T("Type Libraries", "Библиотеки типов"), scan_typelibs, RISK_CAUTION),
    Category("applications", T("Applications", "Приложения"), scan_applications),
    Category("fonts", T("Fonts", "Шрифты"), scan_fonts),
    Category("app_paths", T("Application Paths", "Пути приложений"), scan_app_paths),
    Category("help", T("Help Files", "Файлы справки"), scan_help),
    Category("installer", T("Installer", "Установщик"), scan_installer, RISK_CAUTION),
    Category("obsolete", T("Obsolete Software", "Устаревшее ПО"), scan_obsolete, RISK_CAUTION),
    Category("startup", T("Run At Startup", "Автозапуск"), scan_startup),
    Category("menu_order", T("Start Menu Ordering", "Порядок меню «Пуск»"), scan_menu_order),
    Category("mui", T("MUI Cache", "Кэш MUI"), scan_mui),
    Category("sounds", T("Sound Events", "Звуковые события"), scan_sounds),
    Category("services", T("Windows Services", "Службы Windows"), scan_services, RISK_RISKY),
]


PROBLEMS = {
    "shared_dlls": T("Missing shared DLL", "Общая DLL отсутствует"),
    "extensions": T("Unused file extension", "Неиспользуемое расширение файла"),
    "activex": T("Invalid COM/ActiveX class", "Недействительный класс COM/ActiveX"),
    "typelibs": T("Missing type library", "Библиотека типов отсутствует"),
    "applications": T("Missing application", "Приложение отсутствует"),
    "fonts": T("Missing font file", "Файл шрифта отсутствует"),
    "app_paths": T("Invalid application path", "Неверный путь приложения"),
    "help": T("Missing help file", "Файл справки отсутствует"),
    "installer": T("Missing installer folder", "Папка установщика отсутствует"),
    "obsolete": T("Obsolete software entry", "Запись об удалённой программе"),
    "startup": T("Startup entry points to missing file", "Автозапуск указывает на отсутствующий файл"),
    "menu_order": T("Stale Start menu ordering", "Устаревший порядок меню «Пуск»"),
    "mui": T("Stale MUI cache entry", "Устаревшая запись кэша MUI"),
    "sounds": T("Missing sound file", "Звуковой файл отсутствует"),
    "services": T("Service executable is missing", "Исполняемый файл службы отсутствует"),
}
for _c in CATEGORIES:
    _c.problem = PROBLEMS[_c.id]


# ----------------------------------------------------------------------
# Исправление
# ----------------------------------------------------------------------
def fix(issues: List[Issue], reg: R.RegistryBackend, backup_path: Optional[str]) -> Tuple[int, List[str], int]:
    """Делает .reg-бэкап затронутых ключей и удаляет проблемные значения/ключи.

    Возвращает (исправлено, ошибки, отказано_в_доступе). Если бэкап создать не удалось — ничего не меняем.
    Защищённые ключи (отказ в доступе) не считаются ошибкой: они просто пропускаются.
    """
    todo = [i for i in issues if i.kind in ("regkey", "regvalue")]
    if backup_path:
        keys = [i.location for i in todo]
        try:
            R.write_reg_file(reg, keys, backup_path)
        except OSError as exc:
            return 0, [f"backup failed: {exc}"], 0
    fixed, errors, denied = 0, [], 0
    for i in todo:
        try:
            if i.kind == "regkey":
                reg.delete_key(i.location)
            else:
                reg.delete_value(i.location, i.value_name or "")
            fixed += 1
        except PermissionError:
            denied += 1
        except OSError as exc:
            errors.append(f"{i.location}: {exc}")
    return fixed, errors, denied
