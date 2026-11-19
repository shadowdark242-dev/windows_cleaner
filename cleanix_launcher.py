"""Точка входа для PyInstaller (и для `python cleanix_launcher.py`)."""
import sys

from cleanix.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
