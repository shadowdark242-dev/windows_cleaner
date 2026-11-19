"""Расширения браузеров (просмотр)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from ..catalog import browsers
from ..core.engine import Ctx


@dataclass
class Plugin:
    browser: str
    name: str
    version: str
    ident: str
    path: str


def _chromium_name(ext_dir: Path, manifest: dict) -> str:
    name = str(manifest.get("name", ""))
    if name.startswith("__MSG_") and name.endswith("__"):
        key = name[6:-2]
        loc = manifest.get("default_locale", "en")
        for cand in (loc, "en", "en_US", "ru"):
            f = ext_dir / "_locales" / cand / "messages.json"
            if f.is_file():
                try:
                    msgs = json.loads(f.read_text(encoding="utf-8-sig"))
                    for k, v in msgs.items():
                        if k.lower() == key.lower():
                            return v.get("message", name)
                except (OSError, ValueError):
                    pass
    return name


def list_plugins(ctx: Ctx) -> List[Plugin]:
    out: List[Plugin] = []
    for spec in browsers.CHROMIUM:
        profs, _c, _flat = browsers.chromium_roots(ctx, spec)
        for prof in profs:
            ext_root = prof / "Extensions"
            if not ext_root.is_dir():
                continue
            for ext in sorted(ext_root.iterdir()):
                versions = sorted(p for p in ext.iterdir() if p.is_dir()) if ext.is_dir() else []
                if not versions:
                    continue
                vdir = versions[-1]
                try:
                    m = json.loads((vdir / "manifest.json").read_text(encoding="utf-8-sig"))
                except (OSError, ValueError):
                    continue
                out.append(Plugin(spec[1], _chromium_name(vdir, m) or ext.name, str(m.get("version", "")), ext.name, str(vdir)))
    for prof, _c in browsers.firefox_profiles(ctx):
        f = prof / "extensions.json"
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for a in data.get("addons", []):
            if a.get("location") == "app-system-defaults" or a.get("type") not in ("extension", "theme"):
                continue
            name = (a.get("defaultLocale") or {}).get("name") or a.get("id", "")
            out.append(Plugin("Mozilla Firefox", name, str(a.get("version", "")), a.get("id", ""), str(a.get("path") or prof)))
    return sorted(out, key=lambda p: (p.browser, p.name.lower()))
