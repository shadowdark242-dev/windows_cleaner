"""Общие действия для опций очистки: sqlite, реестр, команды, буфер обмена."""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
from typing import Iterator, List

from ..core.engine import Ctx, Found, ItemResult, delete_found


def run_cmd(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, errors="replace", **kw)


def powershell(script: str, timeout: int = 60) -> str:
    """Выполняет PowerShell-скрипт и возвращает stdout в UTF-8 (иначе кириллица портится)."""
    prefix = "[Console]::OutputEncoding=[Text.Encoding]::UTF8;$ProgressPreference='SilentlyContinue';"
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", prefix + script],
                       capture_output=True, timeout=timeout, **kw)
    return r.stdout.decode("utf-8", errors="replace")


def reg_values(ctx: Ctx, key: str, *, recursive: bool = False) -> Iterator[Found]:
    """Все значения ключа (и подключей) как мусор типа regvalue."""
    reg = ctx.registry
    if reg is None:
        return
    stack = [key]
    while stack:
        k = stack.pop()
        for name, data, _typ in reg.enum_values(k):
            yield Found(k, 0, "regvalue", extra=name)
        if recursive:
            stack.extend(k + "\\" + s for s in reg.enum_keys(k))


def reg_subkeys(ctx: Ctx, key: str) -> Iterator[Found]:
    reg = ctx.registry
    if reg is None:
        return
    for sub in reg.enum_keys(key):
        yield Found(key + "\\" + sub, 0, "regkey")


def action_found(label: str) -> List[Found]:
    return [Found(label, 0, "action")]


# ----------------------------------------------------------------------
# SQLite (куки, история Firefox)
# ----------------------------------------------------------------------
def _cookie_filter(keep: List[str], column: str) -> tuple[str, list]:
    """WHERE-условие: куки, домен которых НЕ входит в список «оставить»."""
    clauses, params = [], []
    for d in keep:
        d = d.strip().lower().lstrip(".")
        if not d:
            continue
        clauses.append(f"NOT (lower(ltrim({column}, '.')) = ? OR lower({column}) LIKE ?)")
        params += [d, "%." + d]
    return " AND ".join(clauses), params


def clean_cookie_dbs(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    """Удаляет куки, кроме доменов из «Cookies to keep»."""
    keep = [d for d in ctx.cfg.cookies_keep if d.strip()]
    if not keep:
        delete_found(ctx, found, res)
        return
    for f in found:
        ctx.check_cancel()
        column = "host" if os.path.basename(f.path).lower().startswith("cookies.sqlite") else "host_key"
        table = "moz_cookies" if column == "host" else "cookies"
        where, params = _cookie_filter(keep, column)
        try:
            if ctx.dry_run:
                res.removed_count += 1
                continue
            con = sqlite3.connect(f.path, timeout=1)
            try:
                cur = con.execute(f"DELETE FROM {table} WHERE {where}", params)
                con.commit()
                res.removed_count += max(cur.rowcount, 0)
            finally:
                con.close()
        except sqlite3.Error as exc:
            res.errors.append(f"{os.path.basename(f.path)}: {exc} (закройте браузер)")


def clean_firefox_history(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    """История Firefox без потери закладок."""
    for f in found:
        ctx.check_cancel()
        try:
            if ctx.dry_run:
                res.removed_count += 1
                continue
            con = sqlite3.connect(f.path, timeout=1)
            try:
                con.execute("DELETE FROM moz_historyvisits")
                con.execute(
                    "DELETE FROM moz_places WHERE id NOT IN "
                    "(SELECT fk FROM moz_bookmarks WHERE fk IS NOT NULL)"
                )
                con.commit()
                res.removed_count += 1
                res.removed_size += f.size
            finally:
                con.close()
        except sqlite3.Error as exc:
            res.errors.append(f"{os.path.basename(f.path)}: {exc} (закройте Firefox)")


# ----------------------------------------------------------------------
# Буфер обмена / DNS
# ----------------------------------------------------------------------
def clear_clipboard(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    if ctx.dry_run:
        res.removed_count += 1
        return
    ok = False
    if ctx.windows:
        try:
            import ctypes
            u = ctypes.windll.user32  # type: ignore[attr-defined]
            if u.OpenClipboard(None):
                u.EmptyClipboard()
                u.CloseClipboard()
                ok = True
        except Exception as exc:
            res.errors.append(str(exc))
    else:
        for cmd in (["wl-copy", "--clear"], ["xclip", "-selection", "clipboard", "-i", os.devnull],
                    ["xsel", "--clipboard", "--clear"]):
            if shutil.which(cmd[0]):
                try:
                    if run_cmd(cmd, 10).returncode == 0:
                        ok = True
                        break
                except Exception:
                    continue
        if not ok:
            res.errors.append("wl-copy / xclip / xsel не найдены")
    if ok:
        res.removed_count += 1


def flush_dns(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    if ctx.dry_run:
        res.removed_count += 1
        return
    cmds = [["ipconfig", "/flushdns"]] if ctx.windows else [["resolvectl", "flush-caches"], ["systemd-resolve", "--flush-caches"]]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            try:
                if run_cmd(cmd, 20).returncode == 0:
                    res.removed_count += 1
                    return
            except Exception:
                pass
    res.errors.append("DNS flush failed")
