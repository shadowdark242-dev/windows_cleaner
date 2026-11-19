"""Каталог опций очистки."""
from __future__ import annotations

from typing import Dict, List, Tuple

from ..core.engine import CleanItem, Ctx, Group
from . import apps, browsers, custom, linux, windows


def _all() -> Tuple[List[Group], List[CleanItem]]:
    groups = windows.GROUPS + linux.GROUPS + browsers.GROUPS + apps.GROUPS + custom.GROUPS
    items = windows.ITEMS + linux.ITEMS + browsers.ITEMS + apps.ITEMS + custom.ITEMS
    return groups, items


def for_platform(platform: str) -> Tuple[List[Group], List[CleanItem]]:
    groups, items = _all()
    g = sorted((x for x in groups if x.platform in ("all", platform)), key=lambda x: x.order)
    ids = {x.id for x in g}
    it = [x for x in items if x.platform in ("all", platform) and x.group in ids]
    return g, it


def is_checked(item: CleanItem, ctx: Ctx) -> bool:
    return ctx.cfg.selected.get(item.id, item.default)


def selected_items(platform: str, ctx: Ctx) -> List[CleanItem]:
    _, items = for_platform(platform)
    return [i for i in items if is_checked(i, ctx)]
