from __future__ import annotations

import os
import time
from pathlib import Path

from homebase.cache import daemon_status as ds
from homebase.core.constants import DAEMON_STALE_S


def _status(**overrides: object) -> ds.DaemonStatus:
    values: dict[str, object] = dict(
        pid=os.getpid(),
        version="0.0.0",
        started_ts=time.time(),
        heartbeat_ts=time.time(),
        last_refresh_ts=0,
        last_refresh_s=0.0,
        refreshes=0,
        state="idle",
    )
    values.update(overrides)
    return ds.DaemonStatus(**values)  # type: ignore[arg-type]  # test factory


def test_status_roundtrip(tmp_path: Path) -> None:
    status = _status(refreshes=3, state="refreshing")
    ds.write_daemon_status(tmp_path, status)
    assert ds.read_daemon_status(tmp_path) == status


def test_read_missing_or_broken_status(tmp_path: Path) -> None:
    assert ds.read_daemon_status(tmp_path) is None
    path = ds.daemon_status_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert ds.read_daemon_status(tmp_path) is None


def test_alive_needs_fresh_heartbeat_and_live_pid(tmp_path: Path) -> None:
    now = time.time()
    ds.write_daemon_status(tmp_path, _status(heartbeat_ts=now))
    assert ds.daemon_alive(tmp_path, now) is True
    assert ds.daemon_alive(tmp_path, now + DAEMON_STALE_S + 1) is False


def test_alive_false_for_dead_pid() -> None:
    dead = _status(pid=2**22 + 12345)
    assert ds.daemon_status_alive(dead) is False
    assert ds.daemon_status_alive(None) is False


def test_clear_only_removes_own_status(tmp_path: Path) -> None:
    ds.write_daemon_status(tmp_path, _status(pid=os.getpid()))
    ds.clear_daemon_status(tmp_path, os.getpid() + 1)
    assert ds.read_daemon_status(tmp_path) is not None
    ds.clear_daemon_status(tmp_path, os.getpid())
    assert ds.read_daemon_status(tmp_path) is None
    ds.clear_daemon_status(tmp_path, os.getpid())


def test_status_roundtrip_with_screen_details(tmp_path: Path) -> None:
    status = _status(
        role="owner", activity="full scan (max age)", activity_since=5.0,
        last_reason="max age", active_rows=3, archived_rows=1, health_issues=2,
        health_ts=7.0, health_took_s=0.5, recent=("a", "b"),
    )
    ds.write_daemon_status(tmp_path, status)
    assert ds.read_daemon_status(tmp_path) == status


def test_old_status_file_reads_with_defaults(tmp_path: Path) -> None:
    import json

    path = ds.daemon_status_path(tmp_path)
    path.parent.mkdir(parents=True)
    old = {k: v for k, v in _status().__dict__.items() if k in {
        "pid", "version", "started_ts", "heartbeat_ts", "last_refresh_ts",
        "last_refresh_s", "refreshes", "state",
    }}
    path.write_text(json.dumps(old), encoding="utf-8")
    status = ds.read_daemon_status(tmp_path)
    assert status is not None
    assert (status.role, status.active_rows, status.recent) == ("", -1, ())
