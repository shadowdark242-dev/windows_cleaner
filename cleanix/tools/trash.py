"""Перемещение в корзину (freedesktop Trash spec / SHFileOperation)."""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote


def move_to_trash(path: str, windows: bool | None = None) -> None:
    windows = (os.name == "nt") if windows is None else windows
    if windows:
        _win_trash(path)
    else:
        _xdg_trash(path)


def _xdg_trash(path: str) -> None:
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    trash = data / "Trash"
    (trash / "files").mkdir(parents=True, exist_ok=True)
    (trash / "info").mkdir(parents=True, exist_ok=True)
    src = Path(os.path.abspath(path))
    name = src.name
    dst = trash / "files" / name
    n = 1
    while dst.exists() or (trash / "info" / (dst.name + ".trashinfo")).exists():
        n += 1
        dst = trash / "files" / f"{src.stem}.{n}{src.suffix}"
    info = trash / "info" / (dst.name + ".trashinfo")
    info.write_text(
        "[Trash Info]\nPath=%s\nDeletionDate=%s\n" % (quote(str(src)), time.strftime("%Y-%m-%dT%H:%M:%S")),
        encoding="utf-8")
    try:
        shutil.move(str(src), str(dst))
    except OSError:
        info.unlink(missing_ok=True)
        raise


def _win_trash(path: str) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_NOERRORUI, FOF_SILENT = 3, 0x40, 0x10, 0x400, 0x4
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0"
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))  # type: ignore[attr-defined]
    if rc != 0 or op.fAnyOperationsAborted:
        raise OSError(f"SHFileOperation failed: {rc}")
