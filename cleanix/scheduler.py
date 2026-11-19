"""Запуск очистки по расписанию (Планировщик Windows / cron)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any, Dict, List

from .catalog.helpers import run_cmd

TASK_NAME = "Cleanix Scheduled Clean"
CRON_MARK = "# cleanix-schedule"


def clean_command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--clean", "--silent"]
    return [sys.executable, "-m", "cleanix", "--clean", "--silent"]


def _quote_win(cmd: List[str]) -> str:
    return " ".join(f'"{c}"' if " " in c else c for c in cmd)


def windows_args(sched: Dict[str, Any]) -> List[str]:
    freq = {"daily": "DAILY", "weekly": "WEEKLY", "logon": "ONLOGON"}[sched.get("freq", "daily")]
    args = ["schtasks", "/create", "/tn", TASK_NAME, "/tr", _quote_win(clean_command()), "/sc", freq, "/f"]
    if freq != "ONLOGON":
        args += ["/st", sched.get("time", "09:00")]
    return args


def cron_line(sched: Dict[str, Any]) -> str:
    hh, _, mm = sched.get("time", "09:00").partition(":")
    cmd = " ".join(f"'{c}'" if " " in c else c for c in clean_command())
    freq = sched.get("freq", "daily")
    if freq == "logon":
        return f"@reboot {cmd} {CRON_MARK}"
    dow = "1" if freq == "weekly" else "*"
    return f"{int(mm or 0)} {int(hh)} * * {dow} {cmd} {CRON_MARK}"


def merge_cron(existing: str, new_line: str | None) -> str:
    lines = [l for l in existing.splitlines() if CRON_MARK not in l]
    if new_line:
        lines.append(new_line)
    return "\n".join(lines) + "\n" if lines else ""


def apply(sched: Dict[str, Any], windows: bool) -> None:
    """Включает/выключает расписание согласно sched['enabled']. Бросает OSError."""
    enabled = bool(sched.get("enabled"))
    if windows:
        if enabled:
            r = run_cmd(windows_args(sched), 30)
        else:
            r = run_cmd(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], 30)
            if r.returncode != 0 and "cannot find" in (r.stderr + r.stdout).lower():
                return
        if r.returncode != 0:
            raise OSError((r.stderr or r.stdout).strip())
        return
    if not shutil.which("crontab"):
        raise OSError("crontab not found")
    cur = run_cmd(["crontab", "-l"], 10)
    text = cur.stdout if cur.returncode == 0 else ""
    new = merge_cron(text, cron_line(sched) if enabled else None)
    r = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True)
    if r.returncode != 0:
        raise OSError(r.stderr.strip())
