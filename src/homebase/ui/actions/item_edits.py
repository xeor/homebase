from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow
from ...hooks import runtime as hooks_runtime
from ...hooks.snapshot import snapshot_target
from ...metadata.api import load_base_data
from . import note_sync as note_sync_actions


def _notify_warning(app: Any, message: str) -> None:
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        notifier(message, severity="warning")


def _rename_abort(app: Any, reason: str, *, level: str = "error") -> None:
    app._log(f"rename aborted: {reason}", level)
    _notify_warning(app, f"Rename aborted: {reason}")
    app._refresh_side()


def _is_dir_writable(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.W_OK | os.X_OK)
    except OSError:
        return False


def _build_note_rename_command(
    app: Any,
    *,
    source_row: ProjectRow,
    updated_row: ProjectRow,
    old_note_path: Path,
    new_note_path: Path,
    command_template: str,
) -> str:
    return note_sync_actions.build_note_sync_command(
        app,
        source_row=source_row,
        target_row=updated_row,
        old_note_path=old_note_path,
        new_note_path=new_note_path,
        command_template=command_template,
    )


def _rename_precheck(
    app: Any,
    *,
    source_row: ProjectRow,
    current: Path,
    target: Path,
) -> tuple[bool, str, Path | None, Path | None, str]:
    if not current.exists():
        return False, "source path does not exist", None, None, ""
    if target.exists():
        return False, f"target project exists ({target.name})", None, None, ""
    if not _is_dir_writable(current.parent):
        return False, f"no write permission in {current.parent}", None, None, ""

    enabled, command_template = note_sync_actions.note_sync_config(app, "rename")
    if not enabled:
        return True, "", None, None, ""

    resolve_notes = getattr(app, "_resolve_notes_path_for_row", None)
    if not callable(resolve_notes):
        return True, "", None, None, ""

    try:
        old_note_path = resolve_notes(source_row)
    except (OSError, ValueError, RuntimeError):
        return True, "", None, None, ""
    try:
        has_old_note = old_note_path.exists() and old_note_path.is_file()
    except OSError as exc:
        return False, f"note precheck failed ({exc})", None, None, ""
    if not has_old_note:
        return True, "", None, None, ""

    updated_row = ProjectRow(
        path=target,
        name=target.name,
        branch=source_row.branch,
        dirty=source_row.dirty,
        last=source_row.last,
        src=source_row.src,
        created=source_row.created,
        tags=list(source_row.tags),
        properties=list(source_row.properties),
        description=source_row.description,
        created_ts=source_row.created_ts,
        last_ts=source_row.last_ts,
        git_ts=source_row.git_ts,
        opened_ts=source_row.opened_ts,
        is_fork=source_row.is_fork,
        is_tmp=source_row.is_tmp,
        archived=source_row.archived,
        restore_target=source_row.restore_target,
        archived_ts=source_row.archived_ts,
        wip=source_row.wip,
        suffix=source_row.suffix,
        packed=source_row.packed,
    )
    try:
        new_note_path = resolve_notes(updated_row)
    except (OSError, ValueError, RuntimeError) as exc:
        return False, f"new note path resolution failed ({exc})", None, None, ""
    if new_note_path != old_note_path and new_note_path.exists():
        return False, f"target note exists ({new_note_path})", None, None, ""
    if new_note_path != old_note_path and not _is_dir_writable(new_note_path.parent):
        return False, f"no write permission for note destination ({new_note_path.parent})", None, None, ""

    if command_template:
        try:
            cmd = _build_note_rename_command(
                app,
                source_row=source_row,
                updated_row=updated_row,
                old_note_path=old_note_path,
                new_note_path=new_note_path,
                command_template=command_template,
            )
        except (TypeError, ValueError) as exc:
            return False, f"note rename command render failed ({exc})", None, None, ""
        if not cmd:
            return False, "note rename command rendered empty", None, None, ""
        return True, "", old_note_path, new_note_path, cmd

    return True, "", old_note_path, new_note_path, ""


def on_set_description(
    app: Any,
    value: str | None,
    *,
    save_base_description: Callable[[Path, str], None],
) -> None:
    if value is None:
        app._log("set description cancelled", "warn")
        app._refresh_side()
        return
    targets = list(app.pending_desc_targets)
    app.pending_desc_targets = []
    if not targets:
        targets = [r.path for r in app._target_rows()]
    app._busy_start("updating descriptions")
    try:
        for path in targets:
            app._busy_tick()
            save_base_description(path, value)
    finally:
        app._busy_stop()
    changed_rows: list[ProjectRow] = []
    for path in targets:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        rows[idx].description = value
        rows[idx].stale = False
        rows[idx].cache_age_s = 0
        changed_rows.append(rows[idx])
    if changed_rows:
        app._touch_rows_cache(changed_rows)
        app._start_cache_refresh("description update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(f"description updated on {len(targets)} item(s)", "info")
    app._refresh_side()


def on_rename_item(
    app: Any,
    value: str | None,
    *,
    project_row: Callable[..., ProjectRow],
) -> None:
    current = app.pending_rename_target
    app.pending_rename_target = None
    if current is None:
        return
    if value is None:
        _rename_abort(app, "rename cancelled", level="warn")
        return
    new_name = value.strip()
    if not new_name:
        _rename_abort(app, "empty name")
        return
    if "/" in new_name or "\\" in new_name:
        _rename_abort(app, "name must not contain path separators")
        return

    hit = app._find_row(current)
    if hit is None:
        _rename_abort(app, "source row not found")
        return
    rows, idx = hit
    source_row = rows[idx]

    target = current.parent / new_name
    if target == current:
        _rename_abort(app, "unchanged", level="warn")
        return
    if target.exists():
        _rename_abort(app, f"target project exists ({target.name})")
        return

    ok, reason, old_note_path, new_note_path, rendered_note_cmd = _rename_precheck(
        app,
        source_row=source_row,
        current=current,
        target=target,
    )
    if not ok:
        _rename_abort(app, reason)
        return

    pre_outcome = hooks_runtime.dispatch_pre(
        app,
        event="rename",
        targets=[snapshot_target(source_row, load_base_data(source_row.path))],
        change={
            "old_path": current,
            "new_path": target,
            "old_name": current.name,
            "new_name": target.name,
        },
        view=app.view_mode,
    )
    if pre_outcome.cancelled:
        _rename_abort(app, pre_outcome.reason or "cancelled by hook")
        return
    change = dict(pre_outcome.change)
    mutated_new_path = change.get("new_path")
    if isinstance(mutated_new_path, Path):
        target = mutated_new_path
        new_name = target.name
    elif isinstance(mutated_new_path, str):
        target = Path(mutated_new_path)
        new_name = target.name

    try:
        current.rename(target)
    except (OSError, ValueError) as exc:
        _rename_abort(app, str(exc))
        return

    try:
        updated = project_row(
            target,
            archived=source_row.archived,
            restore_target=source_row.restore_target,
            archived_ts=source_row.archived_ts,
            opened_ts_override=source_row.opened_ts,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        subprocess.SubprocessError,
        sqlite3.Error,
    ) as exc:
        app._log(f"rename warning: row refresh failed ({exc})", "warn")
        _notify_warning(app, f"Rename warning: row refresh failed ({exc})")
        app._refresh_data()
        app._refresh_table()
        app._refresh_side()
        return

    app._remove_paths_local([current])
    app._move_opened_ts_local(current, target)
    app._upsert_row_local(updated)
    app.multi_selected = {(target if app._same_path(p, current) else p) for p in app.multi_selected}
    app.selected_path = target
    app._touch_rows_cache([updated], removed=[current])
    app._start_cache_refresh("rename item", force=False)
    hooks_runtime.dispatch_post(
        app,
        event="rename",
        targets=[snapshot_target(updated, load_base_data(updated.path))],
        change={
            "old_path": current,
            "new_path": target,
            "old_name": current.name,
            "new_name": target.name,
            "old_note_path": old_note_path,
            "new_note_path": new_note_path,
            "rendered_note_cmd": rendered_note_cmd,
        },
        view=app.view_mode,
    )
    app._refresh_table()
    app._log(f"renamed: {current.name} -> {target.name}", "info")
    app._refresh_side()
