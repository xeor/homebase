from __future__ import annotations

import sqlite3
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from ...cache.api import cache_store_rows
from ...core.models import CacheRefreshOutcome, OperationResult, ProjectRow
from ...workspace.rows import collect_workspace_rows


def start_cache_refresh(
    app: Any,
    *,
    base_dir: Path,
    cache_max_age_s: int,
    reason: str,
    force: bool,
) -> None:
    if app.fast_exit_requested:
        return
    if app.cache_worker_running:
        app.cache_refresh_pending = True
        app.cache_refresh_pending_force = app.cache_refresh_pending_force or force
        app.cache_refresh_pending_reason = reason
        return
    if not force and int(time.time()) - app.cache_last_refresh_ts <= cache_max_age_s:
        return
    app.cache_worker_running = True
    app.cache_worker_note = reason
    app.cache_worker_started_ts = time.time()
    app._busy_start(f"cache refresh ({reason})")
    app.cache_refresh_epoch += 1
    epoch = app.cache_refresh_epoch
    size_cache_seed: dict[Path, tuple[int, int]] = {}
    for row in app.active_rows + app.archived_rows:
        try:
            key = row.path.resolve()
        except (OSError, RuntimeError, ValueError):
            key = row.path
        size_cache_seed[key] = (int(row.size_bytes), int(row.size_refresh_count))
    app._worker_debug(
        f"cache refresh start: reason={reason} force={'yes' if force else 'no'} epoch={epoch}"
    )

    def worker() -> None:
        result = OperationResult.success()
        fresh_active: list[ProjectRow] | None = None
        fresh_archived: list[ProjectRow] | None = None
        try:
            try:
                fresh_active, fresh_archived = collect_workspace_rows(
                    base_dir,
                    include_git_dirty=False,
                    size_cache=size_cache_seed,
                )
            except (
                OSError,
                ValueError,
                TypeError,
                sqlite3.Error,
                yaml.YAMLError,
                subprocess.SubprocessError,
            ) as exc:
                result = OperationResult.failure(f"{exc.__class__.__name__}: {exc}")
        except BaseException as exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            tail = " | ".join(tb.splitlines()[-4:]).strip()
            detail = f"{exc.__class__.__name__}: {exc}"
            if tail:
                detail = f"{detail} [{tail}]"
            result = OperationResult.failure(detail)
        outcome = CacheRefreshOutcome(
            epoch,
            fresh_active,
            fresh_archived,
            result,
        )
        app.call_from_thread(app._on_cache_refresh_done, outcome)

    threading.Thread(target=worker, daemon=True).start()


def on_cache_refresh_done(app: Any, *, base_dir: Path, outcome: CacheRefreshOutcome) -> None:
    if app.fast_exit_requested:
        return
    app.cache_worker_running = False
    app.cache_worker_note = ""
    app.cache_worker_last_done_ts = time.time()
    app.cache_worker_started_ts = 0.0
    app._busy_stop()
    if not outcome.result.ok and outcome.result.error:
        app._worker_debug(
            f"cache refresh failed: epoch={outcome.epoch} error={outcome.result.error}"
        )
        app._log_error_counted(
            "cache_refresh",
            f"cache refresh failed: {outcome.result.error}",
        )
        app._refresh_side()
    elif (
        outcome.epoch == app.cache_refresh_epoch
        and outcome.fresh_active is not None
        and outcome.fresh_archived is not None
    ):
        try:
            app.cache_last_refresh_ts = cache_store_rows(
                base_dir,
                outcome.fresh_active,
                outcome.fresh_archived,
            )
        except (OSError, sqlite3.Error) as exc:
            app._log_error_counted(
                "cache_store",
                f"cache store failed ({exc.__class__.__name__}): {exc}",
            )
        if app._reload_rows_from_cache():
            app._worker_debug(
                f"cache refresh done: epoch={outcome.epoch} active={len(app.active_rows)} archive={len(app.archived_rows)}"
            )
            app._refresh_table()
            app._restore_table_position()
            app._refresh_side()

    if app.cache_refresh_pending:
        reason = app.cache_refresh_pending_reason or "pending"
        force = app.cache_refresh_pending_force
        app.cache_refresh_pending = False
        app.cache_refresh_pending_force = False
        app.cache_refresh_pending_reason = ""
        app._worker_debug(
            f"cache refresh pending-run: reason={reason} force={'yes' if force else 'no'}"
        )
        if not app.fast_exit_requested:
            app.call_after_refresh(lambda: app._start_cache_refresh(reason, force=force))
