from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from ...core.models import ArchiveActionOutcome, ProjectRow


def start_archive_action_worker(
    app: Any,
    action: str,
    paths: list[Path],
    *,
    archive_pack_internal: Callable[[Path, Path], Path],
    archive_unpack_internal: Callable[[Path, Path], Path],
    is_packed_archive_path: Callable[[Path], bool],
) -> None:
    if app.action_worker_running:
        app._log("archive action worker is already running", "warn")
        app._refresh_side()
        return
    app.action_worker_running = True
    app.action_worker_action = action
    app.action_worker_total = len(paths)
    app.action_worker_done = 0
    app.action_worker_current = ""
    app.action_worker_stage = "queued"
    app.action_worker_command = ""
    app.action_worker_started_ts = int(time.time())
    app._busy_start(f"running {action} on selection")
    app._worker_debug(f"archive worker start: action={action} items={len(paths)}")
    app._refresh_side()

    def worker() -> None:
        success = 0
        failed = 0
        removed_paths: list[Path] = []
        upsert_rows: list[ProjectRow] = []
        logs: list[tuple[str, str]] = []
        total = len(paths)
        for i, path in enumerate(paths, start=1):
            app.call_from_thread(
                app._on_archive_action_worker_progress,
                i - 1,
                path.name,
                "preparing",
                "",
            )
            try:
                if action == "pack":
                    cmd = f"tar -czf <tmp> -C {path.parent} {path.name}"
                    app.call_from_thread(
                        app._on_archive_action_worker_progress,
                        i - 1,
                        path.name,
                        "packing",
                        cmd,
                    )
                    packed_path = archive_pack_internal(app.base_dir, path)
                    logs.append(("info", f"packed: {path.name} -> {packed_path.name}"))
                    removed_paths.append(path)
                    upsert_rows.append(app._build_archived_row_from_entry(packed_path))
                elif action == "unpack":
                    cmd = f"tar -xzf {path.name} -C <tmp>"
                    app.call_from_thread(
                        app._on_archive_action_worker_progress,
                        i - 1,
                        path.name,
                        "unpacking",
                        cmd,
                    )
                    unpacked_path = archive_unpack_internal(app.base_dir, path)
                    logs.append(("info", f"unpacked: {path.name} -> {unpacked_path.name}"))
                    removed_paths.append(path)
                    upsert_rows.append(app._build_archived_row_from_entry(unpacked_path))
                elif action == "toggle_pack":
                    if is_packed_archive_path(path):
                        stage, verb = "unpacking", "unpacked"
                        cmd = f"tar -xzf {path.name} -C <tmp>"
                        op = archive_unpack_internal
                    else:
                        stage, verb = "packing", "packed"
                        cmd = f"tar -czf <tmp> -C {path.parent} {path.name}"
                        op = archive_pack_internal
                    app.call_from_thread(
                        app._on_archive_action_worker_progress,
                        i - 1,
                        path.name,
                        stage,
                        cmd,
                    )
                    new_path = op(app.base_dir, path)
                    logs.append(("info", f"{verb}: {path.name} -> {new_path.name}"))
                    removed_paths.append(path)
                    upsert_rows.append(app._build_archived_row_from_entry(new_path))
                else:
                    logs.append(("error", f"unknown archive action: {action}"))
                    failed += 1
                    continue
                success += 1
            except (
                OSError,
                ValueError,
                TypeError,
                sqlite3.Error,
                subprocess.SubprocessError,
                yaml.YAMLError,
                json.JSONDecodeError,
            ) as exc:
                failed += 1
                logs.append(("error", f"{action} failed for {path.name}: {exc}"))

        app.call_from_thread(
            app._on_archive_action_worker_done,
            ArchiveActionOutcome(
                action=action,
                total=total,
                success=success,
                failed=failed,
                removed_paths=removed_paths,
                upsert_rows=upsert_rows,
                logs=logs,
            ),
        )

    threading.Thread(target=worker, daemon=True).start()


def on_archive_action_worker_progress(
    app: Any, done: int, current: str, stage: str, command: str
) -> None:
    app.action_worker_done = done
    app.action_worker_current = current
    app.action_worker_stage = stage
    app.action_worker_command = command
    app._refresh_side()


def on_archive_action_worker_done(app: Any, outcome: ArchiveActionOutcome) -> None:
    app.action_worker_done = outcome.total
    app.action_worker_current = ""
    app.action_worker_running = False
    app.action_worker_action = ""
    app.action_worker_total = 0
    app.action_worker_started_ts = 0
    app.action_worker_stage = ""
    app.action_worker_command = ""
    app._busy_stop()

    for level, msg in outcome.logs:
        app._log(msg, level)

    if outcome.removed_paths:
        app._remove_paths_local(outcome.removed_paths)
    for row in outcome.upsert_rows:
        app._upsert_row_local(row)
    if outcome.removed_paths or outcome.upsert_rows:
        app._touch_rows_cache(outcome.upsert_rows, removed=outcome.removed_paths)
        app._start_cache_refresh(f"{outcome.action} update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(
        f"{outcome.action} finished: ok={outcome.success}, failed={outcome.failed}",
        "info",
    )
    app._worker_debug(
        f"archive worker done: action={outcome.action} ok={outcome.success} failed={outcome.failed}"
    )
    app._refresh_side()
