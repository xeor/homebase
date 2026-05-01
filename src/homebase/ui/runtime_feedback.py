from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Callable

import yaml


def log(app: Any, msg: str, level: str = "info") -> None:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    app.messages.append((level, ts, msg))
    app.messages = app.messages[-8:]


def log_error_counted(app: Any, key: str, msg: str, level: str = "warn") -> None:
    k = str(key).strip() or "error"
    n = int(app.error_counts.get(k, 0)) + 1
    app.error_counts[k] = n
    app._log(f"{msg} [{k}#{n}]", level)


def show_runtime_error(
    app: Any,
    context: str,
    exc: BaseException,
    *,
    traceback_tail: str = "",
    runtime_error_screen: Any,
) -> None:
    operation = str(context).strip() or "runtime operation"
    exc_name = type(exc).__name__
    exc_msg = str(exc).strip() or "(no message)"
    details_lines = [
        f"Exception type: {exc_name}",
        f"Message: {exc_msg}",
    ]
    tail = traceback_tail.strip()
    if tail:
        details_lines.append("")
        details_lines.append("Traceback tail:")
        details_lines.append(tail)
    details = "\n".join(details_lines)
    app._log(f"{operation}: {exc_name}: {exc_msg}", "error")
    app._set_runtime_status(f"{operation}: {exc_name}", "error", ttl_s=18.0)
    if app._modal_active():
        return
    try:
        app.push_screen(runtime_error_screen("Runtime error", operation, details))
    except (
        LookupError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        return


def log_row_health_issues(
    app: Any,
    rows: list[Any],
    *,
    base_meta_health: Callable[[Any], tuple[str, str]],
) -> None:
    for row in rows:
        level, detail = base_meta_health(row.path)
        if level == "ok":
            app._health_issue_seen.pop(row.path, None)
            continue
        sig = f"{level}:{detail}"
        if app._health_issue_seen.get(row.path) == sig:
            continue
        app._health_issue_seen[row.path] = sig
        app._log(
            f"meta {level}: {row.name}: {detail}",
            "error" if level == "error" else "warn",
        )


def mark_state_dirty(app: Any) -> None:
    app._state_dirty = True
    app._state_due_at = time.time() + 0.35


def flush_state_if_due(
    app: Any,
    *,
    force: bool = False,
    base_dir: Any,
    save_ui_state: Callable[[Any, dict[str, object]], None],
) -> None:
    if app._capture_table_position():
        app._state_dirty = True
        app._state_due_at = time.time() + 0.35
    if not app._state_dirty:
        return
    if not force and time.time() < app._state_due_at:
        return
    snap = app._state_snapshot()
    snap_json = json.dumps(snap, sort_keys=True)
    if snap_json == app._state_last_json:
        app._state_dirty = False
        return
    try:
        save_ui_state(base_dir, snap)
        app._state_last_json = snap_json
    except (
        OSError,
        yaml.YAMLError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        app._log(f"state save failed: {exc}", "warn")
    app._state_dirty = False


def persist_state_now(app: Any) -> None:
    app._capture_table_position()
    app._state_dirty = True
    app._flush_state_if_due(force=True)


def busy_start(app: Any, label: str) -> None:
    app._busy_depth += 1
    app._busy_label = label
    if app._busy_depth == 1:
        app._busy_frame_index = 0
    try:
        app._refresh_search_display()
    except (
        LookupError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        pass


def busy_stop(app: Any) -> None:
    if app._busy_depth > 0:
        app._busy_depth -= 1
    if app._busy_depth <= 0:
        app._busy_depth = 0
        app._busy_label = "idle"
    try:
        app._refresh_search_display()
    except (
        LookupError,
        KeyError,
        IndexError,
        AttributeError,
        RuntimeError,
        ValueError,
        TypeError,
    ):
        pass


def busy_tick(app: Any) -> None:
    status_expired = (
        bool(app.runtime_status_text)
        and app.runtime_status_until_ts > 0
        and time.time() >= app.runtime_status_until_ts
    )
    if status_expired:
        app.runtime_status_text = ""
        app.runtime_status_level = "info"
        app.runtime_status_until_ts = 0.0

    if app._busy_depth <= 0:
        if status_expired:
            app._refresh_search_display()
        return
    app._busy_frame_index = (app._busy_frame_index + 1) % len(app._busy_frames)
    app._refresh_search_display()


def set_runtime_status(app: Any, text: str, *, level: str = "info", ttl_s: float = 12.0) -> None:
    msg = str(text).strip()
    if not msg:
        app.runtime_status_text = ""
        app.runtime_status_level = "info"
        app.runtime_status_until_ts = 0.0
        app._refresh_search_display()
        return
    app.runtime_status_text = msg
    app.runtime_status_level = level if level in {"info", "warn", "error"} else "info"
    app.runtime_status_until_ts = max(0.0, time.time() + max(1.0, float(ttl_s)))
    app._refresh_search_display()


def critical_job_active(app: Any) -> bool:
    return bool(app.action_worker_running or app.pending_restore_queue)


def critical_job_label(app: Any) -> str:
    if app.action_worker_running:
        return f"archive {app.action_worker_action}"
    if app.pending_restore_queue:
        return "restore batch"
    return ""


def worker_debug(app: Any, message: str) -> None:
    text = str(message).strip()
    if not text:
        return
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    app.worker_debug_events.append((ts, text))
    app.worker_debug_events = app.worker_debug_events[-30:]
    if app.side_main_tab == "info" and app.side_info_tab == "cache":
        app._refresh_side()


def set_reconcile_skip_reason(app: Any, reason: str) -> None:
    text = str(reason).strip()
    now = time.time()
    if text == app.reconcile_last_skip_reason and (now - float(app.reconcile_last_skip_ts)) < 1.0:
        return
    app.reconcile_last_skip_reason = text
    app.reconcile_last_skip_ts = now
