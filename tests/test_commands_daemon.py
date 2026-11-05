from __future__ import annotations

import time
from pathlib import Path

import pytest

from homebase.cache.api import (
    cache_full_scan_ts,
    cache_load_rows,
    cache_store_rows,
    cache_store_rows_merged,
    cache_upsert_rows,
)
from homebase.cache.daemon_status import daemon_lock_path, read_daemon_status
from homebase.cache.owner import (
    release_cache_owner,
    request_cache_refresh,
    try_acquire_cache_owner,
    try_flock,
)
from homebase.commands import daemon
from homebase.core.constants import CACHE_MAX_AGE_S, UI_TICK_WORKTREE_HEALTH_S
from homebase.core.models import ProjectRow


def _row(path: Path) -> ProjectRow:
    return ProjectRow(
        path=path, name=path.name, branch="main", dirty="", last="-", src="fs",
        created="-", tags=[], properties=[], description="", created_ts=0,
        last_ts=0, git_ts=0, opened_ts=0, is_fork=False, is_tmp=False,
        archived=False, restore_target=None, archived_ts=0, wip=False,
        suffix=None, worktree_of="", repo_dir="",
    )


SCAN_DIRTY: list[bool] = []


def _state(base: Path) -> daemon.DaemonState:
    return daemon.DaemonState(base_dir=base, started_ts=time.time(), version="test")


@pytest.fixture
def scan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[Path]:
    rows = [tmp_path / "alpha", tmp_path / "beta"]
    for path in rows:
        path.mkdir()
    monkeypatch.setattr(
        daemon,
        "collect_workspace_rows",
        lambda _base, include_git_dirty=False, size_cache=None: (
            SCAN_DIRTY.append(include_git_dirty) or [_row(p) for p in rows],
            [],
        ),
    )
    monkeypatch.setattr(
        daemon, "scan_worktree_health", lambda *_a, **_k: ([], [], 0, int(time.time()))
    )
    SCAN_DIRTY.clear()
    return rows


def _merged(base: Path, ts: int | None = None) -> None:
    cache_store_rows_merged(
        base, [_row(base / "a")], [], scan_started_ts=ts or int(time.time())
    )


def test_refresh_reason_without_full_scan(tmp_path: Path) -> None:
    assert daemon.refresh_reason(_state(tmp_path), time.time()) == "no full scan yet"
    # A plain store (not an owner rescan) does not count as a full scan.
    cache_store_rows(tmp_path, [_row(tmp_path / "a")], [])
    assert daemon.refresh_reason(_state(tmp_path), time.time()) == "no full scan yet"


def test_refresh_reason_max_age_and_fresh(tmp_path: Path) -> None:
    _merged(tmp_path)
    st = _state(tmp_path)
    st.signature = daemon._signature(tmp_path)
    now = time.time()
    assert daemon.refresh_reason(st, now) is None
    assert daemon.refresh_reason(st, now + CACHE_MAX_AGE_S + 5) == "max age"


def test_refresh_reason_max_age_ignores_single_row_writes(tmp_path: Path) -> None:
    _merged(tmp_path)
    st = _state(tmp_path)
    st.signature = daemon._signature(tmp_path)
    later = time.time() + CACHE_MAX_AGE_S + 5
    cache_upsert_rows(tmp_path, [_row(tmp_path / "b")], touch_refresh_ts=True)
    assert daemon.refresh_reason(st, later) == "max age"


def test_refresh_reason_workspace_changed(tmp_path: Path) -> None:
    _merged(tmp_path)
    st = _state(tmp_path)
    st.signature = daemon._signature(tmp_path)
    (tmp_path / "new-project").mkdir()
    assert daemon.refresh_reason(st, time.time()) == "workspace changed"
    # Checked again only after DAEMON_SIGNATURE_CHECK_S.
    (tmp_path / "another").mkdir()
    assert daemon.refresh_reason(st, time.time()) is None


def test_refresh_reason_request(tmp_path: Path) -> None:
    _merged(tmp_path)
    st = _state(tmp_path)
    request_cache_refresh(tmp_path, "tag update")
    assert daemon.refresh_reason(st, time.time()) == "requested: tag update"


def test_refresh_reason_ignores_request_covered_by_running_scan(tmp_path: Path) -> None:
    _merged(tmp_path)
    st = _state(tmp_path)
    st.signature = daemon._signature(tmp_path)
    request_cache_refresh(tmp_path, "old")
    st.last_scan_started_at = time.time() + 10
    assert daemon.refresh_reason(st, time.time()) is None


def test_refresh_stores_rows_with_git_status(
    tmp_path: Path, scan: list[Path], capsys: pytest.CaptureFixture[str]
) -> None:
    st = _state(tmp_path)
    assert daemon.refresh(st, "test") is True
    active, archived, _ts = cache_load_rows(tmp_path)
    assert sorted(r.path for r in active) == sorted(scan)
    assert archived == []
    assert cache_full_scan_ts(tmp_path) > 0
    assert SCAN_DIRTY == [True]
    assert st.refreshes == 1
    assert "refresh ok reason='test' active=2 archived=0" in capsys.readouterr().out


def test_ensure_owner_waits_for_holder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    held = try_acquire_cache_owner(tmp_path, role="tui")
    assert held is not None
    st = _state(tmp_path)
    assert daemon.ensure_owner(st) is False
    assert daemon.ensure_owner(st) is False
    assert st.state == "waiting"
    out = capsys.readouterr().out
    assert out.count("waiting for cache owner") == 1
    assert " tui)" in out
    release_cache_owner(held)
    assert daemon.ensure_owner(st) is True
    assert st.state == "idle"
    assert "cache owner" in capsys.readouterr().out
    release_cache_owner(st.owner)


def test_sweep_worktree_health_logs_count_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    results = [[{"kind": "x"}], [{"kind": "x"}], []]
    monkeypatch.setattr(
        daemon,
        "scan_worktree_health",
        lambda *_a, **_k: (results.pop(0), [], 1, 0),
    )
    st = _state(tmp_path)
    now = time.time()
    daemon.sweep_worktree_health(st, now)
    daemon.sweep_worktree_health(st, now + 1)  # not due yet
    daemon.sweep_worktree_health(st, now + UI_TICK_WORKTREE_HEALTH_S)
    daemon.sweep_worktree_health(st, now + 2 * UI_TICK_WORKTREE_HEALTH_S)
    out = capsys.readouterr().out
    assert out.count("worktree health issues=1") == 1
    assert out.count("worktree health issues=0") == 1
    assert results == []


def test_refresh_logs_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def boom(*_a: object, **_k: object) -> tuple[list[ProjectRow], list[ProjectRow]]:
        raise OSError("disk gone")

    monkeypatch.setattr(daemon, "collect_workspace_rows", boom)
    st = _state(tmp_path)
    assert daemon.refresh(st, "test") is False
    assert st.state == "error"
    assert "refresh failed reason='test' OSError: disk gone" in capsys.readouterr().out


def test_cmd_daemon_once_refreshes_and_cleans_up(tmp_path: Path, scan: list[Path], capsys: pytest.CaptureFixture[str]) -> None:
    assert daemon.cmd_daemon(tmp_path, once=True) == 0
    out = capsys.readouterr().out
    assert " start pid=" in out
    assert "refresh ok reason='once'" in out
    assert out.rstrip().endswith(" stop")
    assert read_daemon_status(tmp_path) is None
    active, _archived, _ts = cache_load_rows(tmp_path)
    assert len(active) == 2
    # Owner lock released on stop.
    handle = try_acquire_cache_owner(tmp_path, role="tui")
    assert handle is not None
    release_cache_owner(handle)


def test_cmd_daemon_once_gives_up_when_owner_stays_busy(
    tmp_path: Path, scan: list[Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(daemon, "ONCE_OWNER_WAIT_S", 0.0)
    held = try_acquire_cache_owner(tmp_path, role="tui")
    try:
        assert daemon.cmd_daemon(tmp_path, once=True) == 1
    finally:
        release_cache_owner(held)
    assert "gave up waiting for cache owner" in capsys.readouterr().out
    assert SCAN_DIRTY == []


def test_cmd_daemon_refuses_second_instance(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    held = try_flock(daemon_lock_path(tmp_path), "other")
    assert held is not None
    try:
        assert daemon.cmd_daemon(tmp_path, once=True) == 1
        assert "already running" in capsys.readouterr().out
    finally:
        held.close()


def test_state_log_keeps_lines_and_respects_echo(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    st = _state(tmp_path)
    st.echo = False
    st.log("hello")
    assert capsys.readouterr().out == ""
    assert st.log_count == 1
    assert list(st.lines)[-1].endswith(" hello")


def test_refresh_tracks_activity_and_rows(tmp_path: Path, scan: list[Path]) -> None:
    st = _state(tmp_path)
    seen: list[str] = []
    real = daemon.collect_workspace_rows

    def spy(*args: object, **kwargs: object) -> object:
        seen.append(st.activity)
        return real(*args, **kwargs)

    daemon.collect_workspace_rows = spy  # type: ignore[assignment]
    try:
        assert daemon.refresh(st, "max age") is True
    finally:
        daemon.collect_workspace_rows = real  # type: ignore[assignment]
    assert seen == ["full scan (max age)"]
    assert st.activity == ""
    assert (st.active_rows, st.archived_rows, st.last_reason) == (2, 0, "max age")


def test_status_of_carries_screen_details(tmp_path: Path) -> None:
    st = _state(tmp_path)
    st.echo = False
    for i in range(daemon.DAEMON_STATUS_LOG_LINES + 5):
        st.log(f"line {i}")
    st.begin("worktree health sweep")
    status = daemon.status_of(st, now=123.0)
    assert status.heartbeat_ts == 123.0
    assert status.role == "waiting"
    assert status.activity == "worktree health sweep"
    assert len(status.recent) == daemon.DAEMON_STATUS_LOG_LINES
    assert status.recent[-1].endswith(f"line {daemon.DAEMON_STATUS_LOG_LINES + 4}")


def test_run_daemon_with_stop_set_cleans_up(tmp_path: Path, scan: list[Path]) -> None:
    import threading

    st = daemon.new_daemon_state(tmp_path, echo=False)
    stop = threading.Event()
    stop.set()
    assert daemon.run_daemon(st, stop) == 0
    assert st.state == "stopped"
    assert read_daemon_status(tmp_path) is None
    assert list(st.lines)[-1].endswith(" stop")


def test_update_raycast_snapshot_writes_and_logs_errors_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_store_rows(tmp_path, [_row(tmp_path / "a")], [])
    st = _state(tmp_path)
    st.echo = False
    daemon.update_raycast_snapshot(st)
    assert st.raycast_stamp
    assert (tmp_path / ".homebase" / "runtime" / "raycast.json").is_file()
    assert any("raycast snapshot written" in line for line in st.lines)

    def broken(_base: Path, _key: str | None) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(daemon, "refresh_raycast_snapshot", broken)
    daemon.update_raycast_snapshot(st)
    daemon.update_raycast_snapshot(st)
    assert sum("raycast snapshot failed" in line for line in st.lines) == 1
