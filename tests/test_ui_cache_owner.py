from __future__ import annotations

import os
import time
from pathlib import Path
from types import SimpleNamespace

from homebase.cache.api import cache_store_rows_merged
from homebase.cache.daemon_status import DaemonStatus, write_daemon_status
from homebase.cache.owner import (
    release_cache_owner,
    request_cache_refresh,
    try_acquire_cache_owner,
)
from homebase.core.constants import UI_TICK_CACHE_OWNER_POLL_S
from homebase.ui.sync import cache_owner


def _alive_daemon(base: Path) -> None:
    write_daemon_status(
        base,
        DaemonStatus(
            pid=os.getpid(), version="t", started_ts=time.time(), heartbeat_ts=time.time(),
            last_refresh_ts=0, last_refresh_s=0.0, refreshes=0, state="idle",
        ),
    )


def _make_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        fast_exit_requested=False,
        cache_worker_running=False,
        cache_owner_handle=None,
        cache_owner_checked_at=0.0,
        full_scan_seen_ts=0,
        active_rows=[],
        archived_rows=[],
        debug_msgs=[],
        reloads=0,
        table_refreshed=0,
        refresh_calls=[],
    )
    app._worker_debug = lambda msg: app.debug_msgs.append(msg)

    def _reload() -> bool:
        app.reloads += 1
        return True

    app._reload_rows_from_cache = _reload
    app._refresh_table = lambda: setattr(app, "table_refreshed", app.table_refreshed + 1)
    app._restore_table_position = lambda: None
    app._refresh_side = lambda: None
    app._start_cache_refresh = lambda reason, force: app.refresh_calls.append((reason, force))
    for key, value in overrides.items():
        setattr(app, key, value)
    return app


def _expire(app: SimpleNamespace) -> None:
    app.cache_owner_checked_at -= UI_TICK_CACHE_OWNER_POLL_S


def test_first_tui_becomes_owner_and_second_does_not(tmp_path: Path) -> None:
    first = _make_app()
    second = _make_app()
    assert cache_owner.is_cache_owner(first, base_dir=tmp_path) is True
    assert cache_owner.is_cache_owner(second, base_dir=tmp_path) is False
    assert first.debug_msgs == ["cache owner: this b"]
    # The second takes over once the first lets go.
    release_cache_owner(first.cache_owner_handle)
    _expire(second)
    assert cache_owner.is_cache_owner(second, base_dir=tmp_path) is True
    release_cache_owner(second.cache_owner_handle)


def test_owner_hands_over_to_live_daemon(tmp_path: Path) -> None:
    app = _make_app()
    assert cache_owner.is_cache_owner(app, base_dir=tmp_path) is True
    _alive_daemon(tmp_path)
    # Cached until the next poll tick.
    assert cache_owner.is_cache_owner(app, base_dir=tmp_path) is True
    _expire(app)
    assert cache_owner.is_cache_owner(app, base_dir=tmp_path) is False
    assert app.cache_owner_handle is None
    assert app.debug_msgs[-1] == "cache owner: handed over to b daemon"
    handle = try_acquire_cache_owner(tmp_path, role="daemon")
    assert handle is not None
    release_cache_owner(handle)


def test_poll_non_owner_reloads_once_per_full_scan(tmp_path: Path) -> None:
    _alive_daemon(tmp_path)
    app = _make_app()
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.reloads == 0
    cache_store_rows_merged(tmp_path, [], [], scan_started_ts=int(time.time()))
    _expire(app)
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.reloads == 1
    assert app.table_refreshed == 1
    _expire(app)
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.reloads == 1


def test_poll_owner_runs_requested_rescan(tmp_path: Path) -> None:
    app = _make_app()
    request_cache_refresh(tmp_path, "tag update")
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.refresh_calls == [("requested: tag update", True)]
    # An owner does not reload after a rescan written to the cache.
    cache_store_rows_merged(tmp_path, [], [], scan_started_ts=int(time.time()))
    _expire(app)
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.reloads == 0
    release_cache_owner(app.cache_owner_handle)


def test_poll_skips_after_fast_exit(tmp_path: Path) -> None:
    app = _make_app(fast_exit_requested=True)
    cache_owner.poll_cache_owner(app, base_dir=tmp_path)
    assert app.cache_owner_handle is None
