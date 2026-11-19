"""Определение платформы и прав администратора."""
from __future__ import annotations

import os
import sys

IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")
NAME = "windows" if IS_WINDOWS else "linux"


def is_admin() -> bool:
    """True, если процесс запущен от администратора / root."""
    if IS_WINDOWS:
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def os_description() -> str:
    import platform

    if IS_LINUX:
        try:
            info = platform.freedesktop_os_release()
            return info.get("PRETTY_NAME", "Linux")
        except Exception:
            return "Linux " + platform.release()
    return f"Windows {platform.release()} {platform.machine()}"


def cpu_description() -> str:
    import platform

    return platform.processor() or platform.machine()


def relaunch_as_admin() -> bool:
    """Windows: перезапустить приложение с запросом UAC. Возвращает True, если запрос отправлен."""
    if not IS_WINDOWS:
        return False
    import ctypes

    if getattr(sys, "frozen", False):
        exe, args = sys.executable, ""
    else:
        exe, args = sys.executable, "-m cleanix"
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)  # type: ignore[attr-defined]
    return rc > 32
