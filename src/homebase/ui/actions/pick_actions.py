from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow
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
    }
    handler = handlers.get(value)
    if handler is not None and handler():
        return

    if not targets:
        return
    paths = [r.path for r in targets]
    title, details = app._build_bulk_confirm_payload(value, paths)
    app.push_screen(app._confirm_screen_cls(title, details), lambda ok: app._on_confirm_bulk(ok, value, paths))
