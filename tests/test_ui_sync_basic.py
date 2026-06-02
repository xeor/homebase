from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.ui.sync import cache_state
from homebase.ui.sync import sync as ui_sync


def _make_sync_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        fast_exit_requested=False,
        tag_sync_running=False,
        tag_sync_pending=False,
        tag_sync_pending_reason="",
        cache_worker_running=False,
        workspace_sig_due_at=0.0,
        workspace_sig_last="",
        workspace_sig_last_ts=0.0,
        debug_msgs=[],
        request_calls=[],
        cache_refresh_calls=[],
        thread_calls=[],
    )

    def _request_tag_sync(reason: str) -> None:
        app.request_calls.append(reason)

    def _start_cache_refresh(reason: str, force: bool) -> None:
        app.cache_refresh_calls.append((reason, force))

    app._request_tag_sync = _request_tag_sync
    app._start_cache_refresh = _start_cache_refresh
    app._worker_debug = lambda msg: app.debug_msgs.append(msg)
    app._workspace_quick_signature = lambda: app.__dict__.get("_sig", "sig1")
    app._refresh_side = lambda: app.__dict__.__setitem__(
        "_side_refreshed", True
    )

    def _log_error_counted(key: str, msg: str) -> None:
        app.__dict__.setdefault("_logged_errors", []).append((key, msg))

    app._log_error_counted = _log_error_counted

    def call_from_thread(fn, *args, **kwargs) -> None:
        app.thread_calls.append((fn.__name__, args, kwargs))
        fn(*args, **kwargs)

    app.call_from_thread = call_from_thread
    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_request_tag_sync_noop_when_fast_exit() -> None:
    app = _make_sync_app(fast_exit_requested=True)
    ui_sync.request_tag_sync(app, base_dir=Path("/x"), reason="manual")
    assert app.tag_sync_running is False


def test_request_tag_sync_queues_when_already_running() -> None:
    app = _make_sync_app(tag_sync_running=True)
    ui_sync.request_tag_sync(app, base_dir=Path("/x"), reason="manual")
    assert app.tag_sync_pending is True
    assert app.tag_sync_pending_reason == "manual"


def test_request_tag_sync_runs_thread_and_invokes_callback(
    tmp_path: Path, monkeypatch
) -> None:
    # Replace sync_tag_symlinks to avoid touching filesystem.
    monkeypatch.setattr(ui_sync, "sync_tag_symlinks", lambda _bd: None)
    # Replace Thread to run sync inline so we can observe state.
    import threading

    class InlineThread:
        def __init__(self, *, target, daemon=True) -> None:
            self.target = target

        def start(self) -> None:
            self.target()

    monkeypatch.setattr(threading, "Thread", InlineThread)
    app = _make_sync_app()

    def _on_tag_sync_done(reason: str, err: str | None) -> None:
        app.__dict__["_done_call"] = (reason, err)

    app._on_tag_sync_done = _on_tag_sync_done
    ui_sync.request_tag_sync(app, base_dir=tmp_path, reason="manual")
    assert app.tag_sync_running is True
    assert app.__dict__["_done_call"] == ("manual", None)


def test_on_tag_sync_done_logs_error_and_processes_pending() -> None:
    app = _make_sync_app(
        tag_sync_running=True,
        tag_sync_pending=True,
        tag_sync_pending_reason="manual",
    )
    ui_sync.on_tag_sync_done(app, reason="manual", err="boom")
    assert app.tag_sync_running is False
    assert app.__dict__.get("_logged_errors")
    assert app.request_calls == ["manual"]


def test_on_tag_sync_done_clears_state_when_no_pending() -> None:
    app = _make_sync_app(tag_sync_running=True)
    ui_sync.on_tag_sync_done(app, reason="manual", err=None)
    assert app.tag_sync_running is False
    assert app.request_calls == []


def test_maybe_refresh_cache_noop_when_worker_running() -> None:
    app = _make_sync_app(cache_worker_running=True)
    ui_sync.maybe_refresh_cache(app)
    assert app.cache_refresh_calls == []


def test_maybe_refresh_cache_initialises_signature_on_first_call() -> None:
    app = _make_sync_app()
    ui_sync.maybe_refresh_cache(app)
    assert app.workspace_sig_last == "sig1"
    assert app.cache_refresh_calls == []


def test_maybe_refresh_cache_triggers_refresh_when_signature_changes() -> None:
    app = _make_sync_app(workspace_sig_last="old", workspace_sig_last_ts=0.0)
    ui_sync.maybe_refresh_cache(app)
    assert app.workspace_sig_last == "sig1"
    assert app.cache_refresh_calls == [("hard inconsistency", True)]
    assert app.debug_msgs


def test_workspace_quick_signature_includes_active_and_archive(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "alpha").mkdir()
    (base / "beta").mkdir()
    (base / "_hidden").mkdir()  # excluded — leading underscore
    (base / "_archive" / "2026").mkdir(parents=True)
    (base / "_archive" / "2026-01-01_p.tgz").write_text("")

    out = ui_sync.workspace_quick_signature(
        base_dir=base,
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert out.startswith("active:")
    assert "archive:" in out


def test_workspace_quick_signature_handles_missing_archive(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    out = ui_sync.workspace_quick_signature(
        base_dir=base,
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert "archive:0" in out


def test_workspace_quick_signature_handles_missing_base(tmp_path: Path) -> None:
    out = ui_sync.workspace_quick_signature(
        base_dir=tmp_path / "nope",
        archive_dir_name="_archive",
        packed_archive_suffix=".tgz",
    )
    assert "active:err" in out


def _make_cache_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        cache_refresh_epoch=0,
        cache_worker_running=False,
        cache_refresh_pending=False,
        cache_refresh_pending_force=False,
        cache_refresh_pending_reason="",
        cache_last_refresh_ts=0,
        active_rows=[],
        archived_rows=[],
        logged_errors=[],
    )

    def _log_error_counted(key: str, msg: str) -> None:
        app.logged_errors.append((key, msg))

    app._log_error_counted = _log_error_counted
    app._invalidate_current_rows_cache = lambda: app.__dict__.__setitem__(
        "_invalidated", True
    )
    app._apply_dynamic_properties_all_rows = lambda: app.__dict__.__setitem__(
        "_props_applied", True
    )
    app._log_row_health_issues = lambda rows: app.__dict__.__setitem__(
        "_health_logged", len(rows)
    )
    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_touch_rows_cache_no_rows_no_removed(tmp_path: Path) -> None:
    app = _make_cache_app()
    cache_state.touch_rows_cache(app, base_dir=tmp_path, rows=[], removed=[])
    assert app.cache_refresh_epoch == 1
    assert app.cache_refresh_pending is False


def test_touch_rows_cache_marks_pending_when_worker_running(tmp_path: Path) -> None:
    app = _make_cache_app(cache_worker_running=True)
    cache_state.touch_rows_cache(app, base_dir=tmp_path, rows=[], removed=[])
    assert app.cache_refresh_pending is True
    assert app.cache_refresh_pending_force is True


def test_touch_rows_cache_handles_cache_errors(tmp_path: Path, monkeypatch) -> None:
    app = _make_cache_app()

    def boom(*_a, **_k):
        raise OSError("fail")

    from homebase.ui.sync import cache_state as cs

    monkeypatch.setattr(cs, "cache_upsert_rows", boom)
    cache_state.touch_rows_cache(
        app,
        base_dir=tmp_path,
        rows=[SimpleNamespace(last_cached_ts=0, last_reconciled_ts=0)],
        removed=[],
    )
    assert any(key == "cache_partial_update" for key, _msg in app.logged_errors)


def test_reload_rows_from_cache_returns_false_when_empty(tmp_path: Path) -> None:
    app = _make_cache_app()
    ok = cache_state.reload_rows_from_cache(
        app, base_dir=tmp_path, cache_max_age_s=60
    )
    assert ok is False
