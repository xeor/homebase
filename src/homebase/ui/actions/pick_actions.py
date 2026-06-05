from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow
from ...workspace.worktree_paths import find_worktree_children
from ..screens.choices import SingleChoiceScreen
from ..screens.rename import RenameInputScreen
from .dispatch import dispatch_action


def _truncate(text: str, limit: int = 70) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_set_desc_side_info(app: Any, targets: list[ProjectRow]) -> str:
    """Side-info block for the Set Description dialog.

    Shows the existing description per target (so the user sees what
    they're about to overwrite) and a packed-archive warning when any
    selected entry is packed.
    """
    lines: list[str] = []
    max_preview = 8
    if len(targets) > 1:
        with_desc = sum(1 for r in targets if r.description)
        lines.append(
            f"[cyan]targets[/]: {len(targets)}  "
            f"[dim](with existing description: {with_desc})[/]"
        )
    if any(r.packed for r in targets):
        lines.append("[yellow]some targets are packed — update may be slower[/]")
    lines.append("[cyan]current descriptions[/]:")
    for row in targets[:max_preview]:
        marker = "[dim](empty)[/]" if not row.description else app._esc(_truncate(row.description))
        lines.append(f"  - {app._esc(row.name)}: {marker}")
    if len(targets) > max_preview:
        lines.append(f"  [dim]... +{len(targets) - max_preview} more[/]")
    return "\n".join(lines)


def on_pick_actions(app: Any, value: str | None) -> None:
    if not value or value.startswith("__hdr__") or value == "noop":
        return
    if value.startswith("tab:") or value.startswith("tab."):
        from .dispatch import normalize_action_target

        dispatch_action(app, normalize_action_target(value))
        return
    if value.startswith("custom:"):
        dispatch_action(app, value.split(":", 1)[1])
        return
    ctx = getattr(app, "ctx", None)
    actions = getattr(ctx, "actions", {}) if ctx is not None else {}
    action = actions.get(value) if isinstance(actions, dict) else None
    if action is not None and action.kind != "builtin":
        dispatch_action(app, value)
        return

    button_handlers: dict[str, Callable[[], None]] = {
        "readme_create": lambda: app._run_readme_button_action("readme_create"),
        "readme_edit": lambda: app._run_readme_button_action("readme_edit"),
        "notes_create": lambda: app._run_notes_button_action("notes_create"),
        "notes_open": lambda: app._run_notes_button_action("notes_open"),
    }
    button_handler = button_handlers.get(value)
    if button_handler is not None:
        button_handler()
        return

    targets = app._target_rows()

    def _handle_tags_set() -> bool:
        if not targets:
            return True
        if any(r.packed for r in targets):
            app._log("packed archive selected: tag updates may be slower", "warn")
        app.action_pick_tags()
        return True

    def _handle_suffix_set() -> bool:
        if not targets:
            return True
        if app.view_mode != "active":
            app._log("suffix update is only available in active view", "warn")
            app._refresh_side()
            return True
        app.action_pick_category()
        return True

    def _handle_refresh_cache() -> bool:
        app._start_cache_refresh("manual refresh", force=True)
        app._log("cache refresh requested", "info")
        app._refresh_side()
        return True

    def _handle_full_reconcile() -> bool:
        app._start_cache_refresh("manual full reconcile", force=True)
        app._log("full reconcile requested", "info")
        app._refresh_side()
        return True

    def _handle_edit_global_config() -> bool:
        app._edit_global_config_and_reload()
        return True

    def _handle_reload_global_config() -> bool:
        app._reload_global_config()
        return True

    def _handle_reconcile_all_cache() -> bool:
        all_paths = [r.path for r in (app.active_rows + app.archived_rows)]
        if not all_paths:
            app._log("reconcile skipped: no rows", "warn")
            app._refresh_side()
            return True
        app._start_reconcile_rows("mixed", "manual-all", all_paths)
        app._log(f"reconcile requested for all rows ({len(all_paths)})", "info")
        app._refresh_side()
        return True

    def _handle_reconcile_selection_cache() -> bool:
        if not targets:
            app._log("reconcile skipped: no target", "warn")
            app._refresh_side()
            return True
        paths = [r.path for r in targets]
        mode = (
            "archive"
            if all(r.archived for r in targets)
            else ("active" if all(not r.archived for r in targets) else "mixed")
        )
        app._start_reconcile_rows(mode, "manual-target", paths)
        app._log(f"reconcile requested for target ({len(paths)})", "info")
        app._refresh_side()
        return True

    def _handle_rename_item() -> bool:
        paths = [r.path for r in targets]
        if not paths:
            return True

        def _prompt_next_rename(queue: list[Path], done: int, total: int) -> None:
            if not queue:
                app._refresh_side()
                return
            current = queue[0]
            current_name = current.name
            find_row = getattr(app, "_find_row", None)
            if callable(find_row):
                hit = find_row(current)
                if hit is not None:
                    rows, idx = hit
                    current_name = rows[idx].name
            title = f"Rename target ({done + 1}/{total})"
            app.pending_rename_target = current
            app.push_screen(
                RenameInputScreen(
                    title,
                    current,
                    app.base_dir,
                    current_name=current_name,
                ),
                lambda value: _on_rename_submit(value, queue, done, total),
            )

        def _on_rename_submit(
            value: str | None,
            queue: list[Path],
            done: int,
            total: int,
        ) -> None:
            current = queue.pop(0)
            app.pending_rename_target = current
            app._on_rename_item(value)
            _prompt_next_rename(queue, done + 1, total)

        _prompt_next_rename(list(paths), 0, len(paths))
        return True

    def _handle_meta_actions() -> bool:
        paths = [r.path for r in targets]
        if not paths:
            return True

        def _prompt_next_meta(queue: list[Path]) -> None:
            if not queue:
                app._refresh_side()
                return
            current = queue[0]
            title, details = app._build_bulk_confirm_payload(value, [current])
            app.push_screen(
                app._confirm_screen_cls(title, details),
                lambda ok: _on_meta_confirm(ok, queue),
            )

        def _on_meta_confirm(ok: bool, queue: list[Path]) -> None:
            current = queue.pop(0)
            app._on_confirm_bulk(ok, value, [current])
            if not ok:
                return
            _prompt_next_meta(queue)

        _prompt_next_meta(list(paths))
        return True

    def _handle_set_desc() -> bool:
        if not targets:
            return True
        if any(r.packed for r in targets):
            app._log("packed archive selected: description updates may be slower", "warn")
        app.pending_desc_targets = [r.path for r in targets]
        initial = targets[0].description if len(targets) == 1 else ""
        title = (
            "Set description (empty clears)"
            if len(targets) == 1
            else f"Set description for {len(targets)} targets (empty clears)"
        )
        side_info = _build_set_desc_side_info(app, targets)
        app.push_screen(
            app._input_screen_cls(
                title,
                "short summary",
                initial,
                side_info=side_info,
            ),
            app._on_set_description,
        )
        return True

    def _handle_hooks_refresh() -> bool:
        app._hooks_refresh_action(workspace_scope=False)
        return True

    def _handle_hooks_refresh_view() -> bool:
        app._hooks_refresh_action(workspace_scope=True)
        return True

    def _handle_new_worktree() -> bool:
        if len(targets) != 1:
            app._log("new worktree requires a single target", "warn")
            app._refresh_side()
            return True
        row = targets[0]
        if row.archived:
            app._log("cannot create worktree from archived project", "warn")
            app._refresh_side()
            return True
        parent_name = row.worktree_of or row.name
        app._action_new_worktree(parent_name)
        return True

    def _handle_deworktree() -> bool:
        worktree_rows = [r for r in targets if getattr(r, "worktree_of", "")]
        if not worktree_rows:
            app._log("de-worktree skipped: no worktree rows in target", "warn")
            app._refresh_side()
            return True
        paths = [r.path for r in worktree_rows]
        title, details = app._build_bulk_confirm_payload("deworktree", paths)
        app.push_screen(
            app._confirm_screen_cls(title, details),
            lambda ok: app._on_confirm_bulk(ok, "deworktree", paths),
        )
        return True

    def _handle_fix_worktrees() -> bool:
        app._action_fix_worktrees()
        return True

    def _parent_targets_with_children(target_rows: list[ProjectRow]) -> list[tuple[ProjectRow, list[Path]]]:
        out: list[tuple[ProjectRow, list[Path]]] = []
        for row in target_rows:
            if getattr(row, "archived", False):
                continue
            if getattr(row, "worktree_of", ""):
                continue
            children = find_worktree_children(app.base_dir, row.name)
            if children:
                out.append((row, children))
        return out

    def _handle_delete() -> bool:
        if not targets:
            return False
        parents = _parent_targets_with_children(targets)
        if not parents:
            return False
        parent_row, worktrees = parents[0]
        names = ", ".join(p.name for p in worktrees[:6])
        if len(worktrees) > 6:
            names += f" (+{len(worktrees) - 6} more)"
        title = f"Delete {parent_row.name}: {len(worktrees)} active worktree(s) — {names}"
        options = [
            ("delete_orphan", "Delete parent only (worktrees become orphaned)"),
            ("deworktree_first", "De-worktree all first, then delete parent"),
        ]
        paths = [r.path for r in targets]
        worktree_paths_list = [wt for wt in worktrees]

        def _on_choice(choice: str | None) -> None:
            if not choice:
                app._log("delete cancelled", "warn")
                app._refresh_side()
                return
            if choice == "deworktree_first":
                app._run_family_deworktree_then("delete", worktree_paths_list, paths)
                return
            # delete_orphan: fall through to standard bulk confirm.
            t2, d2 = app._build_bulk_confirm_payload("delete", paths)
            app.push_screen(
                app._confirm_screen_cls(t2, d2),
                lambda ok: app._on_confirm_bulk(ok, "delete", paths),
            )

        app.push_screen(SingleChoiceScreen(title, options), _on_choice)
        return True

    def _handle_archive() -> bool:
        if not targets:
            return False
        parents = _parent_targets_with_children(targets)
        if not parents:
            return False
        parent_row, worktrees = parents[0]
        names = ", ".join(p.name for p in worktrees[:6])
        if len(worktrees) > 6:
            names += f" (+{len(worktrees) - 6} more)"
        title = f"Archive {parent_row.name}: {len(worktrees)} active worktree(s) — {names}"
        options = [
            ("deworktree_first", "De-worktree all first, then archive parent"),
            ("archive_together", "Archive parent + all worktrees together"),
        ]
        paths = [r.path for r in targets]
        worktree_paths_list = [wt for wt in worktrees]

        def _on_choice(choice: str | None) -> None:
            if not choice:
                app._log("archive cancelled", "warn")
                app._refresh_side()
                return
            if choice == "deworktree_first":
                app._run_family_deworktree_then("archive", worktree_paths_list, paths)
                return
            if choice == "archive_together":
                app._run_family_archive_together(parent_row.path, worktree_paths_list)
                return

        app.push_screen(SingleChoiceScreen(title, options), _on_choice)
        return True

    handlers: dict[str, Callable[[], bool]] = {
        "tags_set": _handle_tags_set,
        "suffix_set": _handle_suffix_set,
        "refresh_cache": _handle_refresh_cache,
        "full_reconcile": _handle_full_reconcile,
        "edit_global_config": _handle_edit_global_config,
        "reload_global_config": _handle_reload_global_config,
        "reconcile_all_cache": _handle_reconcile_all_cache,
        "reconcile_selection_cache": _handle_reconcile_selection_cache,
        "rename_item": _handle_rename_item,
        "review_meta": _handle_meta_actions,
        "rename_meta_ext": _handle_meta_actions,
        "set_desc": _handle_set_desc,
        "hooks_refresh": _handle_hooks_refresh,
        "hooks_refresh_view": _handle_hooks_refresh_view,
        "new_worktree": _handle_new_worktree,
        "deworktree": _handle_deworktree,
        "fix_worktrees": _handle_fix_worktrees,
        "delete": _handle_delete,
        "archive": _handle_archive,
    }
    handler = handlers.get(value)
    if handler is not None and handler():
        return

    if not targets:
        return
    paths = [r.path for r in targets]
    title, details = app._build_bulk_confirm_payload(value, paths)
    app.push_screen(app._confirm_screen_cls(title, details), lambda ok: app._on_confirm_bulk(ok, value, paths))
