from __future__ import annotations

import concurrent.futures
import sqlite3
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow
from ...workspace.projects import project_row
from ...workspace.rows import reconcile_queue_pop_next, reconcile_queue_push


def queue_reconcile_request(
    app: Any,
    *,
    mode: str,
    reason: str,
    paths: list[Path],
    priority: int,
) -> None:
    app.reconcile_queue = reconcile_queue_push(
        app.reconcile_queue,
        mode,
        reason,
        paths,
        priority,
        limit=40,
    )
    app._worker_debug(
        f"reconcile queued: mode={mode} reason={reason} paths={len(paths)} prio={priority} q={len(app.reconcile_queue)}"
    )


def run_next_reconcile_from_queue(app: Any) -> None:
    app.reconcile_queue, next_item = reconcile_queue_pop_next(
        app.reconcile_queue,
        app.reconcile_worker_running,
    )
    if next_item is None:
        return
    _prio, mode, reason, paths = next_item
    app._worker_debug(
        f"reconcile dequeue: mode={mode} reason={reason} paths={len(paths)} q={len(app.reconcile_queue)}"
    )
    app._start_reconcile_rows(mode, reason, paths)


def start_reconcile_rows(app: Any, mode: str, reason: str, paths: list[Path]) -> None:
    if app.fast_exit_requested:
        return
    if app.reconcile_worker_running:
        prio = 2 if reason.startswith("manual") else 1
        app._queue_reconcile_request(mode, reason, paths, prio)
        return
    if not paths:
        return

    specs: list[tuple[Path, bool, Path | None, int, int, int]] = []
    for path in paths:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        row = rows[idx]
        specs.append(
            (
                row.path,
                row.archived,
                row.restore_target,
                row.archived_ts,
                int(row.size_bytes),
                int(row.size_refresh_count),
            )
        )
    if not specs:
        return

    app.reconcile_worker_running = True
    app.reconcile_worker_mode = mode
    app.reconcile_worker_reason = reason
    app.reconcile_worker_started_ts = time.time()
    parallelism = app._effective_reconcile_parallelism(mode)
    app._worker_debug(
        f"reconcile start: mode={mode} reason={reason} paths={len(specs)} workers={max(1, int(parallelism))}"
    )

    def worker() -> None:
        refreshed_rows: list[ProjectRow] = []
        removed_paths: list[Path] = []
        failed = 0
        now_ts = int(time.time())

        def reconcile_one(
            spec: tuple[Path, bool, Path | None, int, int, int],
        ) -> tuple[str, ProjectRow | Path | None]:
            path, archived, restore_target, archived_ts, prev_size, prev_size_count = spec
            try:
                if not path.exists():
                    return ("removed", path)
                row = project_row(
                    path,
                    archived=archived,
                    restore_target=restore_target,
                    archived_ts=archived_ts,
                    prev_size_bytes=prev_size,
                    prev_size_refresh_count=prev_size_count,
                )
                row.last_cached_ts = now_ts
                row.last_reconciled_ts = now_ts
                row.stale = False
                row.cache_age_s = 0
                return ("row", row)
            except (OSError, ValueError, TypeError, subprocess.SubprocessError, sqlite3.Error):
                return ("failed", None)

        fatal_error = ""
        try:
            max_workers = max(1, int(parallelism))
            if max_workers == 1:
                for spec in specs:
                    kind, payload = reconcile_one(spec)
                    if kind == "row" and isinstance(payload, ProjectRow):
                        refreshed_rows.append(payload)
                    elif kind == "removed" and isinstance(payload, Path):
                        removed_paths.append(payload)
                    elif kind == "failed":
                        failed += 1
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                    for kind, payload in pool.map(reconcile_one, specs):
                        if kind == "row" and isinstance(payload, ProjectRow):
                            refreshed_rows.append(payload)
                        elif kind == "removed" and isinstance(payload, Path):
                            removed_paths.append(payload)
                        elif kind == "failed":
                            failed += 1
        except BaseException as exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            tail = " | ".join(tb.splitlines()[-4:]).strip()
            fatal_error = f"{exc.__class__.__name__}: {exc}"
            if tail:
                fatal_error = f"{fatal_error} [{tail}]"
            failed = max(failed, len(specs))

        app.call_from_thread(
            app._on_reconcile_rows_done,
            mode,
            reason,
            refreshed_rows,
            removed_paths,
            failed,
            fatal_error,
        )

    threading.Thread(target=worker, daemon=True).start()


def record_reconcile_recent(app: Any, kind: str, label: str) -> None:
    if kind not in {"active", "archive"}:
        return
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = app.reconcile_recent.get(kind, [])
    rows.append((ts, label))
    app.reconcile_recent[kind] = rows[-5:]


def on_reconcile_rows_done(
    app: Any,
    *,
    mode: str,
    reason: str,
    refreshed_rows: list[ProjectRow],
    removed_paths: list[Path],
    failed: int,
    fatal_error: str,
    base_dir: Path,
    archive_dir_name: str,
    mode_active: str,
    mode_archive: str,
    level_warn: str,
    is_under: Callable[[Path, Path], bool],
) -> None:
    app.reconcile_worker_running = False
    app.reconcile_worker_mode = ""
    app.reconcile_worker_reason = ""
    app.reconcile_worker_last_done_ts = time.time()
    app.reconcile_worker_started_ts = 0.0
    if refreshed_rows:
        for row in refreshed_rows:
            app._upsert_row_local(row)
            kind = mode_archive if row.archived else mode_active
            app._record_reconcile_recent(kind, f"{row.name} ({reason})")
        app._touch_rows_cache(refreshed_rows)
    if removed_paths:
        app._remove_paths_local(removed_paths)
        app._touch_rows_cache([], removed=removed_paths)
        for path in removed_paths:
            kind = mode_archive if is_under(path, base_dir / archive_dir_name) else mode_active
            app._record_reconcile_recent(kind, f"{path.name} [removed] ({reason})")
    if refreshed_rows or removed_paths:
        app._refresh_table()
        app._refresh_side()
    if failed > 0:
        if fatal_error:
            app._log(f"reconcile {mode}: fatal worker failure: {fatal_error}", "error")
        app._log(f"reconcile {mode}: failed={failed}", level_warn)
        app._refresh_side()
        app.reconcile_inconsistency_streak += 1
    else:
        app.reconcile_inconsistency_streak = 0

    app._worker_debug(
        f"reconcile done: mode={mode} reason={reason} refreshed={len(refreshed_rows)} removed={len(removed_paths)} failed={failed} q={len(app.reconcile_queue)}"
    )

    if app.reconcile_inconsistency_streak >= 3:
        app.reconcile_inconsistency_streak = 0
        app._worker_debug(
            "reconcile inconsistency streak reached threshold -> cache refresh"
        )
        app._start_cache_refresh("hard inconsistency", force=True)
        app._log("hard inconsistency detected, running full reconcile", level_warn)
        app._refresh_side()
    if mode in {mode_active, mode_archive}:
        interval_s = app._effective_reconcile_wait_s(mode)
        app.reconcile_next_due[mode] = time.time() + interval_s
    app._run_next_reconcile_from_queue()
