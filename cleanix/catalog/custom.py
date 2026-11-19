"""Пользовательские папки/файлы из «Настройки → Включения»."""
from __future__ import annotations

import os
from typing import Iterator, List

from ..core import fs
from ..core.engine import CleanItem, Ctx, Found, Group, ItemResult, delete_found
from ..core.i18n import T

GROUPS = [Group("custom", T("Custom Files and Folders", "Пользовательские файлы и папки"), "system", "all", 90)]

MODES = ("all", "files", "wipe")   # файлы и папки / только файлы / очистить папку полностью


def _scan(ctx: Ctx) -> Iterator[Found]:
    for entry in ctx.cfg.include:
        path = entry.get("path", "")
        if not path or not os.path.exists(path):
            continue
        # защита: не позволять включить корень диска/домашний каталог целиком
        norm = os.path.normpath(path)
        if norm in (os.path.sep, str(ctx.home)) or os.path.dirname(norm) == norm:
            continue
        pattern = (entry.get("pattern") or "*").strip() or "*"
        recursive = bool(entry.get("recursive", True))
        if os.path.isfile(norm):
            yield from ctx.file(norm)
            continue
        root = norm if entry.get("mode", "all") in ("all", "wipe") else ""
        for path_, size in fs.iter_files(norm, [p.strip() for p in pattern.split(";")], recursive, 0, ctx.now, skip=ctx.excluded):
            ctx.check_cancel()
            yield Found(path_, size, "file", root=root)


def _clean(ctx: Ctx, found: List[Found], res: ItemResult) -> None:
    delete_found(ctx, found, res)


ITEMS: List[CleanItem] = [
    CleanItem("custom.include", "custom", T("Custom Files and Folders", "Пользовательские файлы и папки"), _scan, False, "all", clean=_clean),
]
