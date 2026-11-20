"""Консольный режим: анализ/очистка без окна (используется планировщиком)."""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import APP_NAME, __version__
from .catalog import for_platform, is_checked, selected_items
from .core import engine
from .core.config import Config
from .core.i18n import L, human_size, set_language, tr
from .core.platform import NAME


def parse(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="cleanix", description=f"{APP_NAME} {__version__}")
    p.add_argument("--clean", action="store_true", help="очистить отмеченные в настройках опции")
    p.add_argument("--analyze", action="store_true", help="только показать, сколько можно очистить")
    p.add_argument("--list", action="store_true", help="показать все опции очистки")
    p.add_argument("--dry-run", action="store_true", help="ничего не удалять")
    p.add_argument("--silent", action="store_true", help="не печатать подробности")
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return p.parse_args(argv)


def main_cli(args: argparse.Namespace) -> int:
    cfg = Config.load()
    set_language(cfg.language)
    ctx = engine.Ctx(config=cfg)
    ctx.dry_run = args.dry_run
    if args.list:
        groups, items = for_platform(NAME)
        for g in groups:
            print(f"\n[{g.name}]")
            for it in (i for i in items if i.group == g.id):
                mark = "x" if is_checked(it, ctx) else " "
                print(f"  [{mark}] {it.id:<24} {it.name}{'  (admin)' if it.admin else ''}")
        return 0
    items = selected_items(NAME, ctx)
    results = engine.analyze(items, ctx)
    if args.analyze or (not args.clean):
        for r in results:
            if r.count and not args.silent:
                print(f"{str(r.item.name):<45} {r.count:>7}  {human_size(r.size):>10}")
        s = engine.summarize(results)
        print(f"{tr('total')}: {s['count']} / {human_size(s['size'])}")
        return 0
    engine.clean(results, ctx)
    s = engine.summarize(results)
    if not args.silent:
        for r in results:
            for err in r.errors[:3]:
                print(f"! {r.item.name}: {err}", file=sys.stderr)
    label = L("Would remove (dry run)", "Было бы удалено (пробный запуск)") if args.dry_run else tr("removed")
    print(f"{label}: {s['removed_count']} / {human_size(s['removed_size'])}; {tr('errors')}: {s['errors']}")
    return 0
