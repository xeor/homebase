from __future__ import annotations

from typing import Any


def normalize_action_target(value: str) -> str:
    target = str(value or "").strip()
    if not target:
        return ""
    if target.startswith("action:custom:"):
        return target.split(":", 2)[2]
    if target.startswith("action:"):
        return target.split(":", 1)[1]
    if target.startswith("tab:"):
        payload = target.split(":", 1)[1]
        if not payload:
            return ""
        return "tab." + payload.replace("/", ".")
    return target


def dispatch_action(app: Any, action_id: str) -> None:
    aid = str(action_id or "").strip()
    if not aid:
        return
    if aid == "open_selected":
        app.action_open_selected()
        return
    if aid.startswith("tab."):
        payload = aid[len("tab.") :]
        if not payload:
            return
        parts = payload.split(".")
        top = parts[0]
        child = ".".join(parts[1:]) if len(parts) > 1 else ""
        app._jump_to_side_tab(top, child_key=child)
        return

    ctx = getattr(app, "ctx", None)
    actions = getattr(ctx, "actions", {}) if ctx is not None else {}
    action = actions.get(aid) if isinstance(actions, dict) else None
    if action is None and aid.startswith("custom:"):
        app._on_pick_actions(aid)
        return
    if action is None and hasattr(app, "_run_custom_action") and not aid.startswith("tab."):
        if aid not in {
            "readme_create",
            "readme_edit",
            "notes_create",
            "notes_open",
            "tags_set",
            "reconcile_selection_cache",
            "suffix_set",
            "archive",
            "restore",
            "pack",
            "unpack",
            "toggle_pack",
            "delete",
            "set_desc",
            "rename_item",
            "review_meta",
            "rename_meta_ext",
            "refresh_cache",
            "full_reconcile",
            "reconcile_all_cache",
            "edit_global_config",
            "reload_global_config",
            "hooks_refresh",
            "hooks_refresh_view",
            "new_worktree",
            "deworktree",
        }:
            app._run_custom_action(aid)
            return
    if action is None:
        app._on_pick_actions(aid)
        return
    if action.kind == "builtin":
        app._on_pick_actions(aid)
        return

    app._run_custom_action(aid)
