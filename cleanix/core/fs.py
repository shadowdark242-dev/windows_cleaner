"""Файловые помощники: обход, безопасное и «надёжное» удаление."""
from __future__ import annotations

import fnmatch
import os
import stat
import time
from typing import Callable, Iterator, Optional, Sequence, Tuple

CHUNK = 1024 * 1024


def iter_files(
    root: os.PathLike | str,
    patterns: Optional[Sequence[str]] = None,
    recursive: bool = True,
    min_age: float = 0,
    now: Optional[float] = None,
    skip: Optional[Callable[[str], bool]] = None,
) -> Iterator[Tuple[str, int]]:
    """Обычные файлы под *root*: (путь, размер).

    Симлинки на каталоги не раскрываются, симлинки на файлы отдаются как файлы
    нулевого размера (удаляется ссылка, не цель).
    *min_age* — пропускать файлы, изменённые менее чем *min_age* секунд назад.
    """
    now = time.time() if now is None else now
    stack = [str(root)]
    while stack:
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for entry in it:
                try:
                    path = entry.path
                    if skip and skip(path):
                        continue
                    if _is_junction(entry):
                        continue
                    if entry.is_symlink():
                        if patterns and not _match(entry.name, patterns):
                            continue
                        yield path, 0
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if recursive:
                            stack.append(path)
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if patterns and not _match(entry.name, patterns):
                        continue
                    st = entry.stat(follow_symlinks=False)
                    if min_age and now - st.st_mtime < min_age:
                        continue
                    yield path, st.st_size
                except OSError:
                    continue


def _is_junction(entry) -> bool:
    f = getattr(entry, "is_junction", None)
    return bool(f()) if f else False


def _match(name: str, patterns: Sequence[str]) -> bool:
    low = name.lower()
    return any(fnmatch.fnmatch(low, p.lower()) for p in patterns)


def dir_size(path: os.PathLike | str) -> int:
    return sum(sz for _, sz in iter_files(path))


def path_key(p: os.PathLike | str, windows: bool) -> str:
    s = os.path.normpath(str(p))
    return s.lower() if windows else s


def is_under(path: str, root: str, windows: bool = False) -> bool:
    a, b = path_key(path, windows), path_key(root, windows)
    if a == b:
        return True
    sep = "\\" if windows and "\\" in b else os.sep
    return a.startswith(b.rstrip(sep) + sep)


def overwrite_file(path: str, passes: int) -> None:
    """Перезаписывает содержимое файла перед удалением (passes проходов)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size == 0:
        return
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    with open(path, "r+b", buffering=0) as fh:
        for n in range(passes):
            fh.seek(0)
            written = 0
            while written < size:
                block = min(CHUNK, size - written)
                if n % 3 == 0:
                    data = os.urandom(block)
                elif n % 3 == 1:
                    data = b"\x00" * block
                else:
                    data = b"\xff" * block
                fh.write(data)
                written += block
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass


def delete_file(path: str, passes: int = 0) -> None:
    """Удаляет файл или симлинк; при passes>0 сначала перезаписывает содержимое.

    Бросает OSError, если удалить не удалось.
    """
    if os.path.islink(path):
        os.unlink(path)
        return
    if os.path.isdir(path):
        raise IsADirectoryError(path)
    if passes > 0:
        try:
            overwrite_file(path, passes)
        except OSError:
            pass
    try:
        os.unlink(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)  # read-only на Windows
        os.unlink(path)


def prune_empty_dirs(start: str, root: str) -> None:
    """Удаляет пустые каталоги от *start* вверх до *root* (сам root остаётся)."""
    cur = os.path.abspath(start)
    root = os.path.abspath(root)
    while cur != root and cur.startswith(root):
        try:
            os.rmdir(cur)
        except OSError:
            break
        cur = os.path.dirname(cur)


def prune_tree(root: str) -> None:
    """Удаляет все пустые подкаталоги внутри root (root остаётся)."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
