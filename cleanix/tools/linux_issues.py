"""Linux-аналог чистильщика реестра: битые ярлыки, ссылки, автозапуск, ассоциации."""
from __future__ import annotations

import os
import re
import shlex
import shutil
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ..core.i18n import T
from .issues import Category, Issue, IssueCtx


def _home(ctx: IssueCtx) -> Path:
    return Path(ctx.home or Path.home())


def _xdg_data(ctx: IssueCtx) -> Path:
    return Path(ctx.env.get("XDG_DATA_HOME") or _home(ctx) / ".local/share")


def _xdg_config(ctx: IssueCtx) -> Path:
    return Path(ctx.env.get("XDG_CONFIG_HOME") or _home(ctx) / ".config")


def parse_desktop(path: Path) -> dict:
    """Минимальный разбор секции [Desktop Entry]."""
    data = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    in_entry = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if in_entry and "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            data.setdefault(k.strip(), v.strip())
    return data


def exec_missing(exec_line: str, path_env: Optional[str] = None) -> Optional[str]:
    """Имя исполняемого файла, если он не найден; иначе None."""
    if not exec_line:
        return None
    try:
        parts = shlex.split(exec_line)
    except ValueError:
        return None
    while parts and ("=" in parts[0] and not parts[0].startswith("/")) or (parts and parts[0] == "env"):
        parts.pop(0)
    if not parts:
        return None
    exe = parts[0]
    if exe.startswith("%"):
        return None
    if os.path.isabs(exe):
        return None if os.path.exists(exe) else exe
    return None if shutil.which(exe, path=path_env) else exe


def scan_launchers(ctx: IssueCtx) -> List[Issue]:
    out = []
    d = _xdg_data(ctx) / "applications"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.desktop")):
        ctx.check_cancel()
        e = parse_desktop(p)
        if e.get("Type", "Application") != "Application" or e.get("TryExec") is None and "Exec" not in e:
            continue
        bad = exec_missing(e.get("TryExec") or "") or exec_missing(e.get("Exec", ""))
        if bad:
            out.append(Issue("launchers", "Launcher points to a missing program", bad, str(p), None, "file"))
    return out


def scan_autostart(ctx: IssueCtx) -> List[Issue]:
    out = []
    d = _xdg_config(ctx) / "autostart"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.desktop")):
        e = parse_desktop(p)
        bad = exec_missing(e.get("Exec", ""))
        if bad:
            out.append(Issue("autostart", "Autostart entry points to a missing program", bad, str(p), None, "file"))
    return out


def scan_symlinks(ctx: IssueCtx) -> List[Issue]:
    out = []
    home = _home(ctx)
    roots = [home / ".local/bin", home / "Desktop", _xdg_data(ctx) / "applications", _xdg_data(ctx) / "icons"]
    for root in roots:
        if not root.is_dir():
            continue
        depth0 = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            ctx.check_cancel()
            if len(Path(dirpath).parts) - depth0 >= 3:
                dirnames[:] = []
            for name in filenames + dirnames:
                p = os.path.join(dirpath, name)
                if os.path.islink(p) and not os.path.exists(p):
                    out.append(Issue("symlinks", "Broken symbolic link", os.readlink(p), p, None, "file"))
    return out


def scan_mimeapps(ctx: IssueCtx) -> List[Issue]:
    out = []
    f = _xdg_config(ctx) / "mimeapps.list"
    if not f.is_file():
        return out
    app_dirs = [_xdg_data(ctx) / "applications", Path("/usr/share/applications"), Path("/usr/local/share/applications"),
                Path("/var/lib/flatpak/exports/share/applications"), _xdg_data(ctx) / "flatpak/exports/share/applications"]
    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines()):
        if "=" not in line or line.startswith(("#", "[")):
            continue
        mime, _, apps = line.partition("=")
        for app in [a for a in apps.split(";") if a.strip().endswith(".desktop")]:
            if not any((d / app).exists() or any(d.rglob(app)) for d in app_dirs if d.is_dir()):
                out.append(Issue("mimeapps", "Association to an uninstalled application", f"{mime} → {app}",
                                 str(f), None, "line", {"mime": mime, "app": app}))
    return out


def scan_recent(ctx: IssueCtx) -> List[Issue]:
    out = []
    f = _xdg_data(ctx) / "recently-used.xbel"
    if not f.is_file():
        return out
    from urllib.parse import unquote, urlparse
    text = f.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r'<bookmark href="(file://[^"]+)"', text):
        path = unquote(urlparse(m.group(1)).path)
        if not os.path.exists(path):
            out.append(Issue("recent", "Recent file no longer exists", path, str(f), None, "line", {"href": m.group(1)}))
    return out


CATEGORIES: List[Category] = [
    Category("launchers", T("Broken Launchers", "Битые ярлыки приложений"), scan_launchers),
    Category("autostart", T("Orphan Autostart Entries", "Автозапуск несуществующих программ"), scan_autostart),
    Category("symlinks", T("Broken Symbolic Links", "Битые символические ссылки"), scan_symlinks),
    Category("mimeapps", T("Stale File Associations", "Устаревшие ассоциации файлов"), scan_mimeapps),
    Category("recent", T("Dead Recent-Files Entries", "Записи недавних файлов без файлов"), scan_recent),
]


PROBLEMS = {
    "launchers": T("Launcher points to a missing program", "Ярлык указывает на отсутствующую программу"),
    "autostart": T("Autostart entry points to a missing program", "Автозапуск указывает на отсутствующую программу"),
    "symlinks": T("Broken symbolic link", "Битая символическая ссылка"),
    "mimeapps": T("Association to an uninstalled application", "Ассоциация с удалённым приложением"),
    "recent": T("Recent file no longer exists", "Недавний файл больше не существует"),
}
for _c in CATEGORIES:
    _c.problem = PROBLEMS[_c.id]


def _backup(path: str, backup_dir: str) -> None:
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(path, os.path.join(backup_dir, f"{int(time.time())}-{os.path.basename(path)}"), follow_symlinks=False)


def fix(issues: List[Issue], backup_dir: Optional[str]) -> Tuple[int, List[str], int]:
    fixed, errors = 0, []
    lines_by_file = {}
    for i in issues:
        if i.kind == "file":
            try:
                if backup_dir and not os.path.islink(i.location):
                    _backup(i.location, backup_dir)
                os.unlink(i.location)
                fixed += 1
            except OSError as exc:
                errors.append(f"{i.location}: {exc.strerror or exc}")
        elif i.kind == "line":
            lines_by_file.setdefault(i.location, []).append(i)
    for path, group in lines_by_file.items():
        try:
            if backup_dir:
                _backup(path, backup_dir)
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            for i in group:
                if "href" in i.extra:
                    # удаляем целиком <bookmark ...>…</bookmark>
                    text, n = re.subn(r'\s*<bookmark href="%s".*?</bookmark>' % re.escape(i.extra["href"]), "", text, flags=re.S)
                    fixed += 1 if n else 0
                elif "app" in i.extra:
                    out_lines = []
                    for line in text.splitlines():
                        if line.startswith(i.extra["mime"] + "="):
                            mime, _, apps = line.partition("=")
                            kept = [a for a in apps.split(";") if a and a != i.extra["app"]]
                            if kept:
                                out_lines.append(mime + "=" + ";".join(kept) + ";")
                            continue
                        out_lines.append(line)
                    text = "\n".join(out_lines) + "\n"
                    fixed += 1
            Path(path).write_text(text, encoding="utf-8")
        except OSError as exc:
            errors.append(f"{path}: {exc.strerror or exc}")
    return fixed, errors, 0
