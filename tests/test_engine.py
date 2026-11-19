import os
import sqlite3
import struct

from conftest import linux_only, write
from cleanix.catalog import for_platform, windows as wincat
from cleanix.core import engine
from cleanix.core.config import Config
from cleanix.core.engine import Ctx
from cleanix.core.registry import FakeRegistry


def item(platform, item_id):
    _, items = for_platform(platform)
    return next(i for i in items if i.id == item_id)


def run(ctx, *ids, platform=None):
    items = [item(platform or ctx.platform, i) for i in ids]
    res = engine.analyze(items, ctx)
    return res


def lin_ctx(home, **kw):
    cfg = kw.pop("config", None) or Config()
    return Ctx(config=cfg, env={"HOME": str(home)}, home=home, platform="linux", admin=False,
               tmp_dirs=kw.pop("tmp_dirs", [str(home / "tmp")]), **kw)


# --------------------------------------------------------------- linux
def test_linux_trash_and_thumbnails(home):
    write(home / ".local/share/Trash/files/a.txt")
    write(home / ".local/share/Trash/files/dir/b.txt")
    write(home / ".local/share/Trash/info/a.txt.trashinfo")
    write(home / ".cache/thumbnails/normal/x.png", b"y" * 500)
    ctx = lin_ctx(home)
    res = run(ctx, "lin.trash", "lin.thumbs")
    assert res[0].count == 3 and res[1].size == 500
    engine.clean(res, ctx)
    assert not any((home / ".local/share/Trash/files").iterdir())  # включая пустой каталог dir
    assert (home / ".local/share/Trash/files").is_dir()           # корень остался
    assert not (home / ".cache/thumbnails/normal/x.png").exists()
    assert res[0].removed_count == 3 and not res[0].errors


@linux_only
def test_linux_tmp_respects_age_and_owner(home):
    tmp = home / "tmp"
    write(tmp / "old.log", age_hours=48)
    write(tmp / "fresh.log")
    write(tmp / ".hidden/keep.sock")
    write(tmp / "sub/old2.txt", age_hours=72)
    ctx = lin_ctx(home)
    res = run(ctx, "lin.tmp")[0]
    names = sorted(os.path.basename(f.path) for f in res.found)
    assert names == ["old.log", "old2.txt"]
    engine.clean([res], ctx)
    assert (tmp / "fresh.log").exists() and (tmp / ".hidden/keep.sock").exists()
    assert not (tmp / "old.log").exists()


def test_exclude_protects_files(home):
    write(home / ".cache/thumbnails/a.png")
    write(home / ".cache/thumbnails/keep/b.png")
    cfg = Config(exclude=[str(home / ".cache/thumbnails/keep")])
    ctx = lin_ctx(home, config=cfg)
    res = run(ctx, "lin.thumbs")[0]
    assert res.count == 1
    engine.clean([res], ctx)
    assert (home / ".cache/thumbnails/keep/b.png").exists()


def test_dry_run_deletes_nothing(home):
    f = write(home / ".cache/thumbnails/a.png")
    ctx = lin_ctx(home)
    ctx.dry_run = True
    res = run(ctx, "lin.thumbs")
    engine.clean(res, ctx)
    assert f.exists() and res[0].removed_count == 1


def test_secure_delete_overwrites_and_removes(home):
    f = write(home / ".cache/thumbnails/a.png", b"secret" * 1000)
    ctx = lin_ctx(home, config=Config(secure_passes=3))
    res = run(ctx, "lin.thumbs")
    engine.clean(res, ctx)
    assert not f.exists() and not res[0].errors


def test_admin_items_skipped_without_rights(home):
    ctx = lin_ctx(home)
    res = run(ctx, "lin.apt", "lin.journal")
    assert all(r.skipped == "admin" for r in res)
    engine.clean(res, ctx)
    assert all(r.removed_count == 0 for r in res)


def test_recent_documents_reset_not_deleted(home):
    p = write(home / ".local/share/recently-used.xbel", "<xbel>lots of history</xbel>")
    ctx = lin_ctx(home)
    res = run(ctx, "lin.recent")
    engine.clean(res, ctx)
    assert p.exists() and "lots of history" not in p.read_text()


def test_custom_include(home):
    d = home / "scratch"
    write(d / "a.tmp"); write(d / "b.keep"); write(d / "n/c.tmp")
    cfg = Config(include=[{"path": str(d), "mode": "files", "pattern": "*.tmp", "recursive": True}])
    ctx = lin_ctx(home, config=cfg)
    res = run(ctx, "custom.include")
    assert res[0].count == 2
    engine.clean(res, ctx)
    assert (d / "b.keep").exists() and not (d / "a.tmp").exists()


def test_custom_include_refuses_home_root(home):
    write(home / "important.txt")
    cfg = Config(include=[{"path": str(home), "mode": "all", "pattern": "*"}, {"path": "/", "mode": "all"}])
    ctx = lin_ctx(home, config=cfg)
    assert run(ctx, "custom.include")[0].count == 0


# ------------------------------------------------------------- browsers
def make_cookies(path, hosts, table="cookies", col="host_key"):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {table} ({col} TEXT, name TEXT)")
    con.executemany(f"INSERT INTO {table} VALUES (?, 'c')", [(h,) for h in hosts])
    con.commit(); con.close()


def hosts_in(path, table="cookies", col="host_key"):
    con = sqlite3.connect(path)
    try:
        return sorted(r[0] for r in con.execute(f"SELECT {col} FROM {table}"))
    finally:
        con.close()


def test_chrome_cache_and_history_linux(home):
    write(home / ".config/google-chrome/Default/History", b"h" * 10)
    write(home / ".config/google-chrome/Default/Login Data", b"p" * 10)
    write(home / ".cache/google-chrome/Default/Cache/Cache_Data/f_1", b"c" * 1000)
    write(home / ".config/google-chrome/Default/Service Worker/CacheStorage/a/b", b"s" * 10)
    write(home / ".config/google-chrome/Default/Bookmarks", b"keep")
    ctx = lin_ctx(home)
    res = run(ctx, "br.chrome.cache", "br.chrome.history", "br.chrome.passwords")
    assert res[0].count == 2 and res[1].count == 1
    engine.clean(res[:2], ctx)
    assert (home / ".config/google-chrome/Default/Bookmarks").exists()
    assert (home / ".config/google-chrome/Default/Login Data").exists()   # пароли не выбирали
    assert not (home / ".cache/google-chrome/Default/Cache/Cache_Data/f_1").exists()


def test_cookie_keep_list(home):
    db = home / ".config/google-chrome/Default/Network/Cookies"
    make_cookies(db, [".google.com", "mail.google.com", "tracker.net", ".example.org"])
    ctx = lin_ctx(home, config=Config(cookies_keep=["google.com"]))
    res = run(ctx, "br.chrome.cookies")
    engine.clean(res, ctx)
    assert hosts_in(db) == [".google.com", "mail.google.com"]


def test_cookies_without_keep_list_deleted(home):
    db = home / ".config/google-chrome/Default/Network/Cookies"
    make_cookies(db, ["a.com"])
    ctx = lin_ctx(home)
    engine.clean(run(ctx, "br.chrome.cookies"), ctx)
    assert not db.exists()


def test_firefox_history_keeps_bookmarks(home):
    prof = home / ".mozilla/firefox/abc.default"
    write(prof / "prefs.js", b"")
    db = prof / "places.sqlite"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
        CREATE TABLE moz_historyvisits (id INTEGER PRIMARY KEY, place_id INT);
        CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, fk INT);
        INSERT INTO moz_places VALUES (1,'http://a'),(2,'http://b');
        INSERT INTO moz_historyvisits VALUES (1,1),(2,2);
        INSERT INTO moz_bookmarks VALUES (1,2);
    """)
    con.commit(); con.close()
    ctx = lin_ctx(home)
    engine.clean(run(ctx, "br.firefox.history"), ctx)
    con = sqlite3.connect(db)
    assert [r[0] for r in con.execute("SELECT url FROM moz_places")] == ["http://b"]
    assert con.execute("SELECT count(*) FROM moz_historyvisits").fetchone()[0] == 0
    con.close()


# -------------------------------------------------------------- windows
def win_ctx(tmp_path, reg=None, **kw):
    root = tmp_path / "win"
    env = {
        "LOCALAPPDATA": str(root / "AppData/Local"), "APPDATA": str(root / "AppData/Roaming"),
        "TEMP": str(root / "AppData/Local/Temp"), "WINDIR": str(root / "Windows"),
        "PROGRAMDATA": str(root / "ProgramData"), "USERPROFILE": str(root / "Users/me"),
        "SystemDrive": str(root / "C"),
    }
    return Ctx(config=kw.pop("config", None) or Config(), env=env, platform="windows",
               registry=reg or FakeRegistry(), admin=False), root


def test_windows_temp_thumbs_jumplists(tmp_path):
    ctx, r = win_ctx(tmp_path)
    write(r / "AppData/Local/Temp/old.tmp", age_hours=30)
    write(r / "AppData/Local/Temp/new.tmp")
    write(r / "AppData/Local/Microsoft/Windows/Explorer/thumbcache_256.db")
    write(r / "AppData/Local/Microsoft/Windows/Explorer/other.db")
    write(r / "AppData/Roaming/Microsoft/Windows/Recent/AutomaticDestinations/x.automaticDestinations-ms")
    write(r / "AppData/Roaming/Microsoft/Windows/Recent/doc.lnk")
    res = run(ctx, "win.sys.temp", "win.exp.thumbs", "win.exp.jump", "win.exp.recent")
    assert [x.count for x in res] == [1, 1, 1, 1]
    engine.clean(res, ctx)
    assert (r / "AppData/Local/Temp/new.tmp").exists()
    assert (r / "AppData/Local/Microsoft/Windows/Explorer/other.db").exists()
    assert not (r / "AppData/Roaming/Microsoft/Windows/Recent/doc.lnk").exists()


def test_windows_registry_mru(tmp_path):
    reg = FakeRegistry()
    key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\RunMRU"
    reg.add(key, {"a": "cmd\\1", "MRUList": "a"})
    reg.add(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist\{G}\Count", {"x": b"1"})
    ctx, _ = win_ctx(tmp_path, reg)
    res = run(ctx, "win.exp.runmru", "win.adv.userassist")
    assert res[0].count == 2 and res[1].count == 1
    engine.clean(res, ctx)
    assert reg.enum_values(key) == []
    assert reg.key_exists(key)


def test_windows_registry_keys_removed(tmp_path):
    reg = FakeRegistry()
    base = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\MenuOrder"
    reg.add(base + r"\Start Menu2\Programs", {"Order": b"zz"})
    ctx, _ = win_ctx(tmp_path, reg)
    res = run(ctx, "win.adv.menuorder")
    engine.clean(res, ctx)
    assert not reg.key_exists(base + r"\Start Menu2")
    assert reg.key_exists(base)


def make_lnk(path, target):
    t = target.encode() + b"\0"
    info_hdr = 28
    info = struct.pack("<IIIIIII", info_hdr + len(t) + 1, info_hdr, 1, 0, info_hdr, 0, 0) + t + b"\0"
    hdr = struct.pack("<I", 0x4C) + b"\0" * 16 + struct.pack("<I", 0x2) + b"\0" * (0x4C - 24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hdr + info)


def test_lnk_target_and_broken_shortcuts(tmp_path):
    real = write(tmp_path / "real.exe")
    ctx, r = win_ctx(tmp_path)
    make_lnk(r / "Users/me/Desktop/ok.lnk", str(real))
    make_lnk(r / "Users/me/Desktop/dead.lnk", str(tmp_path / "gone.exe"))
    assert wincat.lnk_target(str(r / "Users/me/Desktop/ok.lnk")) == str(real)
    res = run(ctx, "win.sys.desklnk")[0]
    assert [os.path.basename(f.path) for f in res.found] == ["dead.lnk"]


def test_windows_items_without_registry_do_not_crash(tmp_path):
    ctx, _ = win_ctx(tmp_path)
    ctx.registry = None
    _, items = for_platform("windows")
    res = engine.analyze([i for i in items if not i.admin], ctx)
    assert all(not r.errors for r in res)


def test_every_item_scans_cleanly_on_empty_system(home):
    ctx = lin_ctx(home)
    _, items = for_platform("linux")
    res = engine.analyze([i for i in items if not i.admin], ctx)
    assert all(not r.errors for r in res)


# ------------------------------------------------- реестр: проблемы
from cleanix.tools import registry_cleaner as RC, linux_issues as LI
from cleanix.tools.issues import IssueCtx, scan_all
from cleanix.core import registry as R


def rctx(reg, tmp_path):
    return IssueCtx(reg, {"WINDIR": str(tmp_path / "Windows"), "APPDATA": str(tmp_path / "ad"), "PROGRAMDATA": str(tmp_path / "pd")}, platform="windows")


def test_registry_scanners_find_only_real_problems(tmp_path):
    real = write(tmp_path / "bin/app.exe")
    gone = str(tmp_path / "bin/gone.exe")
    reg = R.FakeRegistry()
    cv = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion"
    reg.add(cv + r"\SharedDLLs", {str(real): 1, gone.replace("/", "\\") if False else gone: 1})
    reg.add(cv + r"\App Paths\good.exe", {"": str(real)})
    reg.add(cv + r"\App Paths\bad.exe", {"": gone})
    reg.add(cv + r"\Run", {"Good": f'"{real}" -x', "Bad": f'"{gone}" /s', "Cmd": "notepad.exe"})
    reg.add(cv + r"\Uninstall\Dead", {"DisplayName": "Dead App", "UninstallString": f'"{gone}" /u'})
    reg.add(cv + r"\Uninstall\Msi", {"DisplayName": "Msi App", "UninstallString": "MsiExec.exe /X{1}"})
    reg.add(cv + r"\Uninstall\Alive", {"DisplayName": "Alive", "UninstallString": str(real)})
    reg.add(r"HKLM\SOFTWARE\Classes\CLSID\{A}\InprocServer32", {"": gone})
    reg.add(r"HKLM\SOFTWARE\Classes\CLSID\{B}\InprocServer32", {"": str(real)})
    reg.add(r"HKLM\SOFTWARE\Classes\.zzz", {"": "zzzfile"})
    reg.add(r"HKLM\SOFTWARE\Classes\.ok", {"": "okfile"})
    reg.add(r"HKLM\SOFTWARE\Classes\okfile")
    ctx = rctx(reg, tmp_path)
    issues = scan_all(RC.CATEGORIES, ctx)
    by = {}
    for i in issues:
        by.setdefault(i.category, []).append(i)
    assert len(by["shared_dlls"]) == 1 and by["shared_dlls"][0].data == gone
    assert [i.location.split("\\")[-1] for i in by["app_paths"]] == ["bad.exe"]
    assert [i.value_name for i in by["startup"]] == ["Bad"]
    assert len(by["obsolete"]) == 1 and "Dead App" in by["obsolete"][0].data
    assert [i.location.split("\\")[-1] for i in by["activex"]] == ["{A}"]
    assert [i.data.split(" ")[0] for i in by["extensions"]] == [".zzz"]
    assert "error" not in {i.kind for i in issues}


def test_registry_fix_creates_backup_and_removes(tmp_path):
    reg = R.FakeRegistry()
    key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    reg.add(key, {"Bad": '"C:\\nope\\x.exe"', "Keep": "x"})
    reg.set_value(key, "Num", 5, R.REG_DWORD)
    issue = [i for i in RC.scan_startup(rctx(reg, tmp_path))][0]
    backup = tmp_path / "b.reg"
    fixed, errs = RC.fix([issue], reg, str(backup))
    assert fixed == 1 and not errs
    assert [n for n, _, _ in reg.enum_values(key)] == ["Keep", "Num"]
    text = backup.read_text(encoding="utf-16")
    assert text.startswith("Windows Registry Editor Version 5.00")
    assert '"Bad"="\\"C:\\\\nope\\\\x.exe\\""' in text and "dword:00000005" in text


def test_registry_fix_aborts_when_backup_fails(tmp_path):
    reg = R.FakeRegistry()
    key = r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    reg.add(key, {"Bad": '"C:\\nope\\x.exe"'})
    issue = RC.scan_startup(rctx(reg, tmp_path))[0]
    fixed, errs = RC.fix([issue], reg, str(tmp_path / "no/such/dir/b.reg"))
    assert fixed == 0 and errs and reg.get_value(key, "Bad")


@linux_only
def test_linux_issues_and_fix(home):
    apps = home / ".local/share/applications"
    write(apps / "good.desktop", "[Desktop Entry]\nType=Application\nExec=/bin/sh -c x\n")
    write(apps / "bad.desktop", "[Desktop Entry]\nType=Application\nExec=/opt/nothing/run %U\n")
    write(home / ".config/autostart/dead.desktop", "[Desktop Entry]\nExec=definitely-not-installed-xyz\n")
    (home / ".local/bin").mkdir(parents=True)
    os.symlink("/nonexistent/target", home / ".local/bin/broken")
    write(home / ".config/mimeapps.list", "[Default Applications]\ntext/plain=ghost.desktop;\n")
    write(home / ".local/share/recently-used.xbel",
          '<xbel><bookmark href="file:///no/such/file.txt" added="1"><info/></bookmark></xbel>')
    ctx = IssueCtx(None, {"HOME": str(home)}, home, "linux")
    issues = scan_all(LI.CATEGORIES, ctx)
    cats = sorted(i.category for i in issues)
    assert cats == ["autostart", "launchers", "mimeapps", "recent", "symlinks"]
    fixed, errs = LI.fix(issues, str(home / "bk"))
    assert fixed == 5 and not errs
    assert (apps / "good.desktop").exists() and not (apps / "bad.desktop").exists()
    assert "no/such" not in (home / ".local/share/recently-used.xbel").read_text()
    assert "ghost" not in (home / ".config/mimeapps.list").read_text()
    assert scan_all(LI.CATEGORIES, ctx) == []


# ------------------------------------------------------------ инструменты
import threading
from cleanix.tools import startup as ST, duplicates as DUP, wiper as WP, diskanalyzer as DA, uninstall as UN, trash as TR
from cleanix import scheduler as SCH


def test_duplicates(tmp_path):
    write(tmp_path / "a/one.bin", b"A" * 200_000)
    write(tmp_path / "b/two.bin", b"A" * 200_000)
    write(tmp_path / "b/three.bin", b"A" * 199_999 + b"B")    # тот же размер-1 / отличается
    write(tmp_path / "c/small1.txt", b"hi"); write(tmp_path / "c/small2.txt", b"hi")
    write(tmp_path / "c/other.txt", b"yo")
    groups = DUP.find_duplicates([str(tmp_path)])
    sets = [sorted(os.path.basename(p) for p in g.paths) for g in groups]
    assert ["one.bin", "two.bin"] in sets and ["small1.txt", "small2.txt"] in sets and len(sets) == 2
    assert DUP.find_duplicates([str(tmp_path)], min_size=1000)[0].size == 200_000


def test_duplicates_same_name_only(tmp_path):
    write(tmp_path / "a/x.txt", b"same"); write(tmp_path / "b/x.txt", b"same"); write(tmp_path / "b/y.txt", b"same")
    g = DUP.find_duplicates([str(tmp_path)], same_name=True)
    assert len(g) == 1 and sorted(os.path.basename(p) for p in g[0].paths) == ["x.txt", "x.txt"]


def test_duplicates_hardlinks_not_reported(tmp_path):
    write(tmp_path / "a.txt", b"data")
    os.link(tmp_path / "a.txt", tmp_path / "b.txt")
    assert DUP.find_duplicates([str(tmp_path)]) == []


def test_disk_analyzer(tmp_path):
    write(tmp_path / "x.jpg", b"1" * 1000); write(tmp_path / "s/y.mp4", b"1" * 5000); write(tmp_path / "z.xyz", b"1" * 10)
    rep = DA.analyze(str(tmp_path))
    assert rep.size["pictures"] == 1000 and rep.size["video"] == 5000 and rep.count["other"] == 1
    assert rep.largest()[0][0] == 5000 and rep.total_size == 6010


def test_wipe_free_space_leaves_no_files(tmp_path):
    n = WP.wipe_free_space(str(tmp_path), passes=3, reserve=0, limit=3 * 1024 * 1024)
    assert n == 9 * 1024 * 1024 and list(tmp_path.iterdir()) == []


def test_shred_paths(tmp_path):
    write(tmp_path / "d/a.txt"); write(tmp_path / "d/s/b.txt")
    assert WP.shred_paths([str(tmp_path / "d")], 1) == [] and not (tmp_path / "d").exists()


def test_trash_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    f = write(tmp_path / "gone.txt")
    TR.move_to_trash(str(f), windows=False)
    assert not f.exists() and (tmp_path / "data/Trash/files/gone.txt").exists()
    assert "Path=" in (tmp_path / "data/Trash/info/gone.txt.trashinfo").read_text()


@linux_only
def test_linux_autostart_toggle_and_delete(home):
    ctx = lin_ctx(home)
    ctx.env["XDG_CONFIG_DIRS"] = str(home / "etc")
    write(home / "etc/autostart/sys.desktop", "[Desktop Entry]\nName=SysApp\nExec=sysapp\n")
    write(home / ".config/autostart/me.desktop", "[Desktop Entry]\nName=MyApp\nExec=myapp\n")
    es = {e.name: e for e in ST.lin_run(ctx)}
    assert es["SysApp"].enabled and es["MyApp"].enabled
    ST.set_enabled(ctx, es["SysApp"], False)             # системную отключаем копией в user-dir
    assert (home / ".config/autostart/sys.desktop").read_text().count("Hidden=true") == 1
    assert "Hidden" not in (home / "etc/autostart/sys.desktop").read_text()
    ST.set_enabled(ctx, es["MyApp"], False)
    assert {e.name: e.enabled for e in ST.lin_run(ctx)} == {"SysApp": False, "MyApp": False}
    ST.set_enabled(ctx, es["MyApp"], True)
    assert {e.name: e.enabled for e in ST.lin_run(ctx)}["MyApp"] is True
    ST.delete_entry(ctx, es["MyApp"])
    assert "MyApp" not in {e.name for e in ST.lin_run(ctx)}


def test_cron_parse_and_rewrite():
    text = "MAILTO=x\n# comment\n0 5 * * * /usr/bin/backup --full\n@reboot /opt/x/run\n"
    es = ST.parse_crontab(text)
    assert [e.name for e in es] == ["backup", "run"] and es[0].location == "cron: 0 5 * * *"
    off = ST.cron_rewrite(text, es[0].data["line"], "off")
    assert ST.parse_crontab(off)[0].enabled is False
    assert ST.cron_rewrite(off, es[0].data["line"], "on") == text
    assert "backup" not in ST.cron_rewrite(text, es[0].data["line"], "delete")


def test_windows_startup_entries_and_toggle(tmp_path):
    reg = FakeRegistry()
    run = r"HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    reg.add(run, {"Discord": '"C:\\d.exe"', "Steam": "steam.exe"})
    appr = r"HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
    reg.set_value(appr, "Discord", b"\x03" + b"\0" * 11, R.REG_BINARY)
    ctx, _ = win_ctx(tmp_path, reg)
    es = {e.name: e for e in ST.win_run_entries(ctx)}
    assert es["Discord"].enabled is False and es["Steam"].enabled is True and es["Steam"].location == "HKCU:Run"
    ST.set_enabled(ctx, es["Steam"], False)
    assert {e.name: e.enabled for e in ST.win_run_entries(ctx)}["Steam"] is False
    ST.set_enabled(ctx, es["Steam"], True)
    assert {e.name: e.enabled for e in ST.win_run_entries(ctx)}["Steam"] is True
    ST.delete_entry(ctx, es["Discord"])
    assert "Discord" not in {e.name for e in ST.win_run_entries(ctx)}


def test_package_parsers():
    pk = UN.parse_dpkg("git\t1:2.43\t30000\tDebian\nlibfoo:amd64\t1\t5\tx\n", {"git"})
    assert [p.name for p in pk] == ["git"] and pk[0].size == 30000 * 1024
    assert UN.parse_snap("Name Version Rev Tracking Publisher Notes\nvlc 3.0 1 stable videolan -\ncore22 1 1 x y -\n")[0].name == "vlc"
    assert UN.parse_flatpak("GIMP\torg.gimp.GIMP\t2.10\n")[0].ident == "org.gimp.GIMP"
    assert UN.uninstall_command(pk[0])[-1] == "git"


def test_windows_uninstall_list(tmp_path):
    reg = FakeRegistry()
    u = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    reg.add(u + r"\A", {"DisplayName": "Real App", "UninstallString": "x.exe", "EstimatedSize": 2048, "InstallDate": "20240131"})
    reg.add(u + r"\B", {"DisplayName": "Hidden", "UninstallString": "y", "SystemComponent": 1})
    reg.add(u + r"\C", {"DisplayName": "Patch", "UninstallString": "z", "ParentKeyName": "A"})
    ctx, _ = win_ctx(tmp_path, reg)
    ps = UN.list_windows(ctx)
    assert [p.name for p in ps] == ["Real App"] and ps[0].size == 2048 * 1024 and ps[0].date == "31.01.2024"


def test_scheduler_lines():
    line = SCH.cron_line({"freq": "weekly", "time": "07:30"})
    assert line.startswith("30 7 * * 1 ") and SCH.CRON_MARK in line
    merged = SCH.merge_cron("0 1 * * * old\n" + line + "\n", SCH.cron_line({"freq": "daily", "time": "10:05"}))
    assert merged.count(SCH.CRON_MARK) == 1 and "5 10 * * *" in merged and "old" in merged
    assert SCH.CRON_MARK not in SCH.merge_cron(merged, None)
    args = SCH.windows_args({"freq": "daily", "time": "09:00"})
    assert args[:3] == ["schtasks", "/create", "/tn"] and "/st" in args and "09:00" in args
