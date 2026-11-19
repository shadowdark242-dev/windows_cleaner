"""Общая модель «проблем» для чистильщика реестра (Windows) и системных проблем (Linux)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..core.i18n import Text


@dataclass
class Issue:
    category: str
    problem: str
    data: str
    location: str                 # ключ реестра / путь к файлу
    value_name: Optional[str] = None   # имя значения (None — удалять ключ целиком)
    kind: str = "regkey"          # regkey | regvalue | file | line
    extra: Dict = field(default_factory=dict)
    checked: bool = True


RISK_SAFE, RISK_CAUTION, RISK_RISKY = "safe", "caution", "risky"


@dataclass
class Category:
    id: str
    name: Text
    scan: Callable[["IssueCtx"], List[Issue]]
    risk: str = RISK_SAFE          # safe — рекомендуется; caution/risky — только осознанно
    problem: Optional[Text] = None  # локализованное описание проблемы для таблицы

    @property
    def recommended(self) -> bool:
        return self.risk == RISK_SAFE


def recommended_ids(categories: List[Category]) -> set:
    return {c.id for c in categories if c.recommended}


class IssueCtx:
    def __init__(self, registry=None, env=None, home=None, platform="windows", cancel=None):
        self.reg = registry
        self.env = dict(os.environ if env is None else env)
        self.home = home
        self.platform = platform
        self.cancel = cancel
        self.protected = 0          # сколько защищённых системных записей пропущено

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            from ..core.engine import Cancelled
            raise Cancelled()


def scan_all(categories: List[Category], ctx: IssueCtx, selected: Optional[set] = None,
             progress: Optional[Callable[[str, int, int], None]] = None) -> List[Issue]:
    out: List[Issue] = []
    todo = [c for c in categories if selected is None or c.id in selected]
    for i, cat in enumerate(todo):
        ctx.check_cancel()
        if progress:
            progress(str(cat.name), i, len(todo))
        try:
            found = cat.scan(ctx)
            if ctx.reg is not None:      # скрываем записи, которые нельзя изменить даже администратору
                keep = []
                for i in found:
                    if i.kind in ("regkey", "regvalue") and not ctx.reg.can_modify(i.location, i.kind == "regvalue"):
                        ctx.protected += 1
                    else:
                        keep.append(i)
                found = keep
            out.extend(found)
        except Exception as exc:
            if exc.__class__.__name__ == "Cancelled":
                raise
            out.append(Issue(cat.id, f"Scan error: {exc}", "", "", kind="error", checked=False))
    if progress:
        progress("", len(todo), len(todo))
    return out
