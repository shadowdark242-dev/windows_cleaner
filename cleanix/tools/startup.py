"""Автозагрузка, планировщик, контекстное меню, службы — просмотр, отключение, удаление."""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..catalog.helpers import run_cmd
from ..core import registry as R
from ..core.engine import Ctx

TABS_WINDOWS = ["run", "tasks", "context", "services"]
TABS_LINUX = ["run", "tasks", "services"]

CV = r"SOFTWARE\Microsoft\Windows\CurrentVersion"


@dataclass
class Entry:
    tab: str
    name: str
    command: str = ""
    location: str = ""            # «ключ» в терминах CCleaner: HKCU:Run, autostart, cron ...
    publisher: str = ""
    enabled: Optional[bool] = True
    can_toggle: bool = True
    can_delete: bool = True
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    icon_path: str = ""           # файл с иконкой (Windows) / имя иконки из темы (Linux)


# ======================================================================
# Windows
# ======================================================================
def _approved_state(reg: R.RegistryBackend, key: str, name: str) -> bool:
    v = reg.get_value(key, name)
    if not v or not isinstance(v[0], (bytes, bytearray)) or not v[0]:
        return True
    return (v[0][0] & 1) == 0    # 02/06 — включено, 03/07 — отключено


def _icon_file(command: str) -> str:
    from .uninstall import exe_from_command
    p = exe_from_command(command)
    return p if p and os.path.isfile(p) else ""


def win_run_entries(ctx: Ctx) -> List[Entry]:
    reg = ctx.registry
    out: List[Entry] = []
    if reg is None:
        return out
    items = [
        ("HKCU:Run", rf"HKEY_CURRENT_USER\{CV}\Run", rf"HKEY_CURRENT_USER\{CV}\Explorer\StartupApproved\Run", True),
        ("HKLM:Run", rf"HKEY_LOCAL_MACHINE\{CV}\Run", rf"HKEY_LOCAL_MACHINE\{CV}\Explorer\StartupApproved\Run", True),
        ("HKLM:Run (32)", r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
         rf"HKEY_LOCAL_MACHINE\{CV}\Explorer\StartupApproved\Run32", True),
        ("HKCU:RunOnce", rf"HKEY_CURRENT_USER\{CV}\RunOnce", "", False),
        ("HKLM:RunOnce", rf"HKEY_LOCAL_MACHINE\{CV}\RunOnce", "", False),
    ]
    for loc, key, appr, toggle in items:
        for name, data, _t in reg.enum_values(key):
            if not name:
                continue
            out.append(Entry("run", name, str(data), loc, "", _approved_state(reg, appr, name) if appr else True,
                             toggle, True, "reg", {"key": key, "approved": appr}, _icon_file(str(data))))
    # папки автозагрузки
    for loc, base, appr in (
        ("Startup (user)", ctx.env_path("APPDATA", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
         rf"HKEY_CURRENT_USER\{CV}\Explorer\StartupApproved\StartupFolder"),
        ("Startup (all)", ctx.env_path("PROGRAMDATA", "Microsoft", "Windows", "Start Menu", "Programs", "StartUp"),
         rf"HKEY_LOCAL_MACHINE\{CV}\Explorer\StartupApproved\StartupFolder"),
    ):
        if base and base.is_dir():
            for f in sorted(base.iterdir()):
                if f.is_file() and f.name.lower() != "desktop.ini":
                    out.append(Entry("run", f.name, str(f), loc, "", _approved_state(reg, appr, f.name), True, True,
                                     "folder", {"path": str(f), "approved": appr}, str(f)))
    return out


def _approved_blob(enabled: bool) -> bytes:
    if enabled:
        return b"\x02\x00\x00\x00" + b"\x00" * 8
    ft = int((time.time() + 11644473600) * 10_000_000)
    return b"\x03\x00\x00\x00" + struct.pack("<Q", ft)


def _ps(script: str) -> str:
    from ..catalog.helpers import powershell
    return powershell(script)


def _json_list(text: str) -> List[dict]:
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def win_tasks(ctx: Ctx) -> List[Entry]:
    out = []
    script = ("Get-ScheduledTask | Where-Object {$_.TaskPath -notlike '\\Microsoft\\*'} | "
              "Select-Object TaskName,TaskPath,@{n='State';e={[string]$_.State}},@{n='Author';e={$_.Principal.UserId}},"
              "@{n='Action';e={($_.Actions | Select-Object -First 1).Execute}} | ConvertTo-Json -Compress")
    for t in _json_list(_ps(script)):
        full = f"{t.get('TaskPath', '')}{t.get('TaskName', '')}"
        out.append(Entry("tasks", t.get("TaskName", ""), t.get("Action") or "", t.get("TaskPath", "\\"), t.get("Author") or "",
                         t.get("State") != "Disabled", True, True, "task", {"full": full}))
    return out


def win_context(ctx: Ctx) -> List[Entry]:
    reg = ctx.registry
    out: List[Entry] = []
    if reg is None:
        return out
    blocked_key = rf"HKEY_LOCAL_MACHINE\{CV}\Shell Extensions\Blocked"
    blocked = {n.lower() for n, _d, _t in reg.enum_values(blocked_key)}
    for scope in ("*", "Directory", "Directory\\Background", "Folder", "AllFilesystemObjects", "Drive"):
        base = rf"HKEY_CLASSES_ROOT\{scope}\shellex\ContextMenuHandlers"
        for h in reg.enum_keys(base):
            v = reg.get_value(f"{base}\\{h}", "")
            clsid = v[0] if v and isinstance(v[0], str) else (h if h.startswith("{") else "")
            cmd = ""
            if clsid.startswith("{"):
                srv = reg.get_value(rf"HKEY_CLASSES_ROOT\CLSID\{clsid}\InprocServer32", "")
                cmd = srv[0] if srv else ""
            out.append(Entry("context", h, cmd, scope, "", clsid.lower() not in blocked if clsid else True,
                             bool(clsid.startswith("{")), True, "ctx", {"key": f"{base}\\{h}", "clsid": clsid}))
    return out


def win_services(ctx: Ctx) -> List[Entry]:
    out = []
    script = ("Get-CimInstance Win32_Service | Select-Object Name,DisplayName,StartMode,State,PathName,"
              "@{n='Pub';e={$_.StartName}} | ConvertTo-Json -Compress")
    for s in _json_list(_ps(script)):
        mode = s.get("StartMode", "")
        out.append(Entry("services", s.get("DisplayName") or s.get("Name", ""), s.get("PathName") or "", s.get("State", ""),
                         s.get("Pub") or "", mode != "Disabled", True, False, "svc",
                         {"name": s.get("Name"), "mode": mode}))
    return out


# ======================================================================
# Linux
# ======================================================================
def _desktop_fields(path: Path) -> Dict[str, str]:
    d: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return d
    sec = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            sec = s
        elif sec == "[Desktop Entry]" and "=" in s and not s.startswith("#"):
            k, _, v = s.partition("=")
            d.setdefault(k.strip(), v.strip())
    return d


def _set_desktop_key(text: str, key: str, value: Optional[str]) -> str:
    lines = text.splitlines()
    out, in_entry, done = [], False, False
    for line in lines:
        s = line.strip()
        if s.startswith("["):
            if in_entry and not done and value is not None:
                out.append(f"{key}={value}")
                done = True
            in_entry = s == "[Desktop Entry]"
        if in_entry and re.match(rf"^{re.escape(key)}\s*=", s):
            if value is not None and not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if in_entry and not done and value is not None:
        out.append(f"{key}={value}")
    return "\n".join(out) + "\n"


def autostart_dirs(ctx: Ctx):
    cfg = Path(ctx.env.get("XDG_CONFIG_HOME") or ctx.home / ".config")
    return cfg / "autostart", Path(ctx.env.get("XDG_CONFIG_DIRS", "/etc/xdg").split(":")[0]) / "autostart"


def lin_run(ctx: Ctx) -> List[Entry]:
    user_dir, sys_dir = autostart_dirs(ctx)
    entries: Dict[str, Entry] = {}
    for scope, d in (("system", sys_dir), ("user", user_dir)):   # пользовательские перекрывают системные
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.desktop")):
            e = _desktop_fields(f)
            hidden = e.get("Hidden", "false").lower() == "true" or e.get("X-GNOME-Autostart-enabled", "true").lower() == "false"
            entries[f.name] = Entry("run", e.get("Name") or f.stem, e.get("Exec", ""), f"autostart ({scope})", "",
                                    not hidden, True, True, "desktop", {"path": str(f), "scope": scope},
                                    e.get("Icon", ""))
    return sorted(entries.values(), key=lambda x: x.name.lower())


def lin_run_toggle(ctx: Ctx, e: Entry, enable: bool) -> None:
    user_dir, _ = autostart_dirs(ctx)
    src = Path(e.data["path"])
    dst = user_dir / src.name
    user_dir.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8", errors="replace")
    text = _set_desktop_key(text, "Hidden", None if enable else "true")
    text = _set_desktop_key(text, "X-GNOME-Autostart-enabled", None if enable else "false")
    dst.write_text(text, encoding="utf-8")
    e.data.update(path=str(dst), scope="user")
    e.enabled = enable


def lin_run_delete(ctx: Ctx, e: Entry) -> None:
    src = Path(e.data["path"])
    if e.data["scope"] == "user":
        src.unlink()
        # если есть системная запись — она вернётся, поэтому перекрываем Hidden
        sys_file = autostart_dirs(ctx)[1] / src.name
        if sys_file.exists():
            src.write_text("[Desktop Entry]\nType=Application\nHidden=true\n", encoding="utf-8")
    else:
        dst = autostart_dirs(ctx)[0] / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("[Desktop Entry]\nType=Application\nHidden=true\n", encoding="utf-8")


CRON_OFF = "#cleanix-off# "


def parse_crontab(text: str) -> List[Entry]:
    out = []
    for n, line in enumerate(text.splitlines()):
        s = line.strip()
        off = s.startswith(CRON_OFF)
        body = s[len(CRON_OFF):] if off else s
        if not body or body.startswith("#") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", body):
            continue
        parts = body.split(None, 5) if not body.startswith("@") else body.split(None, 1)
        need = 6 if not body.startswith("@") else 2
        if len(parts) < need:
            continue
        sched = " ".join(parts[:-1])
        cmd = parts[-1]
        out.append(Entry("tasks", cmd.split()[0].split("/")[-1], cmd, f"cron: {sched}", "", not off, True, True, "cron", {"line": n}))
    return out


def lin_tasks(ctx: Ctx) -> List[Entry]:
    out: List[Entry] = []
    if shutil.which("crontab"):
        r = run_cmd(["crontab", "-l"], 10)
        if r.returncode == 0:
            out += parse_crontab(r.stdout)
    if shutil.which("systemctl"):
        r = run_cmd(["systemctl", "--user", "list-unit-files", "--type=timer", "--no-legend", "--no-pager"], 15)
        for line in (r.stdout.splitlines() if r.returncode == 0 else []):
            p = line.split()
            if len(p) >= 2 and p[1] in ("enabled", "disabled"):
                out.append(Entry("tasks", p[0], "", "systemd --user", "", p[1] == "enabled", True, False, "timer",
                                 {"unit": p[0], "user": True}))
    return out


def parse_unit_files(text: str) -> List[Entry]:
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 2 and p[0].endswith(".service") and not p[0].endswith("@.service"):
            tog = p[1] in ("enabled", "disabled")
            out.append(Entry("services", p[0][:-8], "", p[1], "", p[1] in ("enabled", "static", "enabled-runtime"), tog, False,
                             "unit", {"unit": p[0], "state": p[1]}))
    return out


def lin_services(ctx: Ctx) -> List[Entry]:
    if not shutil.which("systemctl"):
        return []
    r = run_cmd(["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"], 20)
    return parse_unit_files(r.stdout) if r.returncode == 0 else []


def _sysctl(unit: str, verb: str, user: bool, ctx: Ctx) -> None:
    cmd = ["systemctl"] + (["--user"] if user else []) + [verb, unit]
    if not user and not ctx.admin:
        cmd = ["pkexec"] + cmd
    r = run_cmd(cmd, 60)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or f"systemctl {verb} failed")


def cron_rewrite(text: str, line_no: int, mode: str) -> str:
    lines = text.splitlines()
    s = lines[line_no]
    if mode == "off" and not s.startswith(CRON_OFF):
        lines[line_no] = CRON_OFF + s
    elif mode == "on" and s.startswith(CRON_OFF):
        lines[line_no] = s[len(CRON_OFF):]
    elif mode == "delete":
        del lines[line_no]
    return "\n".join(lines) + "\n"


def _cron_apply(e: Entry, mode: str) -> None:
    cur = run_cmd(["crontab", "-l"], 10).stdout
    new = cron_rewrite(cur, e.data["line"], mode)
    r = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or "crontab failed")


# ======================================================================
# Диспетчер
# ======================================================================
def tabs_for(ctx: Ctx) -> List[str]:
    return TABS_WINDOWS if ctx.windows else TABS_LINUX


def list_entries(ctx: Ctx, tab: str) -> List[Entry]:
    if ctx.windows:
        return {"run": win_run_entries, "tasks": win_tasks, "context": win_context, "services": win_services}[tab](ctx)
    return {"run": lin_run, "tasks": lin_tasks, "services": lin_services}[tab](ctx)


def set_enabled(ctx: Ctx, e: Entry, enable: bool) -> None:
    reg = ctx.registry
    if e.source in ("reg", "folder"):
        reg.set_value(e.data["approved"], e.name, _approved_blob(enable), R.REG_BINARY)
    elif e.source == "task":
        r = run_cmd(["schtasks", "/change", "/tn", e.data["full"], "/enable" if enable else "/disable"], 30)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or r.stdout.strip())
    elif e.source == "ctx":
        blocked = rf"HKEY_LOCAL_MACHINE\{CV}\Shell Extensions\Blocked"
        if enable:
            reg.delete_value(blocked, e.data["clsid"])
        else:
            reg.set_value(blocked, e.data["clsid"], "", R.REG_SZ)
    elif e.source == "svc":
        mode = "auto" if enable else "disabled"
        r = run_cmd(["sc", "config", e.data["name"], "start=", mode], 30)
        if r.returncode != 0:
            raise OSError(r.stdout.strip() or r.stderr.strip())
    elif e.source == "desktop":
        lin_run_toggle(ctx, e, enable)
    elif e.source == "cron":
        _cron_apply(e, "on" if enable else "off")
    elif e.source == "timer":
        _sysctl(e.data["unit"], "enable" if enable else "disable", True, ctx)
    elif e.source == "unit":
        _sysctl(e.data["unit"], "enable" if enable else "disable", False, ctx)
    else:
        raise ValueError(e.source)
    e.enabled = enable


def delete_entry(ctx: Ctx, e: Entry) -> None:
    reg = ctx.registry
    if e.source == "reg":
        reg.delete_value(e.data["key"], e.name)
        if e.data["approved"]:
            try:
                reg.delete_value(e.data["approved"], e.name)
            except OSError:
                pass
    elif e.source == "folder":
        os.unlink(e.data["path"])
    elif e.source == "task":
        r = run_cmd(["schtasks", "/delete", "/tn", e.data["full"], "/f"], 30)
        if r.returncode != 0:
            raise OSError(r.stderr.strip() or r.stdout.strip())
    elif e.source == "ctx":
        reg.delete_key(e.data["key"])
    elif e.source == "desktop":
        lin_run_delete(ctx, e)
    elif e.source == "cron":
        _cron_apply(e, "delete")
    else:
        raise ValueError("delete not supported")
