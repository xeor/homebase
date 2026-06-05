"""Hotbar + custom-binding helpers.

Pure functions that operate on a UIContext snapshot or on a BApp-like
stub (anything exposing ``ctx``, ``custom_hotkeys``, ``actions`` and a
few callbacks). The BApp methods in ``ui/app.py`` are thin delegators
to the functions here so they can be exercised without booting Textual.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...config.prefs import save_hotbar, save_keys
from . import action_items as textual_ui_action_items
from . import dispatch as textual_ui_action_dispatch

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


# ---- binding extraction / persistence -------------------------------


def bindings_from_ctx(ctx: Any) -> list[dict[str, object]]:
    """Build the ``custom_hotkeys`` table from a UIContext snapshot.

    Why: BApp loads three different shapes from the global config —
    ``hotbar`` (positional), ``keys`` (hotkey-bound), and
    ``custom_hotkeys`` (already-normalised legacy entries) — and they
    all collapse into one list internally.
    """
    if not ctx.hotbar and not ctx.keys and ctx.custom_hotkeys:
        return [dict(item) for item in ctx.custom_hotkeys]
    bindings: list[dict[str, object]] = []
    for idx, item in enumerate(ctx.hotbar, start=1):
        action_id = str(item.get("action", "")).strip()
        if not action_id:
            continue
        row: dict[str, object] = {
            "id": f"hotbar_{idx}",
            "target": action_id,
            "hotbar": True,
        }
        label = str(item.get("label", "")).strip()
        if label:
            row["label"] = label
        style_rows = parse_style_rules(item.get("style", []))
        if style_rows:
            row["style"] = style_rows
        bindings.append(row)
    for idx, (hotkey, entry) in enumerate(ctx.keys.items(), start=1):
        action_id = str(entry.get("action", "")).strip()
        if not action_id:
            continue
        row = {
            "id": f"key_{idx}",
            "target": action_id,
            "hotkey": str(hotkey).strip().lower(),
        }
        label = str(entry.get("label", "")).strip()
        if label:
            row["label"] = label
        bindings.append(row)
    return bindings


def save_bindings(base_dir: Path, bindings: list[dict[str, object]]) -> None:
    """Split the unified binding table back into hotbar + keys YAML."""
    hotbar_payload: list[dict[str, object]] = []
    keys_payload: dict[str, dict[str, object]] = {}
    for row in bindings:
        target = str(row.get("target", "")).strip()
        if not target:
            continue
        label = str(row.get("label", "")).strip()
        if bool(row.get("hotbar", False)):
            payload: dict[str, object] = {
                "action": target,
                **({"label": label} if label else {}),
            }
            style_rows = parse_style_rules(row.get("style", []))
            if style_rows:
                payload["style"] = style_rows
            hotbar_payload.append(payload)
        hotkey = str(row.get("hotkey", "")).strip().lower()
        if hotkey:
            keys_payload[hotkey] = {
                "action": target,
                **({"label": label} if label else {}),
            }
    save_hotbar(base_dir, hotbar_payload)
    save_keys(base_dir, keys_payload)


# ---- hotbar index / cycle -------------------------------------------


def hotbar_targets(app: Any) -> list[str]:
    return textual_ui_action_items.hotbar_targets(app)


def hotbar_visible(app: Any) -> bool:
    return bool(hotbar_targets(app))


def normalize_hotbar_index(app: Any) -> None:
    targets = hotbar_targets(app)
    if not targets:
        app.hotbar_selected_index = 0
        return
    app.hotbar_selected_index = max(
        0, min(app.hotbar_selected_index, len(targets) - 1)
    )


def selected_hotbar_target(app: Any) -> str:
    targets = hotbar_targets(app)
    if not targets:
        return ""
    normalize_hotbar_index(app)
    return str(targets[app.hotbar_selected_index])


def cycle_hotbar(app: Any, delta: int) -> bool:
    targets = hotbar_targets(app)
    if not targets:
        return False
    normalize_hotbar_index(app)
    app.hotbar_selected_index = (app.hotbar_selected_index + delta) % len(targets)
    app._mark_state_dirty()
    app._refresh_search_display()
    return True


def toggle_hotbar_target_from_palette(
    app: Any,
    target: str,
    *,
    save_bindings_fn: Callable[[list[dict[str, object]]], None] | None = None,
) -> bool:
    """Add/remove a target on the hotbar from the command palette.

    Why: the palette's star toggle and the settings table both need
    the same add/remove + save semantics, so the logic lives here.
    """
    value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
    if not value:
        return False
    action = app.actions.get(value)
    if action is not None and action.scope != "target":
        app._log(
            f"{value} cannot be on hotbar: only target-scope actions are eligible",
            "warn",
        )
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
        hotbar = not bool(row.get("hotbar", False))
        if hotbar:
            row["hotbar"] = True
        else:
            row.pop("hotbar", None)
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
                "id": f"hotbar_{len(bindings) + 1}",
                "target": value,
                "hotbar": True,
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


def target_is_hotbar(app: Any, target: str) -> bool:
    value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
    if not value:
        return False
    return value in {
        textual_ui_action_dispatch.normalize_action_target(t)
        for t in hotbar_targets(app)
    }


def hotbar_target_label(app: Any, target: str) -> str:
    value = str(target or "").strip()
    if not value:
        return ""
    custom_label = app._hotbar_target_custom_label_map().get(value, "")
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
