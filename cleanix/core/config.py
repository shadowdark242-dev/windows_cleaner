"""Хранение настроек приложения (JSON)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .platform import IS_WINDOWS


def config_dir() -> Path:
    override = os.environ.get("CLEANIX_CONFIG_DIR")
    if override:
        p = Path(override)
    elif IS_WINDOWS:
        p = Path(os.environ.get("APPDATA", Path.home())) / "Cleanix"
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cleanix"
    p.mkdir(parents=True, exist_ok=True)
    return p


def backup_dir() -> Path:
    p = config_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Config:
    language: str = "auto"            # auto | ru | en
    theme: str = "light"              # light | dark
    secure_passes: int = 0            # 0 — обычное удаление, 1/3/7/35 — перезапись
    min_age_hours: int = 24           # не трогать временные файлы моложе N часов
    confirm_clean: bool = True
    show_sensitive: bool = False      # показывать опции «пароли» и «данные форм»
    selected: Dict[str, bool] = field(default_factory=dict)      # id опции -> отмечена
    include: List[Dict[str, Any]] = field(default_factory=list)  # {path, mode, pattern, recursive}
    exclude: List[str] = field(default_factory=list)
    cookies_keep: List[str] = field(default_factory=list)
    schedule: Dict[str, Any] = field(default_factory=lambda: {"enabled": False, "freq": "daily", "time": "09:00"})
    dup_folders: List[str] = field(default_factory=list)
    last_tab: str = "easy"

    # ------------------------------------------------------------------
    @classmethod
    def path(cls) -> Path:
        return config_dir() / "config.json"

    @classmethod
    def load(cls) -> "Config":
        cfg = cls()
        try:
            data = json.loads(cls.path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        for key, value in data.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        try:
            tmp = self.path().with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path())
        except OSError:
            pass
