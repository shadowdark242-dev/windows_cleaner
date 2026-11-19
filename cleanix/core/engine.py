"""Ядро очистки: описание опций, анализ и удаление."""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Optional

from . import fs
from .config import Config
from .i18n import Text
from .platform import NAME, is_admin
from .registry import RegistryBackend, default_backend


# ----------------------------------------------------------------------
# Модель
# ----------------------------------------------------------------------
@dataclass
class Found:
    """Одна найденная «единица мусора»."""

    path: str                 # файл / ключ реестра / метка действия
    size: int = 0
    kind: str = "file"        # file | regvalue | regkey | action
    extra: str = ""           # имя значения реестра и т.п.
    root: str = ""            # после удаления файла чистить пустые каталоги вверх до root


@dataclass
class Group:
    id: str
    name: Text
    tab: str                  # "system" | "apps"
    platform: str = "all"
    order: int = 0


@dataclass
class CleanItem:
    id: str
    group: str
    name: Text
    scan: Callable[["Ctx"], Iterable[Found]]
    default: bool = False
    platform: str = "all"     # windows | linux | all
    admin: bool = False       # нужны права администратора
    clean: Optional[Callable[["Ctx", List[Found], "ItemResult"], None]] = None
    easy: str = ""            # категория в простом режиме ("" — не входит)
    note: Optional[Text] = None


@dataclass
class ItemResult:
    item: CleanItem
    found: List[Found] = field(default_factory=list)
    size: int = 0
    count: int = 0
    removed_size: int = 0
    removed_count: int = 0
    errors: List[str] = field(default_factory=list)
    skipped: str = ""         # причина пропуска (например, нет прав)


class Cancelled(Exception):
    pass


# ----------------------------------------------------------------------
# Контекст
# ----------------------------------------------------------------------
class Env(dict):
    """Переменные окружения Windows нечувствительны к регистру."""

    def __init__(self, data=None):
        super().__init__({str(k).upper(): v for k, v in (data or {}).items()})

    def get(self, key, default=None):
        return super().get(str(key).upper(), default)

    def __getitem__(self, key):
        return super().__getitem__(str(key).upper())

    def __contains__(self, key):
        return super().__contains__(str(key).upper())


class Ctx:
    def __init__(
        self,
        config: Optional[Config] = None,
        env: Optional[Dict[str, str]] = None,
        home: Optional[os.PathLike | str] = None,
        platform: Optional[str] = None,
        registry: Optional[RegistryBackend] = None,
        admin: Optional[bool] = None,
        now: Optional[float] = None,
        tmp_dirs: Optional[List[str]] = None,
    ):
        self.cfg = config or Config()
        self.platform = platform or NAME
        self.windows = self.platform == "windows"
        raw = os.environ if env is None else env
        self.env: Dict[str, str] = Env(raw) if self.windows else dict(raw)
        self.home = Path(home) if home else Path(
            self.env.get("USERPROFILE" if self.windows else "HOME") or Path.home()
        )
        self.registry = registry if registry is not None else (default_backend() if self.windows else None)
        self.admin = is_admin() if admin is None else admin
        self.now = now or time.time()
        self.tmp_dirs = tmp_dirs
        self.cancel = threading.Event()
        self.dry_run = False
        self._excludes = [fs.path_key(p, self.windows) for p in self.cfg.exclude if p]

    # --- пути ---------------------------------------------------------
    def env_path(self, name: str, *parts: str) -> Optional[Path]:
        base = self.env.get(name)
        if not base:
            return None
        return Path(base).joinpath(*parts)

    @property
    def min_age(self) -> float:
        return float(self.cfg.min_age_hours) * 3600

    def check_cancel(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def excluded(self, path: str) -> bool:
        if not self._excludes:
            return False
        key = fs.path_key(path, self.windows)
        for ex in self._excludes:
            if key == ex or key.startswith(ex.rstrip("\\/") + os.sep) or key.startswith(ex.rstrip("\\/") + "\\"):
                return True
        return False

    # --- удобные сканеры ---------------------------------------------
    def files(self, root: Optional[os.PathLike | str], patterns=None, recursive=True,
              respect_age=False, prune: bool = False) -> Iterator[Found]:
        if root is None:
            return
        root = str(root)
        if not os.path.isdir(root):
            return
        age = self.min_age if respect_age else 0
        for path, size in fs.iter_files(root, patterns, recursive, age, self.now, skip=self.excluded):
            self.check_cancel()
            yield Found(path, size, "file", root=root if prune else "")

    def file(self, path: Optional[os.PathLike | str]) -> Iterator[Found]:
        if path is None:
            return
        p = str(path)
        try:
            if os.path.isfile(p) or os.path.islink(p):
                if not self.excluded(p):
                    yield Found(p, 0 if os.path.islink(p) else os.path.getsize(p))
        except OSError:
            return

    def glob(self, root: Optional[os.PathLike | str], pattern: str, **kw) -> Iterator[Found]:
        """Файлы по маске относительно root без заглублённого обхода."""
        if root is None or not os.path.isdir(str(root)):
            return
        yield from self.files(root, [pattern], recursive=False, **kw)

    def profiles(self, base: Optional[os.PathLike | str], *, pattern="*") -> List[Path]:
        if base is None or not os.path.isdir(str(base)):
            return []
        import fnmatch
        out = []
        for name in sorted(os.listdir(str(base))):
            if fnmatch.fnmatch(name, pattern) and os.path.isdir(os.path.join(str(base), name)):
                out.append(Path(base) / name)
        return out


# ----------------------------------------------------------------------
# Анализ и очистка
# ----------------------------------------------------------------------
ProgressFn = Callable[[str, int, int], None]


def available(item: CleanItem, ctx: Ctx) -> bool:
    return item.platform in ("all", ctx.platform)


def analyze(items: List[CleanItem], ctx: Ctx, progress: Optional[ProgressFn] = None) -> List[ItemResult]:
    results: List[ItemResult] = []
    total = len(items)
    for i, item in enumerate(items):
        ctx.check_cancel()
        if progress:
            progress(str(item.name), i, total)
        res = ItemResult(item)
        if item.admin and not ctx.admin:
            res.skipped = "admin"
        try:
            res.found = list(item.scan(ctx))
        except Cancelled:
            raise
        except Exception as exc:  # сканер не должен ронять весь анализ
            res.errors.append(f"{type(exc).__name__}: {exc}")
        res.count = len(res.found)
        res.size = sum(f.size for f in res.found)
        results.append(res)
    if progress:
        progress("", total, total)
    return results


def clean(results: List[ItemResult], ctx: Ctx, progress: Optional[ProgressFn] = None) -> List[ItemResult]:
    total = len(results)
    for i, res in enumerate(results):
        ctx.check_cancel()
        if progress:
            progress(str(res.item.name), i, total)
        if res.skipped or not res.found:
            continue
        try:
            if res.item.clean is not None:
                res.item.clean(ctx, res.found, res)
            else:
                delete_found(ctx, res.found, res)
        except Cancelled:
            raise
        except Exception as exc:
            res.errors.append(f"{type(exc).__name__}: {exc}")
    if progress:
        progress("", total, total)
    return results


def delete_found(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    """Стандартное удаление: файлы и значения/ключи реестра."""
    pruned: set = set()
    for f in found:
        ctx.check_cancel()
        try:
            if f.kind == "file":
                if ctx.excluded(f.path):
                    continue
                if not ctx.dry_run:
                    fs.delete_file(f.path, ctx.cfg.secure_passes)
                if f.root:
                    pruned.add((os.path.dirname(f.path), f.root))
            elif f.kind == "regvalue":
                if ctx.registry is None:
                    continue
                if not ctx.dry_run:
                    ctx.registry.delete_value(f.path, f.extra)
            elif f.kind == "regkey":
                if ctx.registry is None:
                    continue
                if not ctx.dry_run:
                    ctx.registry.delete_key(f.path)
            else:
                continue
            res.removed_count += 1
            res.removed_size += f.size
        except OSError as exc:
            res.errors.append(f"{f.path}: {exc.strerror or exc}")
    if not ctx.dry_run:
        for start, root in pruned:
            fs.prune_empty_dirs(start, root)


def summarize(results: List[ItemResult]) -> Dict[str, int]:
    return {
        "size": sum(r.size for r in results),
        "count": sum(r.count for r in results),
        "removed_size": sum(r.removed_size for r in results),
        "removed_count": sum(r.removed_count for r in results),
        "errors": sum(len(r.errors) for r in results),
    }
