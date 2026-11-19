"""Хранение настроек приложения (JSON)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from .platform import IS_WINDOWS


DATA_DIRNAME = "data"


def app_dir() -> Path:
    """Папка с программой: рядом с .exe (сборка) или корень проекта (запуск из исходников)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".write_test"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def _fallback_dir() -> Path:
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home())) / "Cleanix"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cleanix"


def config_dir() -> Path:
    """Настройки хранятся в папке «data» рядом с программой (портативный режим).

    Если туда писать нельзя (например, Program Files), используется папка профиля пользователя.
    CLEANIX_CONFIG_DIR перекрывает всё (для тестов).
    """
    override = os.environ.get("CLEANIX_CONFIG_DIR")
    if override:
        p = Path(override)
        p.mkdir(parents=True, exist_ok=True)
        return p
    portable = app_dir() / DATA_DIRNAME
    if _writable(portable):
        return portable
    p = _fallback_dir()
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
    show_paths: bool = False          # показывать пути файлов в результатах анализа
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
