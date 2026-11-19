"""Точки восстановления: Windows System Restore, Linux Timeshift / Snapper."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from ..catalog.helpers import run_cmd
from ..core.engine import Ctx


@dataclass
class RestorePoint:
    ident: str
    description: str
    date: str
    kind: str = ""


def backend_name(ctx: Ctx) -> Optional[str]:
    if ctx.windows:
        return "windows"
    if shutil.which("timeshift"):
        return "timeshift"
    if shutil.which("snapper"):
        return "snapper"
    return None


def parse_timeshift(text: str) -> List[RestorePoint]:
    out = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+>\s+(\S+)\s+(\S+)\s+(\S*)\s*(.*)$", line)
        if m:
            out.append(RestorePoint(m.group(2), m.group(5).strip(), m.group(2), m.group(3)))
    return out


def parse_snapper(text: str) -> List[RestorePoint]:
    out = []
    for line in text.splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) >= 7 and p[0].isdigit() and p[0] != "0":
            out.append(RestorePoint(p[0], p[6], p[3], p[1]))
    return out


def list_points(ctx: Ctx) -> List[RestorePoint]:
    b = backend_name(ctx)
    if b == "windows":
        script = ("Get-ComputerRestorePoint | Select-Object SequenceNumber,Description,"
                  "@{n='Date';e={[Management.ManagementDateTimeConverter]::ToDateTime($_.CreationTime).ToString('yyyy-MM-dd HH:mm')}},"
                  "@{n='Type';e={$_.RestorePointType}} | ConvertTo-Json -Compress")
        from ..catalog.helpers import powershell
        text = powershell(script).strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            return []
        data = data if isinstance(data, list) else [data]
        return [RestorePoint(str(d.get("SequenceNumber")), d.get("Description", ""), d.get("Date", ""), str(d.get("Type", ""))) for d in data]
    if b == "timeshift":
        return parse_timeshift(run_cmd(["pkexec", "timeshift", "--list"], 60).stdout)
    if b == "snapper":
        return parse_snapper(run_cmd(["snapper", "list"], 60).stdout)
    return []


def create_point(ctx: Ctx, description: str) -> None:
    b = backend_name(ctx)
    if b == "windows":
        script = f"Checkpoint-Computer -Description '{description.replace(chr(39), '')}' -RestorePointType MODIFY_SETTINGS"
        cmd = ["powershell", "-NoProfile", "-Command", script]
    elif b == "timeshift":
        cmd = ["pkexec", "timeshift", "--create", "--comments", description, "--scripted"]
    elif b == "snapper":
        cmd = ["pkexec", "snapper", "create", "--description", description]
    else:
        raise OSError("no backend")
    r = run_cmd(cmd, 900)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout).strip() or "failed")


def open_restore_ui(ctx: Ctx) -> None:
    b = backend_name(ctx)
    if b == "windows":
        subprocess.Popen(["rstrui.exe"])
    elif b == "timeshift":
        subprocess.Popen(["timeshift-launcher"] if shutil.which("timeshift-launcher") else ["timeshift-gtk"])
