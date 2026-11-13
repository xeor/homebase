from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from textual.widgets import Log

from homebase.cache.clients import ClientInfo
from homebase.cache.daemon_status import DaemonStatus, write_daemon_status
from homebase.cache.owner import peek_cache_refresh_request
from homebase.commands import daemon
from homebase.ui import daemon_app
from homebase.ui.daemon_app import CacheFacts, ProcFacts


def _status(**overrides: object) -> DaemonStatus:
    values: dict[str, object] = dict(
        pid=os.getpid(), version="1.2.3", started_ts=1000.0, heartbeat_ts=1100.0,
        last_refresh_ts=0, last_refresh_s=4.5, refreshes=2, state="idle",
        role="owner", last_reason="max age", active_rows=10, archived_rows=3,
        health_issues=1, health_ts=1090.0, health_took_s=0.2,
    )
    values.update(overrides)
    return DaemonStatus(**values)  # type: ignore[arg-type]  # test factory


def _cache(**overrides: object) -> CacheFacts:
    values: dict[str, object] = dict(
        full_scan_ts=1080, last_write_ts=1095, db_bytes=2048,
        pending_request=None, owner=f"{os.getpid()} daemon",
    )
    values.update(overrides)
    return CacheFacts(**values)  # type: ignore[arg-type]  # test factory


def _rows(section: daemon_app.Section) -> dict[str, str]:
    return dict(section[1])


def test_daemon_section_main_and_activity(tmp_path: Path) -> None:
    status = _status(activity="full scan (max age)", activity_since=1095.0)
    rows = _rows(daemon_app.daemon_section(status, main=True, base_dir=tmp_path, owner="", now=1100.0))
    assert rows["this screen"] == "the running daemon"
    assert rows["running for"] == "1m40s"
    assert rows["background work"] == "cache owner"
    assert rows["doing right now"] == "full scan (max age), 5s"


def test_startup_section_reports_warm_statistics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    listed = tmp_path / "startup-files.txt"
    listed.write_text("x\n", encoding="utf-8")
    os.utime(listed, (1070.0, 1070.0))
    monkeypatch.setattr(daemon_app, "DEFAULT_LIST_PATH", listed)
    status = _status(
        warm_ts=1090.0, warm_runs=12, warm_cold_runs=2, warm_listed=1506,
        warm_files=1490, warm_bytes=24_400_000, warm_took_s=2.09,
    )
    rows = _rows(daemon_app.startup_section(status, 1100.0))
    assert rows["files kept warm"] == "1490 of 1506 listed files, 23.3 MB"
    assert rows["last warm-up"] == "10s ago, took 2.1s (cold: it would have been a slow start)"
    assert rows["warm-ups"] == "12 done, 2 found the files cold, one every 2m00s"
    assert rows["file list from"] == f"{listed}, written 30s ago"


def test_startup_section_before_any_warm_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daemon_app, "DEFAULT_LIST_PATH", tmp_path / "missing.txt")
    rows = _rows(daemon_app.startup_section(_status(), 1100.0))
    assert rows["files kept warm"] == "none read yet"
    assert rows["last warm-up"] == "not yet, runs every 2m00s"
    assert rows["warm-ups"] == "none yet"
    assert rows["file list from"].endswith("(no b TUI has started yet)")
    assert daemon_app.startup_section(None, 1100.0)[1] == [("files kept warm", "-")]


def test_daemon_section_viewer_waiting_and_stopped(tmp_path: Path) -> None:
    now = time.time()
    waiting = _status(role="waiting", heartbeat_ts=now, started_ts=now)
    rows = _rows(daemon_app.daemon_section(waiting, main=False, base_dir=tmp_path, owner="77 tui", now=now))
    assert rows["this screen"] == f"a viewer of pid {os.getpid()}"
    assert rows["background work"] == "waiting for cache owner (77 tui)"
    stale = _status(heartbeat_ts=now - 3600)
    rows = _rows(daemon_app.daemon_section(stale, main=False, base_dir=tmp_path, owner="", now=now))
    assert rows["daemon running"] == "no"
    rows = _rows(daemon_app.daemon_section(None, main=True, base_dir=tmp_path, owner="", now=now))
    assert rows["daemon running"] == "no"


def test_process_section_formats_missing_values() -> None:
    rows = _rows(daemon_app.process_section(ProcFacts(cpu_pct=12.345, rss_bytes=3 * 1024 * 1024)))
    assert rows["cpu right now"] == "12.3%"
    assert rows["memory in use"] == "3.0 MB"
    assert rows["cpu since start"] == rows["memory high mark"] == rows["threads running"] == "-"


def test_cache_section() -> None:
    rows = _rows(daemon_app.cache_section(_status(), _cache(pending_request="tag update"), 1100.0))
    assert rows["projects cached"] == "10 active, 3 archived"
    assert rows["database size"] == "2.0 KB"
    assert rows["last full scan"] == "20s ago"
    assert rows["that scan took"] == "took 4.5s (max age)"
    scanned = _rows(daemon_app.cache_section(_status(last_refresh_ts=1085), _cache(), 1100.0))
    assert scanned["that scan took"] == "took 4.5s, 15s ago (max age)"
    assert rows["next full scan"].startswith("max age in 1m40s")
    assert rows["rescan requested by"] == "tag update"
    assert rows["worktree health"].startswith("1 issues, swept 10s ago (0.2s)")


def test_cache_section_before_first_scan() -> None:
    status = _status(refreshes=0, active_rows=-1, health_issues=-1)
    rows = _rows(daemon_app.cache_section(status, _cache(full_scan_ts=0), 1100.0))
    assert rows["projects cached"] == "-"
    assert rows["that scan took"] == "-"
    assert rows["next full scan"] == "now"
    assert rows["last full scan"] == "-"
    assert rows["rescan requested by"] == "nobody"
    assert rows["worktree health"] == "not swept yet"


def test_clients_section_marks_owner() -> None:
    home = str(Path.home())
    clients = [
        ClientInfo(pid=11, started_ts=1000.0, tty="/dev/ttys004", cwd=f"{home}/base/p"),
        ClientInfo(pid=12, started_ts=1090.0, tty="", cwd="/elsewhere"),
    ]
    rows = _rows(daemon_app.clients_section(clients, "11 tui", 1100.0))
    assert rows["b windows open"] == "2"
    assert rows["pid 11"] == "ttys004  up 1m40s, cache owner  ~/base/p"
    assert rows["pid 12"] == "-  up 10s  /elsewhere"


def test_gather_cache_facts_and_db_bytes(tmp_path: Path) -> None:
    facts = daemon_app.gather_cache_facts(tmp_path)
    assert facts.full_scan_ts == 0
    assert facts.pending_request is None
    db = daemon_app.cache_db_path(tmp_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"x" * 10)
    db.with_name(db.name + "-wal").write_bytes(b"x" * 5)
    assert daemon_app.db_bytes(tmp_path) == 15


def test_render_section_has_all_rows() -> None:
    table = daemon_app.render_section(("X", [("a", "1"), ("b", "2")]))
    assert table.row_count == 2


def test_entry_uses_plain_log_without_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Path, bool]] = []
    monkeypatch.setattr(daemon_app, "cmd_daemon", lambda base, *, once: seen.append((base, once)) or 5)
    monkeypatch.setattr(daemon_app, "run_daemon_screen", lambda base: 9)
    # pytest captures stdout, so there is no terminal here.
    assert daemon_app.daemon_entry(tmp_path) == 5
    assert daemon_app.daemon_entry(tmp_path, once=True) == 5
    assert seen == [(tmp_path, False), (tmp_path, True)]


async def test_main_screen_shows_state_and_keys(tmp_path: Path) -> None:
    st = daemon.DaemonState(base_dir=tmp_path, started_ts=time.time(), version="9.9", echo=False)
    st.log("hello")
    stop = threading.Event()
    app = daemon_app.DaemonApp(tmp_path, st=st, stop=stop, worker=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _rows(app.sections["daemon"])["this screen"] == "the running daemon"
        assert app.query_one("#log", Log).line_count == 1
        st.log("second")
        app.tick()
        assert app.query_one("#log", Log).line_count == 2
        await pilot.press("r")
        assert peek_cache_refresh_request(tmp_path) == "daemon screen"
        st.health_due_at = 99.0
        await pilot.press("w")
        assert st.health_due_at == 0.0
        await pilot.press("q")
    assert stop.is_set()


async def test_viewer_screen_reads_status_file(tmp_path: Path) -> None:
    now = time.time()
    write_daemon_status(tmp_path, _status(heartbeat_ts=now, started_ts=now, recent=("one", "two")))
    app = daemon_app.DaemonApp(tmp_path, st=None, stop=threading.Event(), worker=None)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert _rows(app.sections["daemon"])["this screen"].startswith("a viewer of pid")
        assert app.query_one("#log", Log).line_count == 2
        await pilot.press("w")  # warns, nothing to change
        await pilot.press("q")


async def test_columns_end_level_and_window_list_scrolls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = time.time()
    write_daemon_status(tmp_path, _status(heartbeat_ts=now, started_ts=now))
    many = [
        ClientInfo(pid=pid, started_ts=now, tty=f"/dev/ttys{pid:03}", cwd=str(tmp_path))
        for pid in range(20)
    ]
    monkeypatch.setattr(daemon_app, "list_clients", lambda _base: many)
    app = daemon_app.DaemonApp(tmp_path, st=None, stop=threading.Event(), worker=None)
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        await pilot.pause()
        left = app.query_one("#column0")
        right = app.query_one("#column1")
        panel = app.query_one("#clients-panel")
        assert right.region.x == left.region.right  # columns touch, no gap
        assert right.outer_size.height == left.outer_size.height
        assert panel.region.bottom == left.region.bottom
        assert panel.max_scroll_y > 0  # 20 windows do not fit, so it scrolls
        await pilot.press("q")
