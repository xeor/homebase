from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import yaml

from ...core.models import ProjectRow
from ...workspace.projects import refresh_row_caches


def tag_plan_model_for_paths(
    app: Any,
    paths: list[Path],
    view_mode: str,
) -> tuple[list[str], dict[str, str], dict[str, int]]:
    target_paths = set(paths)
    current_scope = app.active_rows if view_mode == "active" else app.archived_rows
    targets = [row for row in current_scope if row.path in target_paths]

    all_tags: set[str] = set()
    for row in app.active_rows + app.archived_rows:
        all_tags |= set(row.tags)
    for row in targets:
        all_tags |= set(row.tags)

    other_counts: dict[str, int] = {}
    for tag in sorted(all_tags):
        count = 0
        for row in current_scope:
            if row.path in target_paths:
                continue
            if tag in row.tags:
                count += 1
        other_counts[tag] = count

    presence: dict[str, str] = {}
    for tag in sorted(all_tags):
        count = sum(1 for row in targets if tag in row.tags)
        if targets and count == len(targets):
            presence[tag] = "all"
        elif count == 0:
            presence[tag] = "none"
        else:
            presence[tag] = "mixed"
    return sorted(all_tags), presence, other_counts


def rename_tag_globally(
    app: Any,
    old_tag: str,
    new_tag: str,
    *,
    base_dir: Path,
    save_base_tags: Callable[[Path, Path, list[str]], None],
) -> tuple[bool, str, bool]:
    old = old_tag.strip()
    new = new_tag.strip()
    if not old or not new:
        return False, "rename failed: empty tag", False
    if old == new:
        return True, "rename skipped: unchanged", False

    existed = any(new in row.tags for row in (app.active_rows + app.archived_rows))
    touched = 0
    changed_rows: list[ProjectRow] = []
    app._busy_start("renaming tag")
    try:
        for row in app.active_rows + app.archived_rows:
            if old not in row.tags:
                continue
            merged = sorted({(new if t == old else t).strip() for t in row.tags if t.strip()})
            try:
                save_base_tags(base_dir, row.path, merged)
            except (OSError, yaml.YAMLError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return False, f"rename failed for {row.name}: {exc}", existed
            row.tags = merged
            refresh_row_caches(row)
            row.stale = False
            row.cache_age_s = 0
            changed_rows.append(row)
            touched += 1
    finally:
        app._busy_stop()

    if changed_rows:
        app._touch_rows_cache(changed_rows)
        app._start_cache_refresh("tag rename", force=False)
        app._request_tag_sync("tag rename")
    app._refresh_table()
    app._refresh_side()

    msg = f"renamed '{old}' -> '{new}' on {touched} project(s)"
    return True, msg, existed


def delete_tag_globally(
    app: Any,
    tag: str,
    *,
    base_dir: Path,
    save_base_tags: Callable[[Path, Path, list[str]], None],
) -> tuple[bool, str]:
    victim = tag.strip()
    if not victim:
        return False, "delete failed: empty tag"
    touched = 0
    changed_rows: list[ProjectRow] = []
    app._busy_start("deleting tag")
    try:
        for row in app.active_rows + app.archived_rows:
            if victim not in row.tags:
                continue
            remaining = sorted({t for t in row.tags if t != victim and t.strip()})
            try:
                save_base_tags(base_dir, row.path, remaining)
            except (OSError, yaml.YAMLError, json.JSONDecodeError, TypeError, ValueError) as exc:
                return False, f"delete failed for {row.name}: {exc}"
            row.tags = remaining
            refresh_row_caches(row)
            row.stale = False
            row.cache_age_s = 0
            changed_rows.append(row)
            touched += 1
    finally:
        app._busy_stop()

    if changed_rows:
        app._touch_rows_cache(changed_rows)
        app._start_cache_refresh("tag delete", force=False)
        app._request_tag_sync("tag delete")
    app._refresh_table()
    app._refresh_side()
    return True, f"deleted '{victim}' from {touched} project(s)"


def action_pick_tags(app: Any, *, tag_plan_screen: Any) -> None:
    targets = app._target_rows()
    if not targets:
        return
    if any(r.archived for r in targets):
        app._log("archive tag update selected: packed entries may take longer", "warn")
        app._refresh_side()
    paths = [r.path for r in targets]

    all_tags, presence, other_counts = app._tag_plan_model_for_paths(paths, app.view_mode)

    app.push_screen(
        tag_plan_screen(
            all_tags,
            presence,
            other_counts,
            on_rename_tag=app._rename_tag_globally,
            on_delete_tag=app._delete_tag_globally,
            on_reload_model=lambda p=paths, v=app.view_mode: app._tag_plan_model_for_paths(p, v),
        ),
        lambda plan: app._on_pick_tags(plan, paths),
    )


def on_pick_tags(
    app: Any,
    plan: dict[str, str] | None,
    paths: list[Path],
    *,
    base_dir: Path,
    is_packed_archive_path: Callable[[Path], bool],
    load_base_meta: Callable[[Path], tuple[list[str], str, bool, int]],
    save_base_tags: Callable[[Path, Path, list[str]], None],
) -> None:
    if plan is None:
        app._log("tag update cancelled", "warn")
        app._refresh_side()
        return

    success = 0
    failed = 0
    successful_paths: set[Path] = set()
    app.pending_tag_updates = set(paths)
    app._refresh_table()
    app._busy_start("updating tags")
    try:
        for path in paths:
            app._busy_tick()
            if not path.exists() or (not path.is_dir() and not is_packed_archive_path(path)):
                failed += 1
                app._log(f"tag update failed for {path.name}: not found", "error")
                continue
            existing_tags, _desc, _wip = load_base_meta(path)
            tags = set(existing_tags)
            for tag, op in plan.items():
                if op == "add":
                    tags.add(tag)
                elif op == "remove":
                    tags.discard(tag)
            try:
                save_base_tags(base_dir, path, sorted(tags))
                success += 1
                successful_paths.add(path)
            except (OSError, yaml.YAMLError, json.JSONDecodeError, TypeError, ValueError) as exc:
                failed += 1
                app._log(f"tag update failed for {path.name}: {exc}", "error")
    finally:
        app._busy_stop()
        app.pending_tag_updates.clear()

    app._request_tag_sync("tag update")

    changed_rows: list[ProjectRow] = []
    for path in successful_paths:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        row = rows[idx]
        tags = set(row.tags)
        for tag, op in plan.items():
            if op == "add":
                tags.add(tag)
            elif op == "remove":
                tags.discard(tag)
        row.tags = sorted(tags)
        refresh_row_caches(row)
        row.stale = False
        row.cache_age_s = 0
        changed_rows.append(row)
    if changed_rows:
        app._touch_rows_cache(changed_rows)
        app._start_cache_refresh("tag update", force=False)
    else:
        app._refresh_data()
    app._refresh_table()
    app._log(f"tag update finished: ok={success}, failed={failed}", "info")
    app._refresh_side()
