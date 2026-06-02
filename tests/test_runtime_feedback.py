from __future__ import annotations

import time
from types import SimpleNamespace

from homebase.ui import runtime_feedback


def _make_app(**overrides: object) -> SimpleNamespace:
    app = SimpleNamespace(
        messages=[],
        error_counts={},
        log_calls=[],
        flush_calls=[],
        status_calls=[],
        runtime_status_text="",
        runtime_status_level="info",
        runtime_status_until_ts=0.0,
        _state_dirty=False,
        _state_due_at=0.0,
        _state_last_json="",
        _busy_depth=0,
        _busy_label="idle",
        _busy_frame_index=0,
        _busy_frames=["a", "b", "c"],
        _health_issue_seen={},
        action_worker_running=False,
        action_worker_action="",
        pending_restore_queue=[],
        worker_debug_events=[],
        side_main_tab="info",
        side_info_tab="cache",
        reconcile_last_skip_reason="",
        reconcile_last_skip_ts=0.0,
        push_screen_calls=[],
    )
    app._refresh_search_display = lambda: app.__dict__.__setitem__(
        "_refresh_count", app.__dict__.get("_refresh_count", 0) + 1
    )
    app._refresh_side = lambda: app.__dict__.__setitem__(
        "_refresh_side_count", app.__dict__.get("_refresh_side_count", 0) + 1
    )
    app._capture_table_position = lambda: False
    app._state_snapshot = lambda: {"view": "active", "sort": "last"}
    app._log = lambda msg, level="info": app.log_calls.append((level, msg))
    app._modal_active = lambda: False
    app._flush_state_if_due = lambda *, force=False: app.flush_calls.append(force)
    app._set_runtime_status = lambda text, level="info", ttl_s=0.0: app.status_calls.append(
        (text, level, ttl_s)
    )
    app.push_screen = lambda screen: app.push_screen_calls.append(screen)
    for k, v in overrides.items():
        setattr(app, k, v)
    return app


def test_log_appends_and_caps_at_8() -> None:
    app = _make_app()
    for i in range(12):
        runtime_feedback.log(app, f"m{i}")
    assert len(app.messages) == 8
    assert app.messages[-1][2] == "m11"


def test_log_error_counted_increments() -> None:
    app = _make_app()
    runtime_feedback.log_error_counted(app, "save", "save failed")
    runtime_feedback.log_error_counted(app, "save", "save failed")
    assert app.error_counts["save"] == 2
    assert "save#2" in app.log_calls[-1][1]


def test_log_error_counted_uses_default_key_for_blank() -> None:
    app = _make_app()
    runtime_feedback.log_error_counted(app, "  ", "boom")
    assert app.error_counts["error"] == 1


def test_show_runtime_error_pushes_screen_when_no_modal() -> None:
    app = _make_app()
    seen: list[tuple[str, str, str]] = []

    def _screen_factory(title: str, op: str, details: str) -> str:
        seen.append((title, op, details))
        return f"screen:{title}"

    runtime_feedback.show_runtime_error(
        app,
        "loading config",
        ValueError("boom"),
        traceback_tail="line 1\nline 2",
        runtime_error_screen=_screen_factory,
    )
    assert seen and seen[0][0] == "Runtime error"
    assert "boom" in seen[0][2]
    assert "Traceback" in seen[0][2]
    assert "screen:Runtime error" in app.push_screen_calls


def test_show_runtime_error_skips_when_modal_active() -> None:
    app = _make_app()
    app._modal_active = lambda: True

    runtime_feedback.show_runtime_error(
        app,
        "loading",
        RuntimeError("nope"),
        traceback_tail="",
        runtime_error_screen=lambda *_a: "ignored",
    )
    assert app.push_screen_calls == []


def test_show_runtime_error_swallows_push_screen_exceptions() -> None:
    app = _make_app()
    app.push_screen = lambda _s: (_ for _ in ()).throw(RuntimeError("fail"))
    runtime_feedback.show_runtime_error(
        app,
        "save",
        OSError("disk"),
        traceback_tail="",
        runtime_error_screen=lambda *_a: "x",
    )


def test_log_row_health_issues_logs_once_per_signature() -> None:
    app = _make_app()
    row = SimpleNamespace(path="/a", name="A")

    levels = iter([("warning", "broken"), ("warning", "broken")])
    def _health(_path):
        return next(levels)

    runtime_feedback.log_row_health_issues(app, [row], base_meta_health=_health)
    runtime_feedback.log_row_health_issues(app, [row], base_meta_health=_health)
    # Same signature → still only one log call from the first invocation
    warns = [m for m in app.log_calls if "broken" in m[1]]
    assert len(warns) == 1


def test_log_row_health_issues_clears_seen_when_ok() -> None:
    app = _make_app()
    row = SimpleNamespace(path="/a", name="A")
    app._health_issue_seen["/a"] = "warning:broken"
    runtime_feedback.log_row_health_issues(
        app,
        [row],
        base_meta_health=lambda _p: ("ok", ""),
    )
    assert "/a" not in app._health_issue_seen


def test_mark_state_dirty_sets_flag_and_due_at() -> None:
    app = _make_app()
    before = time.time()
    runtime_feedback.mark_state_dirty(app)
    assert app._state_dirty is True
    assert app._state_due_at >= before


def test_flush_state_if_due_persists_when_forced() -> None:
    app = _make_app()
    app._state_dirty = True
    saved: list[tuple[str, dict[str, object]]] = []
    runtime_feedback.flush_state_if_due(
        app,
        force=True,
        base_dir="/base",
        save_ui_state=lambda bd, snap: saved.append((bd, snap)),
    )
    assert saved
    assert app._state_dirty is False
    assert app._state_last_json


def test_flush_state_if_due_skips_when_not_dirty() -> None:
    app = _make_app()
    saved: list[object] = []
    runtime_feedback.flush_state_if_due(
        app,
        force=False,
        base_dir="/base",
        save_ui_state=lambda *_a: saved.append(_a),
    )
    assert saved == []


def test_flush_state_if_due_skips_when_snapshot_unchanged() -> None:
    app = _make_app()
    app._state_dirty = True
    saved: list[object] = []
    # pre-load last_json with the matching snapshot
    import json

    app._state_last_json = json.dumps(app._state_snapshot(), sort_keys=True)
    runtime_feedback.flush_state_if_due(
        app,
        force=True,
        base_dir="/base",
        save_ui_state=lambda *_a: saved.append(_a),
    )
    assert saved == []
    assert app._state_dirty is False


def test_flush_state_logs_warning_on_save_failure() -> None:
    app = _make_app()
    app._state_dirty = True

    def boom(*_a):
        raise OSError("disk full")

    runtime_feedback.flush_state_if_due(
        app,
        force=True,
        base_dir="/base",
        save_ui_state=boom,
    )
    assert any("state save failed" in msg for level, msg in app.log_calls)


def test_persist_state_now_triggers_flush() -> None:
    app = _make_app()
    runtime_feedback.persist_state_now(app)
    assert app.flush_calls == [True]
    assert app._state_dirty is True


def test_busy_start_increments_depth_and_resets_frame() -> None:
    app = _make_app()
    runtime_feedback.busy_start(app, "doing something")
    assert app._busy_depth == 1
    assert app._busy_label == "doing something"
    assert app._busy_frame_index == 0

    runtime_feedback.busy_start(app, "second")
    assert app._busy_depth == 2


def test_busy_start_swallows_refresh_exception() -> None:
    app = _make_app()
    app._refresh_search_display = lambda: (_ for _ in ()).throw(RuntimeError("x"))
    runtime_feedback.busy_start(app, "x")


def test_busy_stop_decrements_and_resets_label() -> None:
    app = _make_app()
    app._busy_depth = 2
    runtime_feedback.busy_stop(app)
    assert app._busy_depth == 1
    runtime_feedback.busy_stop(app)
    assert app._busy_depth == 0
    assert app._busy_label == "idle"


def test_busy_tick_clears_expired_runtime_status() -> None:
    app = _make_app()
    app.runtime_status_text = "stale"
    app.runtime_status_until_ts = time.time() - 5.0
    runtime_feedback.busy_tick(app)
    assert app.runtime_status_text == ""
    assert app.runtime_status_level == "info"


def test_busy_tick_advances_frame_when_busy() -> None:
    app = _make_app()
    app._busy_depth = 1
    runtime_feedback.busy_tick(app)
    assert app._busy_frame_index == 1


def test_set_runtime_status_clears_when_blank() -> None:
    app = _make_app()
    app.runtime_status_text = "before"
    runtime_feedback.set_runtime_status(app, "  ")
    assert app.runtime_status_text == ""


def test_set_runtime_status_sets_text_and_ttl() -> None:
    app = _make_app()
    before = time.time()
    runtime_feedback.set_runtime_status(app, "hello", level="warn", ttl_s=5)
    assert app.runtime_status_text == "hello"
    assert app.runtime_status_level == "warn"
    assert app.runtime_status_until_ts >= before


def test_set_runtime_status_falls_back_to_info_for_unknown_level() -> None:
    app = _make_app()
    runtime_feedback.set_runtime_status(app, "hello", level="bogus")
    assert app.runtime_status_level == "info"


def test_critical_job_flags() -> None:
    app = _make_app(action_worker_running=False, pending_restore_queue=[])
    assert runtime_feedback.critical_job_active(app) is False
    assert runtime_feedback.critical_job_label(app) == ""

    app = _make_app(action_worker_running=True, action_worker_action="pack", pending_restore_queue=[])
    assert runtime_feedback.critical_job_active(app) is True
    assert runtime_feedback.critical_job_label(app) == "archive pack"

    app = _make_app(action_worker_running=False, pending_restore_queue=["item"])
    assert runtime_feedback.critical_job_active(app) is True
    assert runtime_feedback.critical_job_label(app) == "restore batch"


def test_worker_debug_records_event_and_refreshes_side() -> None:
    app = _make_app()
    runtime_feedback.worker_debug(app, "tick")
    assert app.worker_debug_events
    assert app.worker_debug_events[-1][1] == "tick"


def test_worker_debug_ignores_blank() -> None:
    app = _make_app()
    runtime_feedback.worker_debug(app, "   ")
    assert app.worker_debug_events == []


def test_set_reconcile_skip_reason_deduplicates_within_window() -> None:
    app = _make_app()
    runtime_feedback.set_reconcile_skip_reason(app, "busy")
    ts_1 = app.reconcile_last_skip_ts
    runtime_feedback.set_reconcile_skip_reason(app, "busy")
    assert app.reconcile_last_skip_ts == ts_1


def test_set_reconcile_skip_reason_updates_when_different() -> None:
    app = _make_app()
    runtime_feedback.set_reconcile_skip_reason(app, "first")
    runtime_feedback.set_reconcile_skip_reason(app, "second")
    assert app.reconcile_last_skip_reason == "second"
