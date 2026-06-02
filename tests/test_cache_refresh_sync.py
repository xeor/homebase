from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import CacheRefreshOutcome, OperationResult, ProjectRow
from homebase.ui.sync import cache_refresh


class InlineThread:
    def __init__(self, *, target, daemon=True) -> None:
        self.target = target

    def start(self) -> None:
        self.target()


def _make_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        fast_exit_requested=False,
        cache_worker_running=False,
        cache_refresh_pending=False,
        cache_refresh_pending_force=False,
        cache_refresh_pending_reason="",
        cache_last_refresh_ts=0,
        cache_worker_note="",
        cache_worker_started_ts=0.0,
        cache_worker_last_done_ts=0.0,
        cache_refresh_epoch=0,
        active_rows=[],
        archived_rows=[],
        busy_starts=[],
        busy_stops=0,
        debug_msgs=[],
        side_refreshed=0,
        table_refreshed=0,
        restore_called=0,
        thread_calls=[],
        logged_errors=[],
        after_refresh_calls=[],
    )
    app._busy_start = lambda msg: app.busy_starts.append(msg)
    app._busy_stop = lambda: app.__dict__.__setitem__(
        "busy_stops", app.busy_stops + 1
    )
    app._worker_debug = lambda msg: app.debug_msgs.append(msg)
    app._refresh_side = lambda: app.__dict__.__setitem__(
        "side_refreshed", app.side_refreshed + 1
    )
    app._refresh_table = lambda: app.__dict__.__setitem__(
        "table_refreshed", app.table_refreshed + 1
    )
    app._restore_table_position = lambda: app.__dict__.__setitem__(
        "restore_called", app.restore_called + 1
    )
    app._log_error_counted = lambda key, msg: app.logged_errors.append((key, msg))
    app.call_from_thread = lambda fn, *args, **kw: (
        app.thread_calls.append((fn.__name__, args, kw)) or fn(*args, **kw)
    )
    app.call_after_refresh = lambda fn: app.after_refresh_calls.append(fn)
    app._on_cache_refresh_done = lambda outcome: app.__dict__.__setitem__(
        "_done_outcome", outcome
    )
    app._reload_rows_from_cache = lambda: True
    app._start_cache_refresh = lambda reason, *, force: app.__dict__.setdefault(
        "_pending_start", []
    ).append((reason, force))
    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_start_cache_refresh_noop_on_fast_exit(tmp_path: Path) -> None:
    app = _make_app(fast_exit_requested=True)
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="manual", force=True,
    )
    assert app.cache_worker_running is False


def test_start_cache_refresh_marks_pending_when_worker_running(
    tmp_path: Path,
) -> None:
    app = _make_app(cache_worker_running=True)
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="manual", force=False,
    )
    assert app.cache_refresh_pending is True
    assert app.cache_refresh_pending_reason == "manual"


def test_start_cache_refresh_respects_max_age(tmp_path: Path) -> None:
    app = _make_app(cache_last_refresh_ts=int(time.time()))
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="manual", force=False,
    )
    assert app.cache_worker_running is False


def test_start_cache_refresh_launches_thread(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(threading, "Thread", InlineThread)
    monkeypatch.setattr(
        cache_refresh,
        "collect_workspace_rows",
        lambda _bd, include_git_dirty=False, size_cache=None: ([], []),
    )
    app = _make_app()
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="manual", force=True,
    )
    assert app.cache_worker_running is True
    # call_from_thread routes outcome to _on_cache_refresh_done
    assert "_done_outcome" in app.__dict__
    outcome = app.__dict__["_done_outcome"]
    assert outcome.fresh_active == []


def test_start_cache_refresh_handles_collect_error(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(threading, "Thread", InlineThread)

    def boom(*_a, **_k):
        raise OSError("nope")

    monkeypatch.setattr(cache_refresh, "collect_workspace_rows", boom)
    app = _make_app()
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="manual", force=True,
    )
    outcome = app.__dict__["_done_outcome"]
    assert outcome.result.ok is False
    assert "OSError" in outcome.result.error


def test_on_cache_refresh_done_logs_error(tmp_path: Path) -> None:
    app = _make_app()
    outcome = CacheRefreshOutcome(1, None, None, OperationResult.failure("disk"))
    cache_refresh.on_cache_refresh_done(app, base_dir=tmp_path, outcome=outcome)
    assert app.logged_errors
    assert app.busy_stops == 1


def test_on_cache_refresh_done_stores_rows_when_epoch_matches(
    tmp_path: Path, monkeypatch
) -> None:
    app = _make_app(cache_refresh_epoch=1)
    monkeypatch.setattr(
        cache_refresh, "cache_store_rows", lambda _bd, _a, _r: 100
    )
    outcome = CacheRefreshOutcome(1, [], [], OperationResult.success())
    cache_refresh.on_cache_refresh_done(app, base_dir=tmp_path, outcome=outcome)
    assert app.cache_last_refresh_ts == 100
    assert app.table_refreshed == 1


def test_on_cache_refresh_done_handles_store_error(
    tmp_path: Path, monkeypatch
) -> None:
    app = _make_app(cache_refresh_epoch=1)

    def boom(*_a):
        raise OSError("disk")

    monkeypatch.setattr(cache_refresh, "cache_store_rows", boom)
    outcome = CacheRefreshOutcome(1, [], [], OperationResult.success())
    cache_refresh.on_cache_refresh_done(app, base_dir=tmp_path, outcome=outcome)
    assert any(key == "cache_store" for key, _ in app.logged_errors)


def test_on_cache_refresh_done_processes_pending(
    tmp_path: Path, monkeypatch
) -> None:
    app = _make_app(
        cache_refresh_pending=True,
        cache_refresh_pending_force=True,
        cache_refresh_pending_reason="next",
    )
    outcome = CacheRefreshOutcome(99, [], [], OperationResult.success())
    monkeypatch.setattr(
        cache_refresh, "cache_store_rows", lambda *_a: 0
    )
    cache_refresh.on_cache_refresh_done(app, base_dir=tmp_path, outcome=outcome)
    assert app.cache_refresh_pending is False
    assert app.after_refresh_calls
    # Triggering the deferred call lands in _start_cache_refresh.
    app.after_refresh_calls[0]()
    assert ("next", True) in app.__dict__.get("_pending_start", [])


def test_on_cache_refresh_done_fast_exit_short_circuits(tmp_path: Path) -> None:
    app = _make_app(fast_exit_requested=True)
    outcome = CacheRefreshOutcome(1, None, None, OperationResult.failure("x"))
    cache_refresh.on_cache_refresh_done(app, base_dir=tmp_path, outcome=outcome)
    assert app.busy_stops == 0  # no work done


def test_start_cache_refresh_seeds_size_cache_from_existing_rows(
    tmp_path: Path, monkeypatch
) -> None:
    row = ProjectRow(
        path=tmp_path / "p",
        name="p",
        branch="main",
        dirty="",
        last="2026",
        src="git",
        created="2026",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        size_bytes=4096,
        size_refresh_count=3,
    )
    captured: dict[str, object] = {}

    def fake_collect(_bd, include_git_dirty=False, size_cache=None):
        captured["size_cache"] = size_cache
        return [], []

    monkeypatch.setattr(threading, "Thread", InlineThread)
    monkeypatch.setattr(cache_refresh, "collect_workspace_rows", fake_collect)
    app = _make_app()
    app.active_rows = [row]
    cache_refresh.start_cache_refresh(
        app, base_dir=tmp_path, cache_max_age_s=60, reason="seed", force=True,
    )
    seed = captured["size_cache"]
    assert isinstance(seed, dict)
    assert len(seed) == 1
