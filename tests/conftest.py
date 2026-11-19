import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


linux_only = pytest.mark.skipif(sys.platform.startswith("win"), reason="Linux-specific scenario (fake HOME, /tmp, .desktop)")


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANIX_CONFIG_DIR", str(tmp_path / "cfg"))
    from cleanix.core import i18n
    i18n.set_language("en")
    yield


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def write(path, data=b"x" * 100, age_hours=0):
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    if age_hours:
        t = time.time() - age_hours * 3600
        os.utime(path, (t, t))
    return path
