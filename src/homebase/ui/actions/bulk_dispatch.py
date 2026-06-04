from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ...core.models import HookTarget, ProjectRow
from ...hooks import runtime as hooks_runtime
from ...hooks.snapshot import snapshot_target
from ...metadata.api import load_base_data
from . import note_sync as note_sync_actions


def _notify_warning(app: Any, message: str) -> None:
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        notifier(message, severity="warning")


def _archive_note_sync_with_rollback(
    app: Any,
    *,
    source_path: Path,
    archived_path: Path,
    archive_restore_internal: Callable[..., Path],
) -> bool:
    resolve_notes = getattr(app, "_resolve_notes_path_for_row", None)
    if not callable(resolve_notes):
        return True
    enabled, command_template = note_sync_actions.note_sync_config(app, "archive")
    if not enabled:
        return True
    source_hit = app._find_row(source_path)
    if source_hit is None:
        return True
    source_rows, source_idx = source_hit
    source_row = source_rows[source_idx]
    try:
        old_note_path = resolve_notes(source_row)
    except (OSError, ValueError, RuntimeError):
        return True
    try:
        if not old_note_path.is_file():
            return True
    except OSError as exc:
        app._log(f"archive note sync failed for {source_path.name}: {exc}", "error")
        _notify_warning(app, f"Archive note sync failed: {exc}")
        return False

    try:
        archived_row = app._build_archived_row_from_entry(archived_path)
        new_note_path = resolve_notes(archived_row)
    except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as exc:
        app._log(f"archive note sync failed for {source_path.name}: {exc}", "error")
        _notify_warning(app, f"Archive note sync failed: {exc}")
        try:
            archive_restore_internal(app.base_dir, archived_path, sync_tags=False)
        except ValueError as rollback_exc:
            app._log(
                f"archive rollback failed for {source_path.name}: {rollback_exc}",
                "error",
            )
            _notify_warning(app, f"Archive rollback failed: {rollback_exc}")
        return False

    try:
        if new_note_path.exists() and new_note_path != old_note_path:
            msg = f"target note exists ({new_note_path})"
            app._log(f"archive note sync aborted for {source_path.name}: {msg}", "warn")
            _notify_warning(app, f"Archive note sync aborted: {msg}")
            try:
                archive_restore_internal(app.base_dir, archived_path, sync_tags=False)
            except ValueError as rollback_exc:
                app._log(
                    f"archive rollback failed for {source_path.name}: {rollback_exc}",
                    "error",
                )
                _notify_warning(app, f"Archive rollback failed: {rollback_exc}")
            return False
        if command_template:
            cmd = note_sync_actions.build_note_sync_command(
                app,
                source_row=source_row,
                target_row=archived_row,
                old_note_path=old_note_path,
                new_note_path=new_note_path,
                command_template=command_template,
            )
            if not cmd:
                raise OSError("archive note command rendered empty")
            proc = subprocess.run(
                ["sh", "-lc", cmd],
                cwd=str(app.base_dir),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or f"exit={proc.returncode}"
                raise OSError(err)
        else:
            new_note_path.parent.mkdir(parents=True, exist_ok=True)
            old_note_path.rename(new_note_path)
    except OSError as exc:
        app._log(f"archive note sync failed for {source_path.name}: {exc}", "error")
        _notify_warning(app, f"Archive note sync failed: {exc}")
        try:
            archive_restore_internal(app.base_dir, archived_path, sync_tags=False)
        except ValueError as rollback_exc:
            app._log(
                f"archive rollback failed for {source_path.name}: {rollback_exc}",
                "error",
            )
            _notify_warning(app, f"Archive rollback failed: {rollback_exc}")
        return False
    return True


@dataclass
class _BulkCallbacks:
    archive_move_internal: Callable[..., Path]
    archive_restore_internal: Callable[..., Path]
    archive_pack_internal: Callable[[Path, Path], Path]
    archive_unpack_internal: Callable[[Path, Path], Path]
    delete_internal: Callable[..., None]
    is_packed_archive_path: Callable[[Path], bool]
    open_meta_for_review: Callable[[Path], tuple[bool, str]]
    rename_legacy_base_yaml: Callable[[Path], tuple[bool, str]]
    project_row: Callable[..., ProjectRow]
    row_build_errors: tuple[type[BaseException], ...]
    deworktree_internal: Callable[[Path, Path], None]


@dataclass
class _BulkState:
    success: int = 0
    failed: int = 0
    removed_paths: list[Path] = field(default_factory=list)
    upsert_rows: list[ProjectRow] = field(default_factory=list)


def _safe_build_archived_row(app: Any, path: Path, errors: tuple) -> ProjectRow | None:
    try:
        return app._build_archived_row_from_entry(path)
    except errors:
        return None


def _action_archive(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    dest = cb.archive_move_internal(app.base_dir, path, sync_tags=False)
    if not _archive_note_sync_with_rollback(
        app,
        source_path=path,
        archived_path=dest,
        archive_restore_internal=cb.archive_restore_internal,
    ):
        return False, None, None
    app._log(f"archived: {path.name} -> {dest}", "info")
    return True, path, _safe_build_archived_row(app, dest, cb.row_build_errors)


def _action_restore(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    restored = cb.archive_restore_internal(app.base_dir, path, sync_tags=False)
    app._log(f"restored: {path.name} -> {restored}", "info")
    return True, None, None


def _action_pack(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    packed_path = cb.archive_pack_internal(app.base_dir, path)
    app._log(f"packed: {path.name} -> {packed_path.name}", "info")
    return True, path, _safe_build_archived_row(app, packed_path, cb.row_build_errors)


def _action_unpack(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    unpacked_path = cb.archive_unpack_internal(app.base_dir, path)
    app._log(f"unpacked: {path.name} -> {unpacked_path.name}", "info")
    return True, path, _safe_build_archived_row(app, unpacked_path, cb.row_build_errors)


def _action_toggle_pack(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    if cb.is_packed_archive_path(path):
        new_path = cb.archive_unpack_internal(app.base_dir, path)
        verb = "unpacked"
    else:
        new_path = cb.archive_pack_internal(app.base_dir, path)
        verb = "packed"
    app._log(f"{verb}: {path.name} -> {new_path.name}", "info")
    return True, path, _safe_build_archived_row(app, new_path, cb.row_build_errors)


def _action_delete(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    cb.delete_internal(app.base_dir, path, sync_tags=False)
    app._log(f"deleted: {path}", "info")
    return True, path, None


def _action_deworktree(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    cb.deworktree_internal(app.base_dir, path)
    app._log(f"deworktreed: {path.name}", "info")
    try:
        return True, None, cb.project_row(path, archived=False)
    except cb.row_build_errors:
        return True, None, None


def _action_review_meta(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    ok_review, msg = cb.open_meta_for_review(path)
    if not ok_review:
        app._log(f"review failed for {path.name}: {msg}", "error")
        return False, None, None
    app._log(f"review opened: {path.name}", "info")
    return True, None, None


_RENAME_META_ROW_ERRORS = (
    OSError, ValueError, TypeError, subprocess.SubprocessError, sqlite3.Error,
)


def _rename_meta_upsert(app: Any, path: Path, cb: _BulkCallbacks) -> ProjectRow | None:
    try:
        cur = app._find_row(path)
        if cur is not None:
            rws, ridx = cur
            cur_row = rws[ridx]
            return cb.project_row(
                path,
                archived=cur_row.archived,
                restore_target=cur_row.restore_target,
                archived_ts=cur_row.archived_ts,
            )
        return cb.project_row(path, archived=False)
    except _RENAME_META_ROW_ERRORS:
        return None


def _action_rename_meta_ext(app: Any, path: Path, cb: _BulkCallbacks) -> tuple[bool, Path | None, ProjectRow | None]:
    ok_rename, msg = cb.rename_legacy_base_yaml(path)
    if not ok_rename:
        app._log(f"rename failed for {path.name}: {msg}", "error")
        return False, None, None
    app._log(f"renamed metadata extension: {path.name}", "info")
    return True, None, _rename_meta_upsert(app, path, cb)


_ACTION_HANDLERS: dict[str, Callable[[Any, Path, _BulkCallbacks], tuple[bool, Path | None, ProjectRow | None]]] = {
    "archive": _action_archive,
    "restore": _action_restore,
    "pack": _action_pack,
    "unpack": _action_unpack,
    "toggle_pack": _action_toggle_pack,
    "delete": _action_delete,
    "deworktree": _action_deworktree,
    "review_meta": _action_review_meta,
    "rename_meta_ext": _action_rename_meta_ext,
}


def _run_one(
    app: Any,
    action: str,
    path: Path,
    cb: _BulkCallbacks,
    state: _BulkState,
) -> None:
    handler = _ACTION_HANDLERS.get(action)
    if handler is None:
        app._log(f"unknown action: {action}", "error")
        state.failed += 1
        return
    try:
        success, removed, upsert = handler(app, path, cb)
    except ValueError as exc:
        state.failed += 1
        app._log(f"{action} failed for {path.name}: {exc}", "error")
        return
    if not success:
        state.failed += 1
        if action == "archive":
            app.multi_selected.discard(path)
        return
    if removed is not None:
        state.removed_paths.append(removed)
    if upsert is not None:
        state.upsert_rows.append(upsert)
    state.success += 1
    app.multi_selected.discard(path)


def _build_delete_snapshots(
    app: Any, runnable_paths: list[Path]
) -> tuple[list[HookTarget], dict[Path, dict[str, object]]]:
    delete_targets: list[HookTarget] = []
    removed_snapshots: dict[Path, dict[str, object]] = {}
    for path in runnable_paths:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        row = rows[idx]
        try:
            base_meta = load_base_data(path)
        except OSError:
            base_meta = {}
        target = snapshot_target(row, base_meta)
        delete_targets.append(target)
        removed_snapshots[path] = {
            "name": target.name,
            "archived": target.archived,
            "tags": list(target.tags),
            "properties": list(target.properties),
            "description": target.description,
            "wip": target.wip,
            "suffix": target.suffix,
            "packed": target.packed,
            "base_meta": dict(target.base_meta),
        }
    return delete_targets, removed_snapshots


def _maybe_run_pre_delete_hook(
    app: Any,
    action: str,
    runnable_paths: list[Path],
) -> tuple[list[HookTarget], dict[Path, dict[str, object]], bool]:
    """Return (delete_targets, removed_snapshots, cancelled)."""
    if action != "delete":
        return [], {}, False
    delete_targets, removed_snapshots = _build_delete_snapshots(app, runnable_paths)
    pre_outcome = hooks_runtime.dispatch_pre(
        app,
        event="delete",
        targets=delete_targets,
        change={
            "removed_paths": [target.path for target in delete_targets],
            "removed_snapshots": removed_snapshots,
        },
        view=app.view_mode,
    )
    if pre_outcome.cancelled:
        app._log(f"delete cancelled by hook: {pre_outcome.reason}", "warn")
        app._refresh_side()
        return delete_targets, removed_snapshots, True
    return delete_targets, removed_snapshots, False


def _finalize_bulk(
    app: Any,
    action: str,
    state: _BulkState,
    delete_targets: list[HookTarget],
    removed_snapshots: dict[Path, dict[str, object]],
) -> None:
    if state.removed_paths:
        app._remove_paths_local(state.removed_paths)
    if action in {"archive", "restore"}:
        app._request_tag_sync(f"{action} update")
    if action == "delete" and delete_targets:
        hooks_runtime.dispatch_post(
            app,
            event="delete",
            targets=delete_targets,
            change={
                "removed_paths": [target.path for target in delete_targets],
                "removed_snapshots": removed_snapshots,
            },
            view=app.view_mode,
        )
    for row in state.upsert_rows:
        app._upsert_row_local(row)
    if state.removed_paths or state.upsert_rows:
        app._touch_rows_cache(state.upsert_rows, removed=state.removed_paths)
        app._start_cache_refresh(f"{action} update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(
        f"{action} finished: ok={state.success}, failed={state.failed}", "info"
    )
    app._refresh_side()


def _preflight(
    app: Any, action: str, paths: list[Path]
) -> tuple[list[Path], bool]:
    """Return (runnable, should_continue). should_continue=False means
    side-effects already done; caller must return."""
    runnable_paths, skipped_paths = app._preflight_bulk_action(action, paths)
    if skipped_paths:
        app._log(
            f"{action} preflight skipped {len(skipped_paths)} item(s): "
            f"{app._preflight_skip_summary(skipped_paths)}",
            "warn",
        )
    if not runnable_paths:
        app._log(f"{action} skipped: no eligible items", "warn")
        app._refresh_side()
        return [], False
    return runnable_paths, True


def _maybe_handle_async_action(
    app: Any, action: str, runnable_paths: list[Path]
) -> bool:
    """Restore + pack/unpack/toggle_pack are dispatched to async workers.
    Return True if handled (caller must return)."""
    if action == "restore":
        app.pending_restore_queue = list(runnable_paths)
        app.pending_restore_ok = 0
        app.pending_restore_failed = 0
        app._busy_start("restoring target items")
        app._process_next_restore()
        return True
    if action in {"pack", "unpack", "toggle_pack"}:
        app._start_archive_action_worker(action, list(runnable_paths))
        return True
    return False


def on_confirm_bulk(
    app: Any,
    ok: bool,
    action: str,
    paths: list[Path],
    *,
    archive_move_internal: Callable[..., Path],
    archive_restore_internal: Callable[..., Path],
    archive_pack_internal: Callable[[Path, Path], Path],
    archive_unpack_internal: Callable[[Path, Path], Path],
    delete_internal: Callable[..., None],
    is_packed_archive_path: Callable[[Path], bool],
    open_meta_for_review: Callable[[Path], tuple[bool, str]],
    rename_legacy_base_yaml: Callable[[Path], tuple[bool, str]],
    project_row: Callable[..., ProjectRow],
    row_build_errors: tuple[type[BaseException], ...],
    deworktree_internal: Callable[[Path, Path], None],
) -> None:
    if not ok:
        app._log(f"{action} cancelled", "warn")
        app._refresh_side()
        return

    runnable_paths, cont = _preflight(app, action, paths)
    if not cont:
        return

    if _maybe_handle_async_action(app, action, runnable_paths):
        return

    delete_targets, removed_snapshots, cancelled = _maybe_run_pre_delete_hook(
        app, action, runnable_paths
    )
    if cancelled:
        return

    cb = _BulkCallbacks(
        archive_move_internal=archive_move_internal,
        archive_restore_internal=archive_restore_internal,
        archive_pack_internal=archive_pack_internal,
        archive_unpack_internal=archive_unpack_internal,
        delete_internal=delete_internal,
        is_packed_archive_path=is_packed_archive_path,
        open_meta_for_review=open_meta_for_review,
        rename_legacy_base_yaml=rename_legacy_base_yaml,
        project_row=project_row,
        row_build_errors=row_build_errors,
        deworktree_internal=deworktree_internal,
    )
    state = _BulkState()
    app._busy_start(f"running {action} on target")
    try:
        for path in runnable_paths:
            app._busy_tick()
            _run_one(app, action, path, cb, state)
    finally:
        app._busy_stop()

    _finalize_bulk(app, action, state, delete_targets, removed_snapshots)
