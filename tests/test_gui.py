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


def make_window(app, home, monkeypatch, only=(), show_paths=False):
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    from cleanix.ui.main_window import MainWindow
    from cleanix.ui.theme import stylesheet
    cfg = Config(confirm_clean=False, language="en", show_paths=show_paths)
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
    w = make_window(app, home, monkeypatch, only=("lin.thumbs", "lin.trash"), show_paths=True)
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


@linux_only
def test_issues_page_defaults_and_recommended_button(app, home, monkeypatch):
    from cleanix.core.i18n import T
    from cleanix.tools.issues import Category, Issue
    w = make_window(app, home, monkeypatch)
    page = w.page_by_key["issues"]
    page.categories = [Category("a", T("A"), lambda c: [], "safe"), Category("b", T("B"), lambda c: [], "risky")]
    page.cats.clear()
    from PySide6.QtWidgets import QListWidgetItem
    for c in page.categories:
        it = QListWidgetItem(c.id)
        it.setData(Qt.ItemDataRole.UserRole, c.id)
        it.setCheckState(Qt.CheckState.Checked)
        page.cats.addItem(it)
    page._select_recommended()
    assert page._selected_cats() == {"a"}
    page._set_cats(None)
    assert page._selected_cats() == {"a", "b"}
    page.issues = [Issue("a", "p", "d", "l"), Issue("b", "p", "d", "l")]
    page._fill()
    assert [page.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(2)] == [True, False]
    w.close()


def test_app_icons_never_null(app):
    from cleanix.ui.appicons import icon_for
    assert not icon_for("").isNull() and not icon_for("no-such-icon-xyz").isNull()
    assert not icon_for("/no/such/file.exe").isNull()


def test_table_copy_full_text(app):
    from PySide6.QtCore import QItemSelectionModel
    from cleanix.ui.common import cell, make_table
    t = make_table(["A", "B"], 0)
    long_cmd = '"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --win-session-start ' + "x" * 200
    t.insertRow(0)
    t.setItem(0, 0, cell("Edge"))
    t.setItem(0, 1, cell(long_cmd))
    t.selectRow(0)
    t.copy_rows()
    assert QApplication.clipboard().text() == "Edge\t" + long_cmd
    t.copy_cell(0, 1)
    assert QApplication.clipboard().text() == long_cmd


@linux_only
def test_reset_analysis_and_clean_one_option_at_a_time(app, home, monkeypatch):
    a = write(home / ".cache/thumbnails/a.png", b"x" * 300)
    b = write(home / ".local/share/Trash/files/old.txt", b"y" * 100)
    w = make_window(app, home, monkeypatch, only=("lin.thumbs",))
    page = w.page_by_key["custom"]
    # в результатах нет собственных галочек: отметки только в дереве слева
    page.analyze()
    wait_idle(app, page.runner)
    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).data(Qt.ItemDataRole.CheckStateRole) is None
    page.run_clean()
    wait_idle(app, page.runner)
    assert not a.exists() and b.exists()
    assert page.table.item(0, 3).text() == "Cleaned"
    # сброс анализа очищает таблицу
    page.reset_analysis()
    assert page.table.rowCount() == 0 and page.results == []
    # изменение отметок слева тоже сбрасывает устаревшие результаты
    page.analyze()
    wait_idle(app, page.runner)
    leaf = next(l for l in page._iter_leaves() if l.data(0, Qt.ItemDataRole.UserRole) == "lin.trash")
    leaf.setCheckState(0, Qt.CheckState.Checked)
    assert page.table.rowCount() == 0
    w.close()


def test_details_panel_hidden_without_paths(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch, show_paths=False)
    page = w.page_by_key["custom"]
    assert page.details.isHidden()
    g = w.page_by_key["settings"].pages["general"]
    g.paths.setChecked(True)
    assert not page.details.isHidden() and w.cfg.show_paths
    w.close()


def test_accent_presets_are_readable_in_both_themes():
    from cleanix.ui import theme as TH
    for pid, _name, _color in TH.PRESETS + [("custom", None, None)]:
        TH.set_accent(pid, "#7c3aed")
        for th in ("light", "dark"):
            c = TH.palette(th)
            assert TH.contrast(c["accent"], c["accent_text"]) >= 4.5, (pid, th, "text on fill")
            assert TH.contrast(c["accent_dark"], c["panel"]) >= 4.5, (pid, th, "accent as foreground")
            assert "background" in TH.stylesheet(th, "x.svg", "y.svg")
    TH.set_accent("cleanix")


def test_accent_setting_is_saved_and_applied(app, home, monkeypatch):
    from cleanix.ui import theme as TH
    TH.set_accent("cleanix")
    w = make_window(app, home, monkeypatch)
    reloaded = []
    w._on_reload = lambda tab: reloaded.append(tab)
    g = w.page_by_key["settings"].pages["general"]
    g.accent.setCurrentIndex(g.accent.findData("coral"))
    g._accent()
    assert w.cfg.accent == "coral" and reloaded == ["settings"]
    TH.set_accent("coral")
    assert TH.palette("light")["accent"] == "#ff5a5f"
    assert TH.palette("light")["accent_text"] in ("#ffffff", "#111111")
    TH.set_accent("mono")
    assert TH.palette("light")["accent"] == "#111111" and TH.palette("dark")["accent"] == "#f2f2f2"
    TH.set_accent("cleanix")
    w.close()


def test_results_splitter_is_resizable(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch, show_paths=True)
    page = w.page_by_key["custom"]
    sp = page.vsplit
    assert sp.count() == 2 and sp.widget(0) is page.table and sp.widget(1) is page.details
    sp.setSizes([100, 300])
    assert sp.sizes()[1] > sp.sizes()[0]
    w.close()


def test_splitter_and_window_sizes_are_saved_and_restored(app, home, monkeypatch):
    w = make_window(app, home, monkeypatch, show_paths=True)
    page = w.page_by_key["custom"]
    w.resize(1000, 700)
    page.vsplit.setSizes([111, 333])
    page.vsplit.splitterMoved.emit(111, 1)
    page.hsplit_ref = None
    saved = dict(w.cfg.layout)
    assert saved["custom.v"] == page.vsplit.sizes() and len(saved["custom.v"]) == 2
    w.close()
    assert saved.get("custom.v") and w.cfg.layout["window"] == [1000, 700]
    # новое окно с теми же настройками получает те же размеры
    from cleanix.ui.main_window import MainWindow
    w2 = MainWindow(w.cfg)
    w2.show()
    p2 = w2.page_by_key["custom"]
    assert p2.vsplit.sizes()[0] < p2.vsplit.sizes()[1]
    assert (w2.width(), w2.height()) == (1000, 700)
    w2.close()


def test_registry_protected_rows_have_no_checkbox(app, home, monkeypatch):
    from cleanix.tools.issues import Issue
    w = make_window(app, home, monkeypatch)
    page = w.page_by_key["issues"]
    ok = Issue(page.categories[0].id, "p", "d", "loc1")
    prot = Issue(page.categories[0].id, "p", "d", "loc2", extra={"protected": True}, checked=False)
    page.issues, page.protected = [ok, prot], 1
    page._fill()
    page._check_rows(True)
    assert page.table.item(1, 0).data(Qt.ItemDataRole.CheckStateRole) is None
    assert page.table.item(0, 0).checkState() == Qt.CheckState.Checked
    assert page.rb["fix"].isEnabled()
    page.issues, page.protected = [prot], 1
    page._fill()
    assert not page.rb["fix"].isEnabled()
    w.close()


def test_window_restores_maximized_state(app, home, monkeypatch):
    from cleanix.ui.main_window import MainWindow
    monkeypatch.setenv("HOME", str(home))
    cfg = Config(language="en")
    cfg.layout = {"maximized": True, "window": [1000, 700]}
    w = MainWindow(cfg)          # раньше падало: NameError: Qt
    assert w.windowState() & Qt.WindowState.WindowMaximized
    w.close()


def test_disk_analyzer_structure_view_live_and_delete(app, home, monkeypatch, tmp_path):
    from cleanix.ui import page_tools
    write(tmp_path / "data/a/big.mp4", b"x" * 5000)
    write(tmp_path / "data/a/small.txt", b"x" * 100)
    write(tmp_path / "data/b/pic.jpg", b"x" * 700)
    w = make_window(app, home, monkeypatch)
    w.show_tab("tools")
    w.page_by_key["tools"].show_panel("disk")
    p = w.page_by_key["tools"].panels["disk"]
    p.path.setEditText(str(tmp_path / "data"))
    p.start()
    wait_idle(app, p.runner)
    assert p.report.tree.size == 5800 and p.report.total_size == 5800
    p.modes.setCurrentIndex(1)                         # по структуре диска
    top = p.tree.topLevelItem(0)
    assert top.text(1).startswith("5") and top.childCount() == 2
    top.child(0).setExpanded(False)
    # результат остаётся при переключении вкладок
    w.show_tab("custom"); w.show_tab("tools")
    assert p.report.tree.size == 5800 and p.tree.topLevelItemCount() == 1
    # удаляем папку: итоги пересчитываются, строка исчезает
    monkeypatch.setattr(page_tools, "ask", lambda *a, **k: True)
    monkeypatch.setattr(page_tools, "info", lambda *a, **k: None)
    node = next(c for c in p.report.tree.children if c.name == "a")
    p.tree.setCurrentItem(p._items[id(node)])
    p._delete(True)
    wait_idle(app, p.del_runner)
    assert not (tmp_path / "data/a").exists()
    assert p.report.tree.size == 700 and p.report.tree.dirs == 1 and p.report.total_size == 700
    assert p.tree.topLevelItem(0).childCount() == 1
    # открытие вкладок запускает фоновые чтения (список программ и т. п.) — дожидаемся их, иначе поток переживёт окно
    wait_idle(app, *[pn.runner for pn in w.page_by_key["tools"].panels.values()])


def test_disk_analyzer_refuses_to_delete_protected(app, home, monkeypatch, tmp_path):
    from cleanix.ui import page_tools
    write(tmp_path / "x/f.txt")
    w = make_window(app, home, monkeypatch)
    p = w.page_by_key["tools"].panels["disk"]
    p.path.setEditText(str(tmp_path / "x"))
    p.start()
    wait_idle(app, p.runner)
    asked = []
    monkeypatch.setattr(page_tools, "ask", lambda *a, **k: asked.append(1) or True)
    monkeypatch.setattr(page_tools, "info", lambda *a, **k: None)
    root = os.path.abspath(os.sep)                      # корень диска: на любой ОС защищён
    monkeypatch.setattr(p, "_selected_paths", lambda: [root])
    p._delete(True)
    assert not asked and os.path.isdir(root)
