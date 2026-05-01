from __future__ import annotations

import shutil
import sqlite3
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from textual.widgets import Static

from ...cache.api import cache_db_path
from ...core.models import ProjectRow
from ...core.utils import fmt_age_short, fmt_age_short_from_iso, fmt_iso
from ...workspace.projects import project_row


def cache_info_lines(
    app: Any,
    *,
    base_dir: Path,
    cache_schema_version: int,
    cache_max_age_s: int,
    cache_bg_refresh_s: int,
    mode_active: str,
    mode_archive: str,
    archive_dir_name: str,
) -> list[str]:
    out: list[str] = []
    db = cache_db_path(base_dir)
    exists = db.is_file()
    out.append("[cyan]cache[/]:")
    out.append(f"path: {app._esc(db)}")
    out.append(f"exists: {'yes' if exists else 'no'}")
    if exists:
        try:
            size = db.stat().st_size
            out.append(f"size: {size} bytes")
        except OSError:
            out.append("size: -")
    else:
        out.append("size: -")
    out.append(f"schema version: {cache_schema_version}")
    out.append(
        f"policy: max_age={cache_max_age_s}s background_refresh={cache_bg_refresh_s}s"
    )
    out.append(f"cache epoch: {app.cache_refresh_epoch}")
    out.append(f"cache worker: {'running' if app.cache_worker_running else 'idle'}")
    if app.cache_worker_running and app.cache_worker_started_ts > 0:
        started_ts = int(app.cache_worker_started_ts)
        out.append(f"cache worker running for: {fmt_age_short(started_ts)}")
    elif app.cache_worker_last_done_ts > 0:
        done_ts = int(app.cache_worker_last_done_ts)
        out.append(f"cache worker last done: {fmt_iso(done_ts)} ({fmt_age_short(done_ts)})")
    if app.cache_worker_note:
        out.append(f"worker note: {app._esc(app.cache_worker_note)}")
    if app.cache_last_refresh_ts > 0:
        out.append(
            f"last refresh: {fmt_iso(app.cache_last_refresh_ts)} ({fmt_age_short(app.cache_last_refresh_ts)})"
        )
    else:
        out.append("last refresh: -")
    active_stale = sum(1 for r in app.active_rows if r.stale)
    archived_stale = sum(1 for r in app.archived_rows if r.stale)
    out.append(f"rows: active={len(app.active_rows)} archived={len(app.archived_rows)}")
    out.append(f"stale rows: active={active_stale} archived={archived_stale}")
    for mode in (mode_active, mode_archive):
        wait_s = app._effective_reconcile_wait_s(mode)
        parallel = app._effective_reconcile_parallelism(mode)
        due_at = float(app.reconcile_next_due.get(mode, 0.0))
        wait_left = max(0.0, due_at - time.time()) if due_at > 0 else 0.0
        out.append(
            f"reconcile policy ({mode}): wait={wait_s:.2f}s parallel={parallel} next_in={wait_left:.2f}s"
        )
    selected = app._selected_row()
    if selected is not None:
        out.append("[dim]----------------------------------------[/]")
        out.append("[cyan]selected cache state[/]:")
        out.append(f"row: {app._esc(selected.name)}")
        if selected.last_cached_ts > 0:
            out.append(
                f"last cached: {fmt_iso(selected.last_cached_ts)} ({fmt_age_short(selected.last_cached_ts)})"
            )
        else:
            out.append("last cached: -")
        if selected.last_reconciled_ts > 0:
            out.append(
                f"last reconciled: {fmt_iso(selected.last_reconciled_ts)} ({fmt_age_short(selected.last_reconciled_ts)})"
            )
        else:
            out.append("last reconciled: -")
        usage_score = float(app.row_usage_score.get(selected.path, 0.0))
        usage_hits = int(app.row_usage_hits.get(selected.path, 0))
        out.append(f"reconcile score: {usage_score:.2f} hits={usage_hits}")
    out.append("[dim]----------------------------------------[/]")
    out.append("[cyan]workers[/]:")
    out.append(f"cache refresh thread: {'running' if app.cache_worker_running else 'idle'}")
    out.append(f"reconcile worker: {'running' if app.reconcile_worker_running else 'idle'}")
    if app.reconcile_worker_running and app.reconcile_worker_started_ts > 0:
        started_ts = int(app.reconcile_worker_started_ts)
        out.append(f"reconcile worker running for: {fmt_age_short(started_ts)}")
    elif app.reconcile_worker_last_done_ts > 0:
        done_ts = int(app.reconcile_worker_last_done_ts)
        out.append(
            f"reconcile worker last done: {fmt_iso(done_ts)} ({fmt_age_short(done_ts)})"
        )
    out.append(f"git worker: {'running' if app.git_refresh_running else 'idle'}")
    if app.git_refresh_reason:
        out.append(f"git worker reason: {app._esc(app.git_refresh_reason)}")
    if app.reconcile_worker_reason:
        out.append(
            f"reconcile reason: {app._esc(app.reconcile_worker_reason)} ({app._esc(app.reconcile_worker_mode)})"
        )
    if app.reconcile_last_skip_reason:
        skip_ts = int(app.reconcile_last_skip_ts) if app.reconcile_last_skip_ts > 0 else 0
        if skip_ts > 0:
            out.append(
                f"reconcile scheduler: {app._esc(app.reconcile_last_skip_reason)} ({fmt_age_short(skip_ts)})"
            )
        else:
            out.append(f"reconcile scheduler: {app._esc(app.reconcile_last_skip_reason)}")
    out.append("[cyan]recent reconciled[/] [dim](last 5 per type)[/]:")
    for kind in ("active", "archive"):
        items = app.reconcile_recent.get(kind, [])
        out.append(f"{kind}: {len(items)}")
        if not items:
            out.append("  [dim]-[/]")
            continue
        for ts, label in reversed(items):
            out.append(f"  [dim]{app._esc(ts)} ({fmt_age_short_from_iso(ts)})[/] {app._esc(label)}")
    out.append(
        f"cache queue: pending={'yes' if app.cache_refresh_pending else 'no'} force={'yes' if app.cache_refresh_pending_force else 'no'}"
    )
    out.append(f"reconcile queue size: {len(app.reconcile_queue)}")
    if app.cache_refresh_pending_reason:
        out.append(f"cache pending reason: {app._esc(app.cache_refresh_pending_reason)}")
    if app.cache_worker_note:
        out.append(f"cache active reason: {app._esc(app.cache_worker_note)}")
    out.append(f"detail worker: {'running' if app.detail_worker_running else 'idle'}")
    if app.detail_worker_path is not None:
        out.append(f"detail path: {app._esc(app.detail_worker_path)}")
    out.append(f"detail token: {app.detail_worker_token}")
    out.append(f"tag sync worker: {'running' if app.tag_sync_running else 'idle'}")
    out.append(f"tag sync queue: pending={'yes' if app.tag_sync_pending else 'no'}")
    if app.tag_sync_pending_reason:
        out.append(f"tag sync pending reason: {app._esc(app.tag_sync_pending_reason)}")
    out.append(f"archive action worker: {'running' if app.action_worker_running else 'idle'}")
    out.append(
        f"archive backend: tar={'yes' if shutil.which('tar') is not None else 'python fallback'}"
    )
    if app.action_worker_running:
        out.append(f"archive action: {app._esc(app.action_worker_action)}")
        out.append(f"archive progress: {app.action_worker_done}/{app.action_worker_total}")
        if app.action_worker_current:
            out.append(f"archive current item: {app._esc(app.action_worker_current)}")
        if app.action_worker_stage:
            out.append(f"archive stage: {app._esc(app.action_worker_stage)}")
        if app.action_worker_command:
            out.append(f"archive command: [dim]{app._esc(app.action_worker_command)}[/]")
        if app.action_worker_started_ts > 0:
            out.append(
                "archive started: "
                f"{fmt_iso(app.action_worker_started_ts)} "
                f"({fmt_age_short(app.action_worker_started_ts)})"
            )
    out.append(f"pane probe: {'running' if app.pane_probe_running else 'idle'}")
    out.append(f"busy overlay: depth={app._busy_depth} label={app._esc(app._busy_label)}")
    out.append(
        f"restore queue: active={len(app.pending_restore_queue)} ok={app.pending_restore_ok} failed={app.pending_restore_failed}"
    )
    out.append(f"pending tag confirmations: {len(app.pending_tag_updates)}")
    out.append("[dim]notes: stale rows auto-refresh; selected git/files refresh on demand[/]")
    if app.worker_debug_events:
        out.append("[cyan]worker debug[/] [dim](last 10)[/]:")
        for ts, msg in app.worker_debug_events[-10:]:
            out.append(
                f"  [dim]{app._esc(ts)} ({fmt_age_short_from_iso(ts)})[/] {app._esc(msg)}"
            )
    return out


def refresh_selected_details(app: Any, *, log_success: bool = False) -> None:
    if app.fast_exit_requested:
        return
    row = app._selected_row()
    if not row:
        return
    if app.detail_worker_running and app.detail_worker_path == row.path:
        return
    app.detail_worker_running = True
    app.detail_worker_path = row.path
    app.side_detail_row = row.path
    app.detail_worker_token += 1
    token = app.detail_worker_token
    app._selected_details_worker(
        token,
        row.path,
        row.archived,
        row.restore_target,
        row.archived_ts,
        int(row.size_bytes),
        int(row.size_refresh_count),
        log_success,
    )


def selected_details_worker(
    app: Any,
    *,
    token: int,
    path: Path,
    archived: bool,
    restore_target: Path | None,
    archived_ts: int,
    prev_size_bytes: int,
    prev_size_refresh_count: int,
    log_success: bool,
) -> None:
    def worker() -> None:
        refreshed: ProjectRow | None = None
        git_text = ""
        files_text = ""
        err_exc: BaseException | None = None
        err_tail = ""
        try:
            refreshed = project_row(
                path,
                archived=archived,
                restore_target=restore_target,
                archived_ts=archived_ts,
                prev_size_bytes=prev_size_bytes,
                prev_size_refresh_count=prev_size_refresh_count,
            )
            git_text = app._build_side_git_text(refreshed)
            files_text = app._build_side_files_text(refreshed)
        except (OSError, ValueError, TypeError, subprocess.SubprocessError, sqlite3.Error) as exc:
            err_exc = exc
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            err_tail = "".join(tb_lines[-6:]).strip()
        app.call_from_thread(
            app._on_selected_details_done,
            token,
            path,
            refreshed,
            git_text,
            files_text,
            err_exc,
            err_tail,
            log_success,
        )

    threading.Thread(target=worker, daemon=True).start()


def on_selected_details_done(
    app: Any,
    *,
    token: int,
    path: Path,
    refreshed: ProjectRow | None,
    git_text: str,
    files_text: str,
    err_exc: BaseException | None,
    err_tail: str,
    log_success: bool,
) -> None:
    if app.fast_exit_requested:
        return
    if token != app.detail_worker_token:
        return
    app.detail_worker_running = False
    app.detail_worker_path = None
    if err_exc is not None:
        err_msg = str(err_exc).strip() or type(err_exc).__name__
        app.side_git_text = f"[red]git details failed:[/] {app._esc(err_msg)}"
        app.side_files_text = f"[red]file details failed:[/] {app._esc(err_msg)}"
        app._show_runtime_error("refresh selected details", err_exc, err_tail)
        app._refresh_side()
        return
    if refreshed is None:
        app._refresh_side()
        return
    app.selected_path = refreshed.path
    app.side_detail_row = refreshed.path
    app.side_git_text = git_text
    app.side_files_text = files_text
    app._upsert_row_local(refreshed)
    app._touch_rows_cache([refreshed])
    app._refresh_table()
    if log_success:
        app._log(f"details refreshed: {refreshed.name}", "info")
    app._refresh_side()


def refresh_wip_bar(app: Any) -> None:
    bar = app.query_one("#wip_bar", Static)
    rows = app._wip_rows_sorted()[:9]
    if rows:
        parts = [f"{idx}:{app._esc(row.name)}" for idx, row in enumerate(rows, start=1)]
        bar.update("[bold yellow]WIP[/] [dim](alt+1..9)[/]  " + "  ".join(parts))
    else:
        bar.update("[bold yellow]WIP[/] [dim](alt+1..9)[/]  -")
