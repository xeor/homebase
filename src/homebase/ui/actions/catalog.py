"""Single source of truth for what actions appear in the ctrl+a picker
and (together with extras) the ctrl+p command palette.

To add a new action so it shows up automatically:
  1. Register a BuiltinActionMeta in core/constants.py with the correct
     scope ("target" or "workspace") and view_scope.
  2. Make it appear in `valid_action_items` (action_items.py) when the
     state permits it.
  3. That's it — both ctrl+a and ctrl+p pick it up via this catalog.

To surface an action only in ctrl+p (not ctrl+a), add its id to
`PALETTE_ONLY_ACTION_IDS` below. These are typically maintenance/dev
commands that aren't user-facing "actions".

To attach an action to a notification (so it shows in the leftmost
Notifications tab while the notification is active), add an entry to
`notification_actions`.
"""

from __future__ import annotations

from typing import Any

from ...core.constants import BUILTIN_ACTIONS

CATEGORY_NOTIFICATIONS = "notifications"
CATEGORY_BUTTONS = "buttons"
CATEGORY_TARGET = "target"
CATEGORY_GLOBAL = "global"

# Tab order (left to right) and labels for ActionPickerScreen.
CATEGORY_ORDER: tuple[tuple[str, str], ...] = (
    (CATEGORY_NOTIFICATIONS, "Notifications"),
    (CATEGORY_BUTTONS, "Buttons"),
    (CATEGORY_TARGET, "Target"),
    (CATEGORY_GLOBAL, "Global"),
)

# Actions registered in BUILTIN_ACTIONS that should appear only in the
# ctrl+p command palette, not the ctrl+a action picker. Maintenance/
# dev commands belong here.
PALETTE_ONLY_ACTION_IDS: frozenset[str] = frozenset(
    {
        "hooks_refresh",
        "hooks_refresh_view",
    }
)


def scope_for_action(app: Any, action_id: str) -> str:
    """Return the category for an action ('target' or 'global').

    Custom actions declare scope on their Action record; builtins use
    BuiltinActionMeta.scope. Unknown ids default to 'target'.
    """
    actions = getattr(getattr(app, "ctx", None), "actions", {}) or {}
    custom = actions.get(action_id)
    if custom is not None and getattr(custom, "source", "builtin") != "builtin":
        return CATEGORY_GLOBAL if custom.scope == "workspace" else CATEGORY_TARGET
    meta = BUILTIN_ACTIONS.get(action_id)
    if meta is not None:
        return CATEGORY_GLOBAL if meta.scope == "workspace" else CATEGORY_TARGET
    return CATEGORY_TARGET


def notification_actions(app: Any) -> list[tuple[str, str]]:
    """Actions surfaced by currently-active notifications.

    Each entry is (action_id, rich_label). Empty when no notification
    is active. Future notification sources should add here.
    """
    out: list[tuple[str, str]] = []
    issues = list(getattr(app, "worktree_health_issues", []) or [])
    dismissed = bool(getattr(app, "worktree_health_dismissed", False))
    if issues and not dismissed:
        kinds: dict[str, int] = {}
        for issue in issues:
            key = str(issue.get("kind", "unknown")) if isinstance(issue, dict) else "unknown"
            kinds[key] = kinds.get(key, 0) + 1
        breakdown = ", ".join(f"{k}:{n}" for k, n in sorted(kinds.items()))
        out.append(
            (
                "fix_worktrees",
                f"[bold #FFD166]Fix worktree health[/] "
                f"[dim]({len(issues)} issue(s); {breakdown})[/]",
            )
        )
    return out


def build_picker_catalog(app: Any) -> dict[str, list[tuple[str, str]]]:
    """Build the categorized catalog for the ctrl+a action picker.

    Categories: notifications, buttons, target, global. Each maps to a
    list of (action_id, rich_label) pairs. Categories may be empty.
    """
    out: dict[str, list[tuple[str, str]]] = {
        CATEGORY_NOTIFICATIONS: [],
        CATEGORY_BUTTONS: [],
        CATEGORY_TARGET: [],
        CATEGORY_GLOBAL: [],
    }

    out[CATEGORY_NOTIFICATIONS].extend(notification_actions(app))
    out[CATEGORY_BUTTONS].extend(app._visible_button_actions())

    seen_in_picker: set[str] = set()
    for action_id, label in app._valid_action_items():
        if action_id in PALETTE_ONLY_ACTION_IDS:
            continue
        cat = scope_for_action(app, action_id)
        out[cat].append((action_id, label))
        seen_in_picker.add(action_id)

    return out


def palette_only_extras(app: Any) -> list[tuple[str, str, str]]:
    """Actions reserved for ctrl+p only (not in the ctrl+a picker).

    Returns a list of (action_id, rich_label, category) — category is
    used by the palette for the "Action > Target/Global" prefix.

    Only emits actions whose state currently permits them (target-scope
    requires a selection; workspace-scope is always available).
    """
    out: list[tuple[str, str, str]] = []
    targets = app._target_rows()
    for action_id in sorted(PALETTE_ONLY_ACTION_IDS):
        meta = BUILTIN_ACTIONS.get(action_id)
        if meta is None:
            continue
        if app.view_mode not in meta.view_scope:
            continue
        category = scope_for_action(app, action_id)
        if category == CATEGORY_TARGET and not targets:
            continue
        out.append(
            (
                action_id,
                f"[white]{meta.default_label}[/]",
                category,
            )
        )
    return out
