from __future__ import annotations

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


def _archive_note_sync_with_rollback(
    app: Any,
    *,
    source_path: Path,
    archived_path: Path,
    archive_restore_internal: Callable[[Path, Path, bool], Path],
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


def on_confirm_bulk(
    app: Any,
    ok: bool,
    action: str,
    paths: list[Path],
    *,
    archive_move_internal: Callable[[Path, Path, bool], Path],
    archive_restore_internal: Callable[[Path, Path, bool], Path],
    archive_pack_internal: Callable[[Path, Path], Path],
    archive_unpack_internal: Callable[[Path, Path], Path],
    delete_internal: Callable[[Path, Path, bool], None],
    is_packed_archive_path: Callable[[Path], bool],
    open_meta_for_review: Callable[[Path], tuple[bool, str]],
    rename_legacy_base_yaml: Callable[[Path], tuple[bool, str]],
    project_row: Callable[..., ProjectRow],
    row_build_errors: tuple[type[BaseException], ...],
) -> None:
    if not ok:
        app._log(f"{action} cancelled", "warn")
        app._refresh_side()
        return

    runnable_paths, skipped_paths = app._preflight_bulk_action(action, paths)
    if skipped_paths:
        app._log(
            f"{action} preflight skipped {len(skipped_paths)} item(s): {app._preflight_skip_summary(skipped_paths)}",
            "warn",
        )
    if not runnable_paths:
        app._log(f"{action} skipped: no eligible items", "warn")
        app._refresh_side()
        return

    if action == "restore":
        app.pending_restore_queue = list(runnable_paths)
        app.pending_restore_ok = 0
        app.pending_restore_failed = 0
        app._busy_start("restoring target items")
        app._process_next_restore()
        return

    if action in {"pack", "unpack", "toggle_pack"}:
        app._start_archive_action_worker(action, list(runnable_paths))
        return

    success = 0
    failed = 0
    removed_paths: list[Path] = []
    upsert_rows: list[ProjectRow] = []
    delete_targets: list[object] = []
    removed_snapshots: dict[Path, dict[str, object]] = {}
    if action == "delete":
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
    app._busy_start(f"running {action} on target")
    try:
        for path in runnable_paths:
            app._busy_tick()
            try:
                if action == "archive":
                    dest = archive_move_internal(app.base_dir, path, sync_tags=False)
                    if not _archive_note_sync_with_rollback(
                        app,
                        source_path=path,
                        archived_path=dest,
                        archive_restore_internal=archive_restore_internal,
                    ):
                        failed += 1
                        app.multi_selected.discard(path)
                        continue
                    app._log(f"archived: {path.name} -> {dest}", "info")
                    removed_paths.append(path)
                    try:
                        upsert_rows.append(app._build_archived_row_from_entry(dest))
                    except row_build_errors:
                        pass
                elif action == "restore":
                    restored = archive_restore_internal(app.base_dir, path, sync_tags=False)
                    app._log(f"restored: {path.name} -> {restored}", "info")
                elif action == "pack":
                    packed_path = archive_pack_internal(app.base_dir, path)
                    app._log(f"packed: {path.name} -> {packed_path.name}", "info")
                    removed_paths.append(path)
                    try:
                        upsert_rows.append(app._build_archived_row_from_entry(packed_path))
                    except row_build_errors:
                        pass
                elif action == "unpack":
                    unpacked_path = archive_unpack_internal(app.base_dir, path)
                    app._log(f"unpacked: {path.name} -> {unpacked_path.name}", "info")
                    removed_paths.append(path)
                    try:
                        upsert_rows.append(
                            app._build_archived_row_from_entry(unpacked_path)
                        )
                    except row_build_errors:
                        pass
                elif action == "toggle_pack":
                    if is_packed_archive_path(path):
                        new_path = archive_unpack_internal(app.base_dir, path)
                        verb = "unpacked"
                    else:
                        new_path = archive_pack_internal(app.base_dir, path)
                        verb = "packed"
                    app._log(f"{verb}: {path.name} -> {new_path.name}", "info")
                    removed_paths.append(path)
                    try:
                        upsert_rows.append(app._build_archived_row_from_entry(new_path))
                    except row_build_errors:
                        pass
                elif action == "delete":
                    delete_internal(app.base_dir, path, sync_tags=False)
                    app._log(f"deleted: {path}", "info")
                    removed_paths.append(path)
                elif action == "review_meta":
                    ok_review, msg = open_meta_for_review(path)
                    if not ok_review:
                        failed += 1
                        app._log(f"review failed for {path.name}: {msg}", "error")
                        continue
                    app._log(f"review opened: {path.name}", "info")
                elif action == "rename_meta_ext":
                    ok_rename, msg = rename_legacy_base_yaml(path)
                    if not ok_rename:
                        failed += 1
                        app._log(f"rename failed for {path.name}: {msg}", "error")
                        continue
                    app._log(f"renamed metadata extension: {path.name}", "info")
                    try:
                        cur = app._find_row(path)
                        if cur is not None:
                            rws, ridx = cur
                            cur_row = rws[ridx]
                            upsert_rows.append(
                                project_row(
                                    path,
                                    archived=cur_row.archived,
                                    restore_target=cur_row.restore_target,
                                    archived_ts=cur_row.archived_ts,
                                )
                            )
                        else:
                            upsert_rows.append(project_row(path, archived=False))
                    except (
                        OSError,
                        ValueError,
                        TypeError,
                        subprocess.SubprocessError,
                        sqlite3.Error,
                    ):
                        pass
                else:
                    app._log(f"unknown action: {action}", "error")
                    failed += 1
                    continue
                success += 1
                app.multi_selected.discard(path)
            except ValueError as exc:
                failed += 1
                app._log(f"{action} failed for {path.name}: {exc}", "error")
    finally:
        app._busy_stop()

    if removed_paths:
        app._remove_paths_local(removed_paths)
    if action in {"archive", "restore", "delete"}:
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
    for row in upsert_rows:
        app._upsert_row_local(row)
    if removed_paths or upsert_rows:
        app._touch_rows_cache(upsert_rows, removed=removed_paths)
        app._start_cache_refresh(f"{action} update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(f"{action} finished: ok={success}, failed={failed}", "info")
    app._refresh_side()
