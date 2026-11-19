import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from conftest import linux_only, write
from cleanix.catalog import for_platform
from cleanix.core.config import Config
from cleanix.core.i18n import set_language


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    a.setStyle("Fusion")
    return a


def wait_idle(app, *runners, timeout=15):
    t0 = time.time()
    while any(r.busy for r in runners):
        app.processEvents()
        time.sleep(0.01)
        assert time.time() - t0 < timeout, "worker timeout"
    for _ in range(5):
        app.processEvents()


def make_window(app, home, monkeypatch, only=()):
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    from cleanix.ui.main_window import MainWindow
    from cleanix.ui.theme import stylesheet
    cfg = Config(confirm_clean=False, language="en")
    _, items = for_platform("linux")
    cfg.selected = {i.id: (i.id in only) for i in items}      # ВАЖНО: ничего лишнего (например /tmp) не трогаем
    set_language("en")
    app.setStyleSheet(stylesheet("light"))
    w = MainWindow(cfg)
    w.show()
    return w


@linux_only
def test_custom_clean_end_to_end(app, home, monkeypatch):
    write(home / ".cache/thumbnails/a.png", b"x" * 2048)
    write(home / ".local/share/Trash/files/old.txt", b"y" * 100)
    keep = write(home / "Documents/keep.txt")
    w = make_window(app, home, monkeypatch, only=("lin.thumbs", "lin.trash"))
    page = w.page_by_key["custom"]
    w.show_tab("custom")
    page.analyze()
    wait_idle(app, page.runner)
    assert page.table.rowCount() == 2
    counts = {page.table.item(r, 0).text(): page.table.item(r, 1).text() for r in range(2)}
    assert set(counts.values()) == {"1"}
    page.table.selectRow(0)
    assert page.details.count() >= 1
    page.run_clean()                       # результаты уже есть → сразу чистим (confirm выключен)
    wait_idle(app, page.runner)
    assert not (home / ".cache/thumbnails/a.png").exists()
    assert not (home / ".local/share/Trash/files/old.txt").exists()
    assert keep.exists()
    assert "Done" in page.summary.text()
    w.close()


@linux_only
def test_run_cleaner_without_prior_analysis(app, home, monkeypatch):
    write(home / ".cache/thumbnails/a.png")
    w = make_window(app, home, monkeypatch, only=("lin.thumbs",))
    page = w.page_by_key["custom"]
    page.run_clean()
    wait_idle(app, page.runner)
    wait_idle(app, page.runner)
    assert not (home / ".cache/thumbnails/a.png").exists()
    w.close()


@linux_only
def test_easy_page(app, home, monkeypatch):
    write(home / ".cache/thumbnails/a.png", b"x" * 4096)
    w = make_window(app, home, monkeypatch)
    page = w.page_by_key["easy"]
    for k, c in page.checks.items():
        c.setChecked(k == "temp")
    # временные файлы: /tmp сканируем только как анализ, чистим только то, что в домашнем каталоге
    page.cat_items["temp"] = [i for i in page.cat_items["temp"] if i.id in ("lin.thumbs", "lin.trash")]
    page.analyze()
    wait_idle(app, page.runner)
    assert "KB" in page.sizes["temp"].text()
    page.clean()
    wait_idle(app, page.runner)
    assert not (home / ".cache/thumbnails/a.png").exists()
    w.close()


def test_apps_tab_and_stop_button_state(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch)
    page = w.page_by_key["custom"]
    page.set_view("apps")
    assert page.stack.currentWidget() is page.trees["apps"]
    assert not page.ribbon_buttons["stop"].isEnabled() and page.ribbon_buttons["analyze"].isEnabled()
    w.close()


@linux_only
def test_issues_page_scan_and_fix(app, home, monkeypatch):
    write(home / ".config/autostart/dead.desktop", "[Desktop Entry]\nExec=definitely-not-installed-xyz\n")
    w = make_window(app, home, monkeypatch)
    monkeypatch.setattr("cleanix.ui.page_registry.backup_dir", lambda: home / "bk")
    page = w.page_by_key["issues"]
    page.scan()
    wait_idle(app, page.runner)
    assert page.table.rowCount() == 1
    from cleanix.ui import page_registry
    monkeypatch.setattr(page_registry, "ask", lambda *a, **k: True)
    monkeypatch.setattr(page_registry, "info", lambda *a, **k: None)
    page.fix()
    wait_idle(app, page.runner)
    assert not (home / ".config/autostart/dead.desktop").exists()
    assert (home / "bk").is_dir()
    w.close()


def test_tools_panels_load_without_errors(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch)
    tools = w.page_by_key["tools"]
    w.show_tab("tools")
    for key in tools.panels:
        tools.show_panel(key)
        p = tools.panels[key]
        wait_idle(app, p.runner)
    # Startup: переключаем под-вкладки
    sp = tools.panels["startup"]
    for i in range(sp.tabbar.count()):
        sp.tabbar.setCurrentIndex(i)
        wait_idle(app, sp.runner)
    w.close()


def test_settings_persist_and_language_switch(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch)
    reloaded = []
    w._on_reload = lambda tab: reloaded.append(tab)
    st = w.page_by_key["settings"]
    g = st.pages["general"]
    g.lang.setCurrentIndex(g.lang.findData("ru"))
    assert w.cfg.language == "ru" and reloaded == ["settings"]
    ex = st.pages["exclude"]
    ex._add("/some/path")
    assert w.cfg.exclude == ["/some/path"]
    ck = st.pages["cookies"]
    ck.manual.setText("Example.com")
    ck._add_manual()
    assert w.cfg.cookies_keep == ["example.com"]
    w.close()
    set_language("en")


def test_russian_ui_builds_and_has_no_english_tab_titles(app, home, monkeypatch):
    monkeypatch.setenv("HOME", str(home))
    from cleanix.ui.main_window import MainWindow
    set_language("ru")
    w = MainWindow(Config(language="ru"))
    titles = [w.tabbar.tabText(i) for i in range(w.tabbar.count())]
    assert titles[0] == "Очистка" and "Настройки" in titles
    w.close()
    set_language("en")
