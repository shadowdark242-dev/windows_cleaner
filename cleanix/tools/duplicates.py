"""Поиск дубликатов файлов: размер → быстрый хэш → полный хэш."""
from __future__ import annotations

import hashlib
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional


@dataclass
class DupGroup:
    size: int
    paths: List[str]


def _hash(path: str, limit: Optional[int] = None) -> Optional[bytes]:
    h = hashlib.blake2b(digest_size=16)
    try:
        with open(path, "rb") as fh:
            remaining = limit
            while True:
                block = fh.read(1024 * 1024 if remaining is None else min(65536, remaining))
                if not block:
                    break
                h.update(block)
                if remaining is not None:
                    remaining -= len(block)
                    if remaining <= 0:
                        break
    except OSError:
        return None
    return h.digest()


def find_duplicates(
    folders: Iterable[str],
    min_size: int = 1,
    same_name: bool = False,
    exclude: Optional[Callable[[str], bool]] = None,
    cancel: Optional[threading.Event] = None,
    progress: Optional[Callable[[str, int, int], None]] = None,
    skip_hidden: bool = False,
) -> List[DupGroup]:
    by_size: Dict[int, List[str]] = defaultdict(list)
    seen_real = set()
    scanned = 0
    for root in folders:
        for dirpath, dirnames, filenames in os.walk(root):
            if cancel is not None and cancel.is_set():
                return []
            if skip_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))
                           and not (hasattr(os.path, "isjunction") and os.path.isjunction(os.path.join(dirpath, d)))]
            for name in filenames:
                p = os.path.join(dirpath, name)
                if (skip_hidden and name.startswith(".")) or (exclude and exclude(p)):
                    continue
                try:
                    if os.path.islink(p):
                        continue
                    st = os.stat(p)
                except OSError:
                    continue
                key = (st.st_dev, st.st_ino)
                if key in seen_real:            # жёсткая ссылка / повторный проход одной папки
                    continue
                seen_real.add(key)
                if st.st_size >= min_size and st.st_size > 0:
                    by_size[st.st_size].append(p)
                scanned += 1
                if progress and scanned % 500 == 0:
                    progress("scan", scanned, 0)
    cands = [(s, ps) for s, ps in by_size.items() if len(ps) > 1]
    total = sum(len(ps) for _, ps in cands)
    done = 0
    groups: List[DupGroup] = []
    for size, paths in cands:
        quick: Dict[bytes, List[str]] = defaultdict(list)
        for p in paths:
            if cancel is not None and cancel.is_set():
                return []
            hq = _hash(p, 65536)
            if hq is not None:
                quick[hq].append(p)
        for same_quick in quick.values():
            if len(same_quick) < 2:
                continue
            full: Dict[bytes, List[str]] = defaultdict(list)
            for p in same_quick:
                if cancel is not None and cancel.is_set():
                    return []
                hf = _hash(p)
                if hf is not None:
                    full[hf].append(p)
            for g in full.values():
                if len(g) < 2:
                    continue
                if same_name:
                    by_name: Dict[str, List[str]] = defaultdict(list)
                    for p in g:
                        by_name[os.path.basename(p).lower()].append(p)
                    for sub in by_name.values():
                        if len(sub) > 1:
                            groups.append(DupGroup(size, sorted(sub)))
                else:
                    groups.append(DupGroup(size, sorted(g)))
        done += len(paths)
        if progress:
            progress("hash", done, total)
    groups.sort(key=lambda g: g.size * (len(g.paths) - 1), reverse=True)
    return groups
