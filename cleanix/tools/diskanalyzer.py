"""Анализатор диска: типы файлов, самые большие файлы и дерево папок (как в TreeSize / WinDirStat)."""
from __future__ import annotations

import heapq
import os
import threading
from collections import deque
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


_NO_KIDS: tuple = ()
_NO_CATS: Dict[str, List[int]] = {}


class Node:
    """Папка в дереве. Файлы по отдельности не хранятся: только суммы (иначе на целом диске не хватит памяти)."""
    __slots__ = ("name", "_root", "parent", "children", "size", "files", "dirs", "own_size", "own_files", "cats")

    def __init__(self, name: str, path: Optional[str] = None, parent: Optional["Node"] = None):
        self.name = name
        self._root = path if parent is None else None      # полный путь хранит только корень, у остальных он собирается
        self.parent = parent
        self.children = _NO_KIDS                           # общий пустой кортеж: без отдельного списка на каждую папку
        self.size = 0          # байт во всём поддереве
        self.files = 0         # файлов во всём поддереве
        self.dirs = 0          # вложенных папок во всём поддереве
        self.own_size = 0      # байт в файлах прямо в этой папке
        self.own_files = 0
        self.cats: Dict[str, List[int]] = _NO_CATS     # категория -> [файлов, байт] (только прямые файлы)

    @property
    def path(self) -> str:
        if self.parent is None:
            return self._root or self.name
        return os.path.join(self.parent.path, self.name)


@dataclass
class Report:
    root: str
    count: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in CATEGORIES})
    size: Dict[str, int] = field(default_factory=lambda: {k: 0 for k in CATEGORIES})
    top: Dict[str, List[Tuple[int, str]]] = field(default_factory=lambda: {k: [] for k in CATEGORIES})
    tree: Optional[Node] = None
    keep: int = 500
    scanning: bool = False
    files_seen: int = 0

    @property
    def total_size(self) -> int:
        return sum(self.size.values())

    @property
    def total_count(self) -> int:
        return sum(self.count.values())

    def largest(self, category: Optional[str] = None, n: int = 500) -> List[Tuple[int, str]]:
        if category:
            return sorted(self.top[category], reverse=True)[:n]
        allf = [x for v in list(self.top.values()) for x in list(v)]
        return heapq.nlargest(n, allf)


def _is_junction(e: os.DirEntry) -> bool:
    fn = getattr(e, "is_junction", None)
    return bool(fn and fn())


def _add_up(node: Optional[Node], size: int, files: int, dirs: int) -> None:
    while node is not None:
        node.size += size
        node.files += files
        node.dirs += dirs
        node = node.parent


def _scan_dir(rep: Report, node: Node, dev: int, one_device: bool, shallow: bool = False,
              progress: Optional[Callable[[int, str], None]] = None) -> List[Node]:
    """Читает одну папку: прямые файлы -> суммы узла и отчёта; подпапки -> новые дочерние узлы (их вернёт)."""
    own_size = own_files = 0
    cats: Dict[str, List[int]] = {}
    subdirs: List[str] = []
    try:
        it = os.scandir(node.path)
    except OSError:
        return []
    with it:
        for e in it:
            try:
                if e.is_symlink() or _is_junction(e):
                    continue
                if e.is_dir(follow_symlinks=False):
                    if not shallow and not (one_device and e.stat(follow_symlinks=False).st_dev != dev):
                        subdirs.append(e.name)
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            cat = category_of(e.name)
            c = cats.setdefault(cat, [0, 0])
            c[0] += 1
            c[1] += st.st_size
            own_size += st.st_size
            own_files += 1
            heap = rep.top[cat]
            if len(heap) < rep.keep:
                heapq.heappush(heap, (st.st_size, e.path))
            elif st.st_size > heap[0][0]:
                heapq.heapreplace(heap, (st.st_size, e.path))
    for cat, (cnt, sz) in cats.items():
        rep.count[cat] += cnt
        rep.size[cat] += sz
    node.own_size, node.own_files, node.cats = own_size, own_files, (cats or _NO_CATS)
    kids = [Node(n, None, node) for n in subdirs]
    if kids and not shallow:
        node.children = kids
    _add_up(node, own_size, own_files, len(kids))
    rep.files_seen += own_files
    if progress and rep.files_seen % 2000 < own_files:
        progress(rep.files_seen, node.path)
    return kids


def _scan_tree(rep: Report, start: Node, dev: int, one_device: bool, cancel: Optional[threading.Event],
               progress: Optional[Callable[[int, str], None]]) -> None:
    """Обход вширь: размеры верхних папок растут равномерно, и живая картина осмысленна с первых секунд."""
    queue = deque([start])
    while queue:
        if cancel is not None and cancel.is_set():
            break
        node = queue.popleft()
        queue.extend(_scan_dir(rep, node, dev, one_device, progress=progress))


def _device(path: str, one_device: bool) -> Tuple[int, bool]:
    if os.name == "nt":
        one_device = False      # DirEntry.stat().st_dev на Windows всегда 0
    try:
        return os.stat(path).st_dev, one_device
    except OSError:
        return 0, False


def analyze(root: str, cancel: Optional[threading.Event] = None, progress: Optional[Callable[[int, str], None]] = None,
            keep: int = 500, one_device: bool = True, report: Optional[Report] = None) -> Report:
    """Полный обход. Можно передать заранее созданный *report*: он наполняется по ходу, и интерфейс читает его вживую."""
    rep = report if report is not None else Report(root)
    rep.keep = keep
    if not os.path.isdir(root):
        return rep
    dev, one_device = _device(root, one_device)
    rep.tree = Node(root, root)
    rep.scanning = True
    try:
        _scan_tree(rep, rep.tree, dev, one_device, cancel, progress)
    finally:
        rep.scanning = False
    return rep


# --------------------------- дерево: поиск и пересчёт -----------------------------
def find_node(rep: Report, path: str) -> Optional[Node]:
    node = rep.tree
    if node is None:
        return None
    rel = os.path.relpath(path, rep.root)
    if rel == ".":
        return node
    if rel.startswith(".."):
        return None
    for part in rel.split(os.sep):
        key = os.path.normcase(part)
        node = next((c for c in list(node.children) if os.path.normcase(c.name) == key), None)
        if node is None:
            return None
    return node


def _subtree_cats(node: Node, own_only: bool = False) -> Dict[str, List[int]]:
    total: Dict[str, List[int]] = {}
    stack = [node]
    while stack:
        n = stack.pop()
        for cat, (c, s) in n.cats.items():
            t = total.setdefault(cat, [0, 0])
            t[0] += c
            t[1] += s
        if not own_only:
            stack.extend(n.children)
    return total


def _drop_totals(rep: Report, cats: Dict[str, List[int]]) -> None:
    for cat, (c, s) in cats.items():
        rep.count[cat] -= c
        rep.size[cat] -= s


def _prune_top(rep: Report, path: str, deep: bool) -> None:
    """Убирает из списков «самых больших файлов» записи пересчитываемой папки."""
    pre = path.rstrip(os.sep) + os.sep
    for heap in rep.top.values():
        kept = [x for x in heap if not (x[1].startswith(pre) if deep else os.path.dirname(x[1]) == path.rstrip(os.sep))]
        if len(kept) != len(heap):
            heap[:] = kept
            heapq.heapify(heap)


def remove_node(rep: Report, node: Node) -> Optional[Node]:
    """Папки больше нет: вычитаем её из итогов предков и отчёта. Возвращает родителя."""
    parent = node.parent
    if parent is None:
        return None
    _drop_totals(rep, _subtree_cats(node))
    _prune_top(rep, node.path, True)
    _add_up(parent, -node.size, -node.files, -(node.dirs + 1))
    parent.children = [c for c in parent.children if c is not node] or _NO_KIDS
    return parent


def rescan(rep: Report, node: Node, cancel: Optional[threading.Event] = None, one_device: bool = True,
           progress: Optional[Callable[[int, str], None]] = None) -> Optional[Node]:
    """Считает поддерево заново. Если папка исчезла, убирает её из дерева и возвращает родителя."""
    if not os.path.isdir(node.path):
        return remove_node(rep, node)
    _drop_totals(rep, _subtree_cats(node))
    _prune_top(rep, node.path, True)
    _add_up(node.parent, -node.size, -node.files, -node.dirs)
    node.children = _NO_KIDS
    node.size = node.files = node.dirs = node.own_size = node.own_files = 0
    node.cats = _NO_CATS
    dev, one_device = _device(node.path, one_device)
    _scan_tree(rep, node, dev, one_device, cancel, progress)
    return node


def refresh_own_files(rep: Report, node: Node) -> None:
    """Пересчитывает только файлы, лежащие прямо в папке (после удаления отдельных файлов)."""
    _drop_totals(rep, _subtree_cats(node, own_only=True))
    _prune_top(rep, node.path, False)
    _add_up(node, -node.own_size, -node.own_files, 0)
    node.own_size = node.own_files = 0
    node.cats = _NO_CATS
    _scan_dir(rep, node, 0, False, shallow=True)


def list_files(path: str, limit: int = 3000) -> List[Tuple[str, str, int, float]]:
    """Файлы прямо в папке: (имя, путь, размер, mtime), крупные первыми."""
    out: List[Tuple[str, str, int, float]] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_symlink() or _is_junction(e) or e.is_dir(follow_symlinks=False):
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                out.append((e.name, e.path, st.st_size, st.st_mtime))
    except OSError:
        return []
    out.sort(key=lambda x: -x[2])
    return out[:limit]


def is_protected_path(path: str, env: Optional[Dict[str, str]] = None) -> bool:
    """Нельзя удалять из анализатора: корни дисков, домашняя папка, системные каталоги и всё внутри них."""
    env = env if env is not None else dict(os.environ)

    def norm(x: str) -> str:
        return os.path.normcase(os.path.abspath(x)).rstrip("\\/")

    p = norm(path) or os.sep
    if os.path.splitdrive(p)[1] in ("", os.sep, "\\"):
        return True
    exact = {norm(os.path.expanduser("~"))}
    trees = set()
    for k in ("WINDIR", "SystemRoot"):
        if env.get(k):
            trees.add(norm(env[k]))
    for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramData", "USERPROFILE", "SystemDrive"):
        if env.get(k):
            exact.add(norm(env[k]))
    if os.name != "nt":
        trees |= {"/bin", "/boot", "/dev", "/etc", "/lib", "/lib32", "/lib64", "/proc", "/sbin", "/sys", "/usr"}
        exact |= {"/home", "/opt", "/root", "/run", "/srv", "/var", "/var/lib"}
    return p in exact or any(p == t or p.startswith(t + os.sep) for t in trees)
