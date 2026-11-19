"""Сборка одного исполняемого файла через PyInstaller.

    python build.py            # собирает под текущую ОС (Windows → dist/Cleanix.exe, Linux → dist/cleanix)
"""
import subprocess
import sys

NAME = "Cleanix" if sys.platform.startswith("win") else "cleanix"

cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", NAME,
    "--icon", "assets/cleanix.ico",
    "--collect-submodules", "cleanix",
    "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtQuick",
    "--exclude-module", "PySide6.Qt3DCore", "--exclude-module", "PySide6.QtMultimedia",
    "cleanix_launcher.py",
]
# Манифест с запросом прав администратора НЕ добавляем: приложение работает и без них,
# а повышение можно запросить кнопкой в «Настройки → Дополнительно».
sys.exit(subprocess.call(cmd))
