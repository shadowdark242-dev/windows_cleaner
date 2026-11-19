"""Анализатор диска: распределение по типам файлов и самые большие файлы."""
from __future__ import annotations

import heapq
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..core.i18n import T

CATEGORIES: Dict[str, Tuple[T, Tuple[str, ...]]] = {
    "pictures": (T("Pictures", "Изображения"), (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".heic", ".raw", ".psd", ".ico")),
    "music": (T("Music", "Музыка"), (".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus")),
    "video": (T("Video", "Видео"), (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg")),
    "documents": (T("Documents", "Документы"), (".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt", ".odt", ".ods", ".csv", ".rtf", ".epub", ".md")),
    "archives": (T("Archives", "Архивы"), (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso", ".img", ".cab", ".zst")),
    "programs": (T("Programs", "Программы"), (".exe", ".dll", ".msi", ".so", ".deb", ".rpm", ".appimage", ".bin", ".apk", ".sys", ".jar")),
    "other": (T("Other", "Прочее"), ()),
}
_EXT = {e: k for k, (_n, exts) in CATEGORIES.items() for e in exts}


def category_of(name: str) -> str:
    return _EXT.get(os.path.splitext(name)[1].lower(), "other")


@dataclass
class Report:
    root: str
    count: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in CATEGORIES})
    size: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in CATEGORIES})
    top: Dict[str, List[Tuple[int, str]]] = field(default_factory=lambda: {k: [] for k in CATEGORIES})

    @property
    def total_size(self) -> int:
        return sum(self.size.values())

    @property
    def total_count(self) -> int:
        return sum(self.count.values())

    def largest(self, category: Optional[str] = None, n: int = 500) -> List[Tuple[int, str]]:
        if category:
            return sorted(self.top[category], reverse=True)[:n]
        allf = [x for v in self.top.values() for x in v]
        return heapq.nlargest(n, allf)


def analyze(root: str, cancel: Optional[threading.Event] = None, progress: Optional[Callable[[int, str], None]] = None,
            keep: int = 500, one_device: bool = True) -> Report:
    rep = Report(root)
    try:
        dev = os.stat(root).st_dev
    except OSError:
        return rep
    n = 0
    stack = [root]
    while stack:
        if cancel is not None and cancel.is_set():
            break
        cur = stack.pop()
        try:
            it = os.scandir(cur)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_symlink() or (getattr(e, "is_junction", None) and e.is_junction()):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if one_device and e.stat(follow_symlinks=False).st_dev != dev:
                            continue
                        stack.append(e.path)
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                cat = category_of(e.name)
                rep.count[cat] += 1
                rep.size[cat] += st.st_size
                heap = rep.top[cat]
                if len(heap) < keep:
                    heapq.heappush(heap, (st.st_size, e.path))
                elif st.st_size > heap[0][0]:
                    heapq.heapreplace(heap, (st.st_size, e.path))
                n += 1
                if progress and n % 2000 == 0:
                    progress(n, cur)
    return rep
