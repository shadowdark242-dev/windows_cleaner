"""Стирание свободного места и надёжное удаление файлов."""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ..core import fs

BLOCK = 4 * 1024 * 1024
MAX_FILE = 1 << 30          # 1 ГиБ на временный файл
PASS_PRESETS = {1: "1 pass", 3: "3 passes (DoD-like)", 7: "7 passes", 35: "35 passes (Gutmann-like)"}


@dataclass
class Drive:
    path: str
    label: str
    fs: str
    total: int
    free: int


def list_drives() -> List[Drive]:
    out: List[Drive] = []
    if os.name == "nt":
        import ctypes
        import string
        mask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i):
                root = f"{letter}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(root) != 3:   # DRIVE_FIXED
                    continue
                try:
                    u = shutil.disk_usage(root)
                    out.append(Drive(root, root, "", u.total, u.free))
                except OSError:
                    pass
        return out
    real = {"ext2", "ext3", "ext4", "btrfs", "xfs", "f2fs", "vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "zfs", "jfs", "reiserfs"}
    seen = set()
    try:
        lines = Path("/proc/mounts").read_text().splitlines()
    except OSError:
        lines = []
    for line in lines:
        p = line.split()
        if len(p) < 3 or p[2] not in real:
            continue
        mp = p[1].replace("\\040", " ")
        if mp in seen or mp.startswith(("/snap", "/var/lib/docker", "/boot/efi")):
            continue
        seen.add(mp)
        try:
            u = shutil.disk_usage(mp)
        except OSError:
            continue
        out.append(Drive(mp, mp, p[2], u.total, u.free))
    return out


def _pattern(pass_no: int) -> Callable[[int], bytes]:
    kind = pass_no % 3
    if kind == 0:
        return lambda n: os.urandom(n)
    byte = b"\x00" if kind == 1 else b"\xff"
    return lambda n: byte * n


def wipe_free_space(
    path: str,
    passes: int = 1,
    reserve: int = 64 * 1024 * 1024,
    limit: Optional[int] = None,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    """Заполняет свободное место на томе (где лежит *path*) и удаляет временные файлы.

    reserve — сколько байт оставить свободными (чтобы не убить систему);
    limit — максимум записать за проход (для тестов). Возвращает записанных байт за все проходы.
    """
    work = Path(path) / ".cleanix_wipe"
    work.mkdir(exist_ok=True)
    total_written = 0
    try:
        for n in range(passes):
            gen = _pattern(n)
            written = 0
            files: List[Path] = []
            idx = 0
            try:
                while True:
                    free = shutil.disk_usage(path).free
                    room = free - reserve
                    if limit is not None:
                        room = min(room, limit - written)
                    if room <= 0:
                        break
                    f = work / f"wipe_{n}_{idx}.tmp"
                    idx += 1
                    files.append(f)
                    with open(f, "wb", buffering=0) as fh:
                        size = 0
                        while size < MAX_FILE:
                            if cancel is not None and cancel.is_set():
                                raise InterruptedError
                            free = shutil.disk_usage(path).free
                            chunk = min(BLOCK, free - reserve, MAX_FILE - size)
                            if limit is not None:
                                chunk = min(chunk, limit - written)
                            if chunk <= 0:
                                break
                            try:
                                fh.write(gen(chunk))
                            except OSError:
                                chunk = 0
                                break
                            size += chunk
                            written += chunk
                            if progress:
                                progress(n + 1, passes, written)
                        try:
                            os.fsync(fh.fileno())
                        except OSError:
                            pass
                    if size == 0:
                        break
            finally:
                for f in files:
                    try:
                        f.unlink()
                    except OSError:
                        pass
            total_written += written
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return total_written


def shred_paths(paths: List[str], passes: int = 3) -> List[str]:
    """Надёжно удаляет файлы/папки. Возвращает список ошибок."""
    errors: List[str] = []
    for p in paths:
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                for fp, _ in fs.iter_files(p):
                    fs.delete_file(fp, passes)
                for dirpath, _d, _f in os.walk(p, topdown=False):
                    os.rmdir(dirpath)
            else:
                fs.delete_file(p, passes)
        except OSError as exc:
            errors.append(f"{p}: {exc.strerror or exc}")
    return errors
