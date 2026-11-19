"""Список установленных программ и их удаление."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import List, Optional

from ..catalog.helpers import run_cmd
from ..core.engine import Ctx

CV = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"


@dataclass
class Program:
    name: str
    publisher: str = ""
    version: str = ""
    size: int = 0          # байт (0 — неизвестно)
    date: str = ""
    kind: str = ""         # reg | dpkg | rpm | pacman | flatpak | snap
    ident: str = ""        # пакет / ключ / app-id
    command: str = ""      # Windows: UninstallString
    icon_path: str = ""    # Windows: файл с иконкой (exe/ico); Linux: пусто, иконка берётся из темы по ident


# --------------------------- иконки -----------------------------------
def exe_from_command(cmd) -> str:
    """Путь к файлу из строки вида '"C:\\a b\\app.exe" /arg' или 'C:\\app.exe,0'. Пустая строка — не нашли."""
    import re
    if not isinstance(cmd, str) or not cmd.strip():
        return ""
    s = os.path.expandvars(cmd.strip())
    if s.startswith('"'):
        end = s.find('"', 1)
        s = s[1:end] if end > 0 else s[1:]
    else:
        m = re.match(r"(.+?\.(?:exe|ico|dll|icl))(?:[ ,/\"].*)?$", s, re.I)
        if m:
            s = m.group(1)
    s = re.sub(r",\s*-?\d+$", "", s).strip()
    return s


def find_icon_file(display_icon, install_location, uninstall_cmd) -> str:
    """Лучший файл-источник иконки: DisplayIcon → exe из InstallLocation → exe деинсталлятора."""
    cand = exe_from_command(display_icon)
    if cand and os.path.isfile(cand):
        return cand
    loc = exe_from_command(install_location) if isinstance(install_location, str) else ""
    if loc and os.path.isdir(loc):
        try:
            exes = sorted(f for f in os.listdir(loc) if f.lower().endswith(".exe") and not f.lower().startswith(("unins", "uninst", "setup")))
        except OSError:
            exes = []
        if exes:
            return os.path.join(loc, exes[0])
    cand = exe_from_command(uninstall_cmd)
    if cand and os.path.isfile(cand) and not os.path.basename(cand).lower().startswith("msiexec"):
        return cand
    return ""


# --------------------------- Windows ---------------------------------
def list_windows(ctx: Ctx) -> List[Program]:
    reg = ctx.registry
    out: List[Program] = []
    if reg is None:
        return out
    roots = [rf"HKEY_LOCAL_MACHINE\{CV}", r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
             rf"HKEY_CURRENT_USER\{CV}"]
    seen = set()
    for root in roots:
        for sub in reg.enum_keys(root):
            v = {n.lower(): d for n, d, _ in reg.enum_values(f"{root}\\{sub}")}
            name = v.get("displayname")
            if not isinstance(name, str) or not name.strip():
                continue
            if v.get("systemcomponent") == 1 or v.get("parentkeyname") or v.get("releasetype") in ("Update", "Security Update", "Hotfix"):
                continue
            cmd = v.get("uninstallstring")
            if not isinstance(cmd, str) or not cmd:
                continue
            key = (name, str(v.get("displayversion", "")))
            if key in seen:
                continue
            seen.add(key)
            size_kb = v.get("estimatedsize")
            d = str(v.get("installdate", ""))
            out.append(Program(
                name.strip(), str(v.get("publisher", "") or ""), str(v.get("displayversion", "") or ""),
                int(size_kb) * 1024 if isinstance(size_kb, int) else 0,
                f"{d[6:8]}.{d[4:6]}.{d[:4]}" if len(d) == 8 and d.isdigit() else "",
                "reg", f"{root}\\{sub}", cmd,
                find_icon_file(v.get("displayicon"), v.get("installlocation"), cmd)))
    return sorted(out, key=lambda p: p.name.lower())


# --------------------------- Linux -----------------------------------
def parse_dpkg(output: str, manual: Optional[set] = None) -> List[Program]:
    out = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        pkg = parts[0].split(":")[0]
        if manual is not None and pkg not in manual:
            continue
        size = int(parts[2]) * 1024 if len(parts) > 2 and parts[2].isdigit() else 0
        out.append(Program(pkg, parts[3] if len(parts) > 3 else "", parts[1], size, "", "dpkg", pkg))
    return out


def parse_rpm(output: str) -> List[Program]:
    out = []
    for line in output.splitlines():
        p = line.split("\t")
        if len(p) >= 2 and p[0] and not p[0].startswith("gpg-pubkey"):
            out.append(Program(p[0], p[3] if len(p) > 3 and p[3] != "(none)" else "", p[1],
                               int(p[2]) if len(p) > 2 and p[2].isdigit() else 0, "", "rpm", p[0]))
    return out


def parse_pacman(output: str) -> List[Program]:
    return [Program(p[0], "", p[1], 0, "", "pacman", p[0]) for p in (l.split() for l in output.splitlines()) if len(p) >= 2]


def parse_flatpak(output: str) -> List[Program]:
    out = []
    for line in output.splitlines():
        p = line.split("\t")
        if len(p) >= 2 and "." in p[1]:
            out.append(Program(p[0], "", p[2] if len(p) > 2 else "", 0, "", "flatpak", p[1]))
    return out


def parse_snap(output: str) -> List[Program]:
    out = []
    for line in output.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2 and p[0] not in ("core", "bare", "snapd") and not p[0].startswith(("core2", "gtk-common", "gnome-")):
            out.append(Program(p[0], p[4] if len(p) > 4 else "", p[1], 0, "", "snap", p[0]))
    return out


def _try(cmd: List[str]) -> str:
    if not shutil.which(cmd[0]):
        return ""
    try:
        r = run_cmd(cmd, 60)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def list_linux(ctx: Ctx) -> List[Program]:
    out: List[Program] = []
    if shutil.which("dpkg-query"):
        manual_txt = _try(["apt-mark", "showmanual"])
        manual = set(manual_txt.split()) if manual_txt else None
        out += parse_dpkg(_try(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Installed-Size}\t${Maintainer}\n"]), manual)
    elif shutil.which("rpm"):
        out += parse_rpm(_try(["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SIZE}\t%{VENDOR}\n"]))
    elif shutil.which("pacman"):
        out += parse_pacman(_try(["pacman", "-Qe"]))
    out += parse_flatpak(_try(["flatpak", "list", "--app", "--columns=name,application,version"]))
    out += parse_snap(_try(["snap", "list"]))
    return sorted(out, key=lambda p: p.name.lower())


def list_programs(ctx: Ctx) -> List[Program]:
    return list_windows(ctx) if ctx.windows else list_linux(ctx)


def msi_uninstall(cmd: str) -> str:
    """MsiExec.exe /I{GUID} открывает мастер изменения — заменяем на /X{GUID} (удаление)."""
    import re
    if re.match(r'^\s*"?msiexec(\.exe)?"?\s', cmd, re.I):
        return re.sub(r"(?i)(\s)/I(\s*\{)", r"\1/X\2", cmd, count=1)
    return cmd


def uninstall_command(p: Program) -> List[str] | str:
    """Команда удаления: строка (Windows, запускается через shell) или argv."""
    if p.kind == "reg":
        return msi_uninstall(p.command)
    if p.kind == "dpkg":
        return ["pkexec", "apt-get", "remove", "-y", p.ident]
    if p.kind == "rpm":
        return ["pkexec", "dnf", "remove", "-y", p.ident] if shutil.which("dnf") else ["pkexec", "zypper", "--non-interactive", "remove", p.ident]
    if p.kind == "pacman":
        return ["pkexec", "pacman", "-Rns", "--noconfirm", p.ident]
    if p.kind == "flatpak":
        return ["flatpak", "uninstall", "-y", p.ident]
    if p.kind == "snap":
        return ["pkexec", "snap", "remove", p.ident]
    raise ValueError(p.kind)


def run_uninstall(p: Program) -> None:
    import subprocess
    cmd = uninstall_command(p)
    if isinstance(cmd, str):
        subprocess.Popen(cmd, shell=True)       # Windows: запускаем штатный деинсталлятор
    else:
        subprocess.Popen(cmd)
