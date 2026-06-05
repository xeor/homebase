"""Favorite / custom-binding helpers.

A **Favorite** is a starred target. Its visual surface is derived from
the target prefix and (for action targets) the action's scope:

- target-scope action  → bottom hotbar bar slot
- workspace-scope action → entry in the Favorites list
- ``tab:``/``tab.`` nav target → entry in the Favorites list
- unknown → entry in the Favorites list

Pure functions that operate on a UIContext snapshot or on a BApp-like
stub (anything exposing ``ctx``, ``custom_hotkeys``, ``actions`` and a
few callbacks). The BApp methods in ``ui/app.py`` are thin delegators
to the functions here so they can be exercised without booting Textual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...config.prefs import save_favorites
from . import action_items as textual_ui_action_items
from . import dispatch as textual_ui_action_dispatch

SURFACE_HOTBAR = "hotbar"
SURFACE_GLOBAL = "global"
SURFACE_NAV = "nav"


# ---- style rules ----------------------------------------------------


def parse_style_rule(raw_rule: object) -> dict[str, object] | None:
    if not isinstance(raw_rule, dict):
        return None
    bg_color = str(raw_rule.get("bg_color", "")).strip()
    fg_color = str(raw_rule.get("fg_color", "")).strip()
    when = str(raw_rule.get("when", "")).strip()
    bold = bool(raw_rule.get("bold", False))
    underline = bool(raw_rule.get("underline", False))
    italic = bool(raw_rule.get("italic", False))
    if not when:
        return None
    if not bg_color and not fg_color and not (bold or underline or italic):
        return None
    rule: dict[str, object] = {"when": when}
    if bg_color:
        rule["bg_color"] = bg_color
    if fg_color:
        rule["fg_color"] = fg_color
    if bold:
        rule["bold"] = True
    if underline:
        rule["underline"] = True
    if italic:
        rule["italic"] = True
    return rule


def parse_style_rules(raw_style: object) -> list[dict[str, object]]:
    if not isinstance(raw_style, list) or not raw_style:
        return []
    out: list[dict[str, object]] = []
    for raw_rule in raw_style:
        rule = parse_style_rule(raw_rule)
        if rule is not None:
            out.append(rule)
    return out


# ---- surface derivation ---------------------------------------------


def favorite_surface(target: str, actions: dict[str, Any]) -> str:
    """Return which UI surface a favorite renders on.

    Why: a single ``favorite: true`` flag drives three different
    placements (bottom hotbar bar, Favorites list, nav jump entry).
    The target prefix + action scope decide.
    """
    value = str(target or "").strip()
    if not value:
        return SURFACE_NAV
    if value.startswith("tab:") or value.startswith("tab."):
        return SURFACE_NAV
    action_id = value.split(":", 1)[1] if value.startswith("action:") else value
    action = actions.get(action_id)
    if action is not None and getattr(action, "scope", "") == "target":
        return SURFACE_HOTBAR
    if action is not None and getattr(action, "scope", "") == "workspace":
        return SURFACE_GLOBAL
    return SURFACE_NAV


# ---- binding extraction / persistence -------------------------------


def bindings_from_ctx(ctx: Any) -> list[dict[str, object]]:
    """Return the unified favorites table from a UIContext snapshot."""
    return [dict(item) for item in getattr(ctx, "favorites", []) or []]


def save_bindings(base_dir: Path, bindings: list[dict[str, object]]) -> None:
    """Persist the unified favorites table to the global config YAML."""
    save_favorites(base_dir, bindings)


# ---- hotbar bar (slot) index / cycle --------------------------------


def hotbar_slot_targets(app: Any) -> list[str]:
    """Targets that render on the bottom hotbar bar.

    Filters favorites to those whose surface is ``hotbar``
    (i.e. target-scope action favorites only).
    """
    return textual_ui_action_items.hotbar_slot_targets(app)


def hotbar_visible(app: Any) -> bool:
    return bool(hotbar_slot_targets(app))


def normalize_hotbar_index(app: Any) -> None:
    targets = hotbar_slot_targets(app)
    if not targets:
        app.hotbar_selected_index = 0
        return
    app.hotbar_selected_index = max(
        0, min(app.hotbar_selected_index, len(targets) - 1)
    )


def selected_hotbar_slot_target(app: Any) -> str:
    targets = hotbar_slot_targets(app)
    if not targets:
        return ""
    normalize_hotbar_index(app)
    return str(targets[app.hotbar_selected_index])


def cycle_hotbar_slot(app: Any, delta: int) -> bool:
    targets = hotbar_slot_targets(app)
    if not targets:
        return False
    normalize_hotbar_index(app)
    app.hotbar_selected_index = (app.hotbar_selected_index + delta) % len(targets)
    app._mark_state_dirty()
    app._refresh_search_display()
    return True


def favorite_targets(app: Any) -> list[str]:
    """All favorited targets, regardless of surface, in stored order."""
    out: list[str] = []
    seen: set[str] = set()
    for binding in getattr(app, "custom_hotkeys", []) or []:
        if not bool(binding.get("favorite", False)):
            continue
        target = str(binding.get("target", "")).strip()
        if not target or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def toggle_favorite_target(
    app: Any,
    target: str,
    *,
    save_bindings_fn: Callable[[list[dict[str, object]]], None] | None = None,
) -> bool:
    """Add/remove a target from the favorites list.

    Accepts any target — action id, ``action:<id>``, ``tab:...`` — and
    derives the rendering surface from prefix + scope. There is no
    eligibility gate; callers are responsible for passing a valid
    target.
    """
    value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
    if not value:
        return False
    save_fn = save_bindings_fn or (lambda b: save_bindings(app.base_dir, b))
    bindings: list[dict[str, object]] = [dict(row) for row in app.custom_hotkeys]
    found_idx = -1
    for i, row in enumerate(bindings):
        if str(row.get("target", "")).strip() == value:
            found_idx = i
            break
    if found_idx >= 0:
        row = dict(bindings[found_idx])
        favorite = not bool(row.get("favorite", False))
        if favorite:
            row["favorite"] = True
        else:
            row.pop("favorite", None)
            if not str(row.get("hotkey", "")).strip():
                bindings.pop(found_idx)
                try:
                    save_fn(bindings)
                    app.custom_hotkeys = bindings
                    normalize_hotbar_index(app)
                    app._mark_state_dirty()
                    app._refresh_search_display()
                    return True
                except (OSError, TypeError, ValueError) as exc:
                    app._show_runtime_error("save bindings", exc)
                    return False
        bindings[found_idx] = row
    else:
        bindings.append(
            {
                "id": f"fav_{len(bindings) + 1}",
                "target": value,
                "favorite": True,
            }
        )
    try:
        save_fn(bindings)
        app.custom_hotkeys = bindings
    except (OSError, TypeError, ValueError) as exc:
        app._show_runtime_error("save bindings", exc)
        return False
    normalize_hotbar_index(app)
    app._mark_state_dirty()
    app._refresh_search_display()
    return True


def target_is_favorite(app: Any, target: str) -> bool:
    value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
    if not value:
        return False
    return value in {
        textual_ui_action_dispatch.normalize_action_target(t)
        for t in favorite_targets(app)
    }


def favorite_target_label(app: Any, target: str) -> str:
    value = str(target or "").strip()
    if not value:
        return ""
    custom_label = app._favorite_target_custom_label_map().get(value, "")
    if custom_label:
        return custom_label
    if value.startswith("tab:"):
        return value.split(":", 1)[1]
    if value.startswith("tab."):
        return value.split(".", 1)[1]
    action_id = value.split(":", 1)[1] if value.startswith("action:") else value
    for aid, label in app._valid_action_items():
        if aid == action_id:
            return app._label_plain(label)
    if action_id in app.actions:
        return app.actions[action_id].label
    return value
