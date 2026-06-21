from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from ..core.constants import (
    CACHE_PROFILE_CONFIG,
    DEFAULT_ARCHIVE_TZ_NAME,
    NAMED_FILTERS,
    NEW_PROJECT_DEFAULTS,
    NOTES_CONFIG,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    PREVIEW_ENTRIES_LIMIT_MAX,
    PREVIEW_ENTRIES_LIMIT_MIN,
    RAYCAST_CONFIG,
    RECONCILE_CONFIG,
    SAVED_FILTER_QUERIES,
    SIDE_CHILD_TABS,
    SIDE_TAB_EVENTS_DEFAULT,
    SIDE_TAB_OVERVIEW_DEFAULT,
    SIDE_TAB_SELECTED_DEFAULT,
    SIDE_TAB_TABLE_DEFAULT,
    SIDE_TOP_TABS,
    SORT_MODE_SPECS,
    STATE_KEY_SIDE_INFO,
    STATE_KEY_SIDE_MAIN,
    STATE_KEY_SIDE_SELECTED,
    STATE_KEY_SIDE_SETTINGS,
    TABLE_BEHAVIOR_CONFIG,
    TABLE_COLUMN_CATALOG,
    TABLE_COLUMN_VIEWS,
    TABLE_DATE_COLOR_COLUMNS,
    TABLE_SIDE_WIDTH_PRESETS,
    WIP_OPEN_SYMBOL_MAP,
)
from ..core.models import Action, PostCommandOption
from ..core.utils import normalize_filter_expression
from . import cache_profile as cache_profile_config
from . import open_mode as open_mode_config
from . import store as config_store
from . import workspace as workspace_settings
from .store import load_global_config_dict, save_global_config_dict

_FILTER_TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\||[^\s()|]+", re.IGNORECASE)


def load_post_command_options(base_dir: Path) -> list[PostCommandOption]:
    raw = load_global_config_dict(base_dir)

    items: list[object] = []
    if isinstance(raw, dict):
        new_conf = raw.get("new", {})
        if isinstance(new_conf, dict):
            val = new_conf.get("post-commands", [])
            if isinstance(val, list):
                items = val

    out: list[PostCommandOption] = []
    used: set[str] = set()

    def alloc_id(seed: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "_", seed.lower()).strip("_") or "cmd"
        key = base
        i = 2
        while key in used:
            key = f"{base}_{i}"
            i += 1
        used.add(key)
        return key

    for item in items:
        if isinstance(item, str):
            command = item.strip()
            if not command:
                continue
            key = alloc_id(command)
            out.append(PostCommandOption(key=key, label=command, command=command))
            continue
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        command = str(item.get("command", "")).strip()
        if not command:
            continue
        seed = label or command
        key = alloc_id(seed)
        label = label or command
        out.append(PostCommandOption(key=key, label=label, command=command))

    return out


def load_archive_timezone_name(base_dir: Path) -> str:
    raw = load_global_config_dict(base_dir)
    archive_conf = raw.get("archive", {})
    if not isinstance(archive_conf, dict):
        return DEFAULT_ARCHIVE_TZ_NAME
    name = str(archive_conf.get("timezone", DEFAULT_ARCHIVE_TZ_NAME)).strip()
    return name or DEFAULT_ARCHIVE_TZ_NAME


def load_wip_symbol_map(base_dir: Path) -> dict[str, int]:
    raw = load_global_config_dict(base_dir)
    wip_conf = raw.get("wip", {})
    if not isinstance(wip_conf, dict):
        return dict(WIP_OPEN_SYMBOL_MAP)
    mapping = wip_conf.get("hotkeys", {})
    if not isinstance(mapping, dict):
        return dict(WIP_OPEN_SYMBOL_MAP)

    out: dict[str, int] = {}

    for idx in range(1, 10):
        raw_value = mapping.get(str(idx), mapping.get(idx, None))
        if raw_value is None:
            continue
        values: list[str]
        if isinstance(raw_value, list):
            values = [str(v) for v in raw_value if str(v)]
        else:
            values = [str(raw_value)]
        for token in values:
            token = token.strip()
            if token:
                out[token] = idx

    return out or dict(WIP_OPEN_SYMBOL_MAP)


def load_suffixes(base_dir: Path) -> list[str]:
    return workspace_settings.load_suffixes(
        load_global_config_dict(base_dir),
        default_suffixes=["tmp", "fork"],
    )


def load_file_view_exclude_patterns(base_dir: Path) -> list[str]:
    return workspace_settings.load_file_view_exclude_patterns(
        load_global_config_dict(base_dir)
    )


def load_actions(base_dir: Path, *, builtins) -> dict[str, Action]:
    return workspace_settings.load_actions(
        load_global_config_dict(base_dir),
        builtins=builtins,
    )


def load_favorites(base_dir: Path, *, actions) -> list[dict[str, object]]:
    return workspace_settings.load_favorites(
        load_global_config_dict(base_dir), actions=actions
    )


def _serialize_style_rule(raw_rule: object) -> dict[str, str] | None:
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
    rule: dict[str, str] = {"when": when}
    if bg_color:
        rule["bg_color"] = bg_color
    if fg_color:
        rule["fg_color"] = fg_color
    if bold:
        rule["bold"] = "1"
    if underline:
        rule["underline"] = "1"
    if italic:
        rule["italic"] = "1"
    return rule


def _serialize_favorite_row(idx: int, row: object) -> dict[str, object] | None:
    if not isinstance(row, dict):
        return None
    target = str(row.get("target", "")).strip()
    if not target:
        return None
    payload: dict[str, object] = {
        "id": str(row.get("id", "")).strip() or f"fav_{idx}",
        "target": target,
    }
    if bool(row.get("favorite", False)):
        payload["favorite"] = True
    hotkey = str(row.get("hotkey", "")).strip().lower()
    if hotkey:
        payload["hotkey"] = hotkey
    label = str(row.get("label", "")).strip()
    if label:
        payload["label"] = label
    style = row.get("style", [])
    style_out: list[dict[str, str]] = []
    if isinstance(style, list):
        for raw_rule in style:
            rule = _serialize_style_rule(raw_rule)
            if rule is not None:
                style_out.append(rule)
    if style_out:
        payload["style"] = style_out
    return payload


def save_favorites(base_dir: Path, favorites: Sequence[object]) -> None:
    """Persist the unified favorites table. Drops any legacy keys."""
    data = load_global_config_dict(base_dir)
    out: list[dict[str, object]] = []
    for idx, item in enumerate(favorites, start=1):
        serialized = _serialize_favorite_row(idx, item)
        if serialized is not None:
            out.append(serialized)
    data["favorites"] = out
    save_global_config_dict(base_dir, data)


def load_open_mode_config(base_dir: Path) -> dict[str, str]:
    data = load_global_config_dict(base_dir)
    return open_mode_config.load_open_mode_config(
        data,
        default_profile=str(OPEN_MODE_CONFIG["profile"]),
        known_profiles={str(p.get("id", "")) for p in OPEN_MODE_PROFILES},
    )


def load_notes_config(base_dir: Path) -> dict[str, object]:
    return workspace_settings.load_notes_config(
        load_global_config_dict(base_dir),
        defaults=NOTES_CONFIG,
    )


def load_raycast_config(base_dir: Path) -> dict[str, object]:
    return workspace_settings.load_raycast_config(
        load_global_config_dict(base_dir),
        defaults=RAYCAST_CONFIG,
    )


def load_reconcile_config(base_dir: Path) -> dict[str, dict[str, object]]:
    return workspace_settings.load_reconcile_config(
        load_global_config_dict(base_dir),
        defaults=RECONCILE_CONFIG,
        default_cache_profiles=CACHE_PROFILE_CONFIG,
    )


def load_cache_profile_table(base_dir: Path) -> dict[str, dict[str, dict[str, object]]]:
    raw = load_global_config_dict(base_dir)
    merged = dict(raw) if isinstance(raw, dict) else {}
    merged_profiles = {
        "all": dict(CACHE_PROFILE_CONFIG.get("all", {})),
        "active": dict(CACHE_PROFILE_CONFIG.get("active", {})),
        "archive": dict(CACHE_PROFILE_CONFIG.get("archive", {})),
    }
    raw_profiles = merged.get("cache_profile", {})
    if isinstance(raw_profiles, dict):
        for scope in ("all", "active", "archive"):
            scope_raw = raw_profiles.get(scope, {})
            if not isinstance(scope_raw, dict):
                continue
            cur = merged_profiles.get(scope, {})
            cur.update(scope_raw)
            merged_profiles[scope] = cur
    merged["cache_profile"] = merged_profiles
    return cache_profile_config.load_cache_profile_table(merged)


def nested_discovery_enabled(base_dir: Path) -> bool:
    return workspace_settings.nested_discovery_enabled(load_global_config_dict(base_dir))


def set_nested_discovery_enabled(base_dir: Path, enabled: bool) -> None:
    save_global_config_dict(
        base_dir,
        workspace_settings.set_nested_discovery_enabled(
            load_global_config_dict(base_dir),
            enabled=enabled,
        ),
    )


def save_open_mode_config(base_dir: Path, conf: dict[str, str]) -> None:
    data = load_global_config_dict(base_dir)
    updated = open_mode_config.save_open_mode_config(
        data,
        conf,
        default_profile=str(OPEN_MODE_CONFIG["profile"]),
        known_profiles={str(p.get("id", "")) for p in OPEN_MODE_PROFILES},
    )
    save_global_config_dict(base_dir, updated)


def load_new_project_defaults(base_dir: Path) -> dict[str, object]:
    data = load_global_config_dict(base_dir)
    raw = data.get("new_project", {}) if isinstance(data, dict) else {}
    out = dict(NEW_PROJECT_DEFAULTS)
    if not isinstance(raw, dict):
        return out

    name_options_raw = raw.get("name_options", [])
    if isinstance(name_options_raw, list):
        out["name_options"] = [
            str(v).strip() for v in name_options_raw if str(v).strip()
        ]

    template_raw = raw.get("template")
    if template_raw is None:
        out["template"] = None
    else:
        template = str(template_raw).strip()
        out["template"] = template or None

    post_commands_raw = raw.get("post_commands", [])
    if isinstance(post_commands_raw, list):
        out["post_commands"] = [
            str(v).strip() for v in post_commands_raw if str(v).strip()
        ]

    tags_raw = raw.get("tags", [])
    if isinstance(tags_raw, list):
        out["tags"] = [str(v).strip() for v in tags_raw if str(v).strip()]

    after_create = str(raw.get("after_create", "open")).strip() or "open"
    out["after_create"] = after_create
    return out


def save_new_project_defaults(base_dir: Path, conf: dict[str, object]) -> None:
    data = load_global_config_dict(base_dir)
    raw_name_options = conf.get("name_options", [])
    raw_post_commands = conf.get("post_commands", [])
    raw_tags = conf.get("tags", [])

    name_options = (
        [str(v).strip() for v in raw_name_options if str(v).strip()]
        if isinstance(raw_name_options, list)
        else []
    )
    post_commands = (
        [str(v).strip() for v in raw_post_commands if str(v).strip()]
        if isinstance(raw_post_commands, list)
        else []
    )
    tags = (
        [str(v).strip() for v in raw_tags if str(v).strip()]
        if isinstance(raw_tags, list)
        else []
    )

    template_raw = conf.get("template")
    template: str | None
    if template_raw is None:
        template = None
    else:
        t = str(template_raw).strip()
        template = t or None

    after_create = str(conf.get("after_create", "open")).strip() or "open"

    data["new_project"] = {
        "name_options": sorted(set(name_options)),
        "template": template,
        "post_commands": sorted(set(post_commands)),
        "tags": sorted(set(tags)),
        "after_create": after_create,
    }
    save_global_config_dict(base_dir, data)


def _table_catalog_for_view(view_mode: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for col in TABLE_COLUMN_CATALOG:
        raw_views = col.get("views", [])
        views_iter = raw_views if isinstance(raw_views, (list, tuple)) else ()
        views = [str(v) for v in views_iter if str(v).strip()]
        if not views:
            views = list(TABLE_COLUMN_VIEWS)
        if view_mode in views:
            entry = dict(col)
            entry["views"] = views
            out.append(entry)
    return out


def _merge_table_columns_for_view(
    view_mode: str, raw_cols: list[dict[str, object]]
) -> list[dict[str, object]]:
    catalog = _table_catalog_for_view(view_mode)
    by_id: dict[str, dict[str, object]] = {str(c.get("id", "")): c for c in catalog}
    seen: set[str] = set()
    out: list[dict[str, object]] = []

    for raw in raw_cols:
        cid = str(raw.get("id", "")).strip()
        if not cid or cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        base = dict(by_id[cid])
        enabled = bool(raw.get("enabled", base.get("default", True)))
        base["enabled"] = enabled
        default_width = _as_int(base.get("width", 12), 12)
        width = _as_int(raw.get("width", default_width), default_width)
        base["width"] = max(1, width)
        out.append(base)

    for col in catalog:
        cid = str(col.get("id", ""))
        if cid in seen:
            continue
        entry = dict(col)
        entry["enabled"] = bool(col.get("default", True))
        out.append(entry)

    return out


def load_table_columns_config(base_dir: Path) -> dict[str, list[dict[str, object]]]:
    data = load_global_config_dict(base_dir)
    raw = data.get("table", {}) if isinstance(data, dict) else {}
    columns_raw = raw.get("columns", {}) if isinstance(raw, dict) else {}
    if not isinstance(columns_raw, dict):
        columns_raw = {}

    out: dict[str, list[dict[str, object]]] = {}
    for view in TABLE_COLUMN_VIEWS:
        view_raw = columns_raw.get(view, [])
        view_list = view_raw if isinstance(view_raw, list) else []
        out[view] = _merge_table_columns_for_view(view, list(view_list))
    return out


def save_table_columns_config(
    base_dir: Path, columns_by_view: dict[str, list[dict[str, object]]]
) -> None:
    data = load_global_config_dict(base_dir)
    table = data.get("table", {}) if isinstance(data, dict) else {}
    if not isinstance(table, dict):
        table = {}

    serialized: dict[str, list[dict[str, object]]] = {}
    for view in TABLE_COLUMN_VIEWS:
        cols = columns_by_view.get(view, [])
        view_out: list[dict[str, object]] = []
        for col in cols:
            cid = str(col.get("id", "")).strip()
            if not cid:
                continue
            view_out.append(
                {
                    "id": cid,
                    "enabled": bool(col.get("enabled", True)),
                    "width": max(1, _as_int(col.get("width", 12), 12)),
                }
            )
        serialized[view] = view_out

    table["columns"] = serialized
    data["table"] = table
    save_global_config_dict(base_dir, data)


def _normalize_side_width_pct(value: object) -> int:
    default = _as_int(TABLE_BEHAVIOR_CONFIG["side_width_pct"], 33)
    n = _as_int(value, default)
    presets = list(TABLE_SIDE_WIDTH_PRESETS) or [n]
    return min(presets, key=lambda p: abs(p - n))


def _normalize_preview_entries_limit(value: object) -> int:
    default = _as_int(TABLE_BEHAVIOR_CONFIG["preview_entries_limit"], 8)
    n = _as_int(value, default)
    return max(PREVIEW_ENTRIES_LIMIT_MIN, min(PREVIEW_ENTRIES_LIMIT_MAX, n))


def load_table_behavior_config(base_dir: Path) -> dict[str, object]:
    data = load_global_config_dict(base_dir)
    raw = data.get("table", {}) if isinstance(data, dict) else {}
    behavior_raw = raw.get("behavior", {}) if isinstance(raw, dict) else {}
    if not isinstance(behavior_raw, dict):
        behavior_raw = {}

    out = dict(TABLE_BEHAVIOR_CONFIG)
    if "pin_wip_top" in behavior_raw:
        out["pin_wip_top"] = bool(behavior_raw.get("pin_wip_top"))
    if "side_width_pct" in behavior_raw:
        out["side_width_pct"] = _normalize_side_width_pct(behavior_raw.get("side_width_pct"))
    if "preview_entries_limit" in behavior_raw:
        out["preview_entries_limit"] = _normalize_preview_entries_limit(
            behavior_raw.get("preview_entries_limit")
        )
    return out


def save_table_behavior_config(base_dir: Path, conf: dict[str, object]) -> None:
    data = load_global_config_dict(base_dir)
    table = data.get("table", {}) if isinstance(data, dict) else {}
    if not isinstance(table, dict):
        table = {}

    behavior = {
        "pin_wip_top": bool(conf.get("pin_wip_top", False)),
        "side_width_pct": _normalize_side_width_pct(conf.get("side_width_pct")),
        "preview_entries_limit": _normalize_preview_entries_limit(
            conf.get("preview_entries_limit")
        ),
    }
    table["behavior"] = behavior
    data["table"] = table
    save_global_config_dict(base_dir, data)


def save_archive_timezone_name(base_dir: Path, name: str) -> None:
    cleaned = str(name).strip()
    if not cleaned:
        cleaned = DEFAULT_ARCHIVE_TZ_NAME
    data = load_global_config_dict(base_dir)
    archive = data.get("archive", {})
    if not isinstance(archive, dict):
        archive = {}
    archive["timezone"] = cleaned
    data["archive"] = archive
    save_global_config_dict(base_dir, data)


_HEX_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return default


def _extract_date_ranges_raw(table_raw: dict) -> object:
    columns_style_raw = table_raw.get("columns_style", {})
    if isinstance(columns_style_raw, dict):
        return columns_style_raw.get(
            "date",
            table_raw.get("date_columns", table_raw.get("date_color_ranges", {})),
        )
    return table_raw.get("date_columns", table_raw.get("date_color_ranges", {}))


def _parse_numeric_scale(row: dict) -> list[dict[str, object]] | None:
    stops: list[dict[str, object]] = []
    for key, value in row.items():
        try:
            days = max(0.0, float(key))
        except (TypeError, ValueError):
            return None
        color = str(value).strip()
        if not _HEX_COLOR_PATTERN.fullmatch(color):
            return None
        stops.append({"days": days, "color": color})
    if not stops:
        return None
    return sorted(stops, key=lambda item: _as_float(item.get("days", 0.0), 0.0))


def _parse_scale_dict(scale_raw: object) -> list[dict[str, object]]:
    if not isinstance(scale_raw, dict):
        return []
    stops: list[dict[str, object]] = []
    for key, value in scale_raw.items():
        try:
            days = max(0.0, float(key))
        except (TypeError, ValueError):
            continue
        color = str(value).strip()
        if not _HEX_COLOR_PATTERN.fullmatch(color):
            continue
        stops.append({"days": days, "color": color})
    return sorted(stops, key=lambda item: _as_float(item.get("days", 0.0), 0.0))


def _parse_from_to_color(row: dict) -> list[dict[str, object]] | None:
    from_color = str(
        row.get("from_color", row.get("newer_color", row.get("new_color", "")))
    ).strip()
    to_color = str(
        row.get("to_color", row.get("older_color", row.get("old_color", "")))
    ).strip()
    try:
        range_days = max(1.0, float(row.get("range_days", 365)))
    except (TypeError, ValueError):
        return None
    if not _HEX_COLOR_PATTERN.fullmatch(from_color):
        return None
    if not _HEX_COLOR_PATTERN.fullmatch(to_color):
        return None
    return [
        {"days": 0.0, "color": from_color},
        {"days": range_days, "color": to_color},
    ]


def _parse_column_stops(row: object) -> list[dict[str, object]] | None:
    if not isinstance(row, dict):
        return None
    stops = _parse_numeric_scale(row)
    if stops:
        return stops
    stops = _parse_scale_dict(row.get("scale"))
    if stops:
        return stops
    return _parse_from_to_color(row)


def load_table_date_column_styles(base_dir: Path) -> dict[str, dict[str, dict[str, object]]]:
    data = load_global_config_dict(base_dir)
    raw = data.get("table", {}) if isinstance(data, dict) else {}
    table_raw = raw if isinstance(raw, dict) else {}
    ranges_raw = _extract_date_ranges_raw(table_raw)
    if not isinstance(ranges_raw, dict):
        return {"all": {}, "active": {}, "archive": {}}
    out: dict[str, dict[str, dict[str, object]]] = {
        "all": {},
        "active": {},
        "archive": {},
    }
    for view in ("all", "active", "archive"):
        view_raw = ranges_raw.get(view, {})
        if not isinstance(view_raw, dict):
            continue
        for cid in TABLE_DATE_COLOR_COLUMNS:
            stops = _parse_column_stops(view_raw.get(cid, {}))
            if stops:
                out[view][cid] = {"stops": stops}
    return out


def _sort_mode_ids() -> set[str]:
    return {str(spec.get("id", "")).strip() for spec in SORT_MODE_SPECS if spec.get("id")}


def load_ui_state(base_dir: Path) -> dict[str, object]:
    return config_store.load_ui_state_from_data(
        load_global_config_dict(base_dir),
        state_key_side_main=STATE_KEY_SIDE_MAIN,
        state_key_side_selected=STATE_KEY_SIDE_SELECTED,
        state_key_side_info=STATE_KEY_SIDE_INFO,
        state_key_side_settings=STATE_KEY_SIDE_SETTINGS,
        state_key_hotbar_slot_index="hotbar_selected_index",
        side_tab_selected_default=SIDE_TAB_SELECTED_DEFAULT,
        side_tab_overview_default=SIDE_TAB_OVERVIEW_DEFAULT,
        side_tab_events_default=SIDE_TAB_EVENTS_DEFAULT,
        side_tab_table_default=SIDE_TAB_TABLE_DEFAULT,
        side_top_tabs=SIDE_TOP_TABS,
        side_child_tabs=SIDE_CHILD_TABS,
        sort_mode_ids=_sort_mode_ids(),
    )


def save_ui_state(base_dir: Path, state: dict[str, object]) -> None:
    data = load_global_config_dict(base_dir)
    out = config_store.save_ui_state_to_data(
        data,
        state,
        state_key_side_main=STATE_KEY_SIDE_MAIN,
        state_key_side_selected=STATE_KEY_SIDE_SELECTED,
        state_key_side_info=STATE_KEY_SIDE_INFO,
        state_key_side_settings=STATE_KEY_SIDE_SETTINGS,
        state_key_hotbar_slot_index="hotbar_selected_index",
        side_tab_selected_default=SIDE_TAB_SELECTED_DEFAULT,
        side_tab_overview_default=SIDE_TAB_OVERVIEW_DEFAULT,
        side_tab_events_default=SIDE_TAB_EVENTS_DEFAULT,
        side_tab_table_default=SIDE_TAB_TABLE_DEFAULT,
    )
    save_global_config_dict(base_dir, out)


def load_saved_filter_queries(base_dir: Path) -> tuple[dict[str, str], list[str]]:
    named, saved = config_store.load_saved_filter_queries_from_data(
        load_global_config_dict(base_dir)
    )
    NAMED_FILTERS.clear()
    NAMED_FILTERS.update(named)
    SAVED_FILTER_QUERIES.clear()
    SAVED_FILTER_QUERIES.extend(saved)
    return named, saved


def save_filter_query(base_dir: Path, expr: str, name: str | None = None) -> None:
    data = load_global_config_dict(base_dir)
    out, named, saved = config_store.save_filter_query_to_data(data, expr, name=name)
    save_global_config_dict(base_dir, out)
    NAMED_FILTERS.clear()
    NAMED_FILTERS.update(named)
    SAVED_FILTER_QUERIES.clear()
    SAVED_FILTER_QUERIES.extend(saved)


def delete_named_filter(base_dir: Path, name: str) -> bool:
    data = load_global_config_dict(base_dir)
    out, removed, named = config_store.delete_named_filter_from_data(data, name)
    if removed:
        save_global_config_dict(base_dir, out)
        NAMED_FILTERS.clear()
        NAMED_FILTERS.update(named)
    return removed


def resolve_named_filters_for_display(expr: str, depth: int = 0) -> str:
    return config_store.resolve_named_filters_for_display(
        expr,
        named_filters=NAMED_FILTERS,
        token_finder=_FILTER_TOKEN_RE,
        depth=depth,
    )


def resolve_filter_expression(base_dir: Path, expr: str) -> tuple[str, str | None]:
    text = expr.strip()
    if not text:
        return "", None
    if not NAMED_FILTERS:
        load_saved_filter_queries(base_dir)
    return _expand_named_tokens(text, depth=0)


def _expand_named_tokens(text: str, depth: int) -> tuple[str, str | None]:
    if depth > 8:
        return text, "named filter recursion exceeded"
    tokens = _FILTER_TOKEN_RE.findall(text)
    if not tokens:
        return text, None
    out_parts: list[str] = []
    for token in tokens:
        if token.startswith("@") and len(token) > 1:
            name = token[1:].strip()
            if not name:
                out_parts.append(token)
                continue
            inner = NAMED_FILTERS.get(name)
            if inner is None:
                return text, f"named filter not found: {name}"
            inner_resolved, err = _expand_named_tokens(inner, depth + 1)
            if err is not None:
                return text, err
            out_parts.append(f"({inner_resolved})")
        else:
            out_parts.append(token)
    expanded = " ".join(out_parts)
    return normalize_filter_expression(expanded, token_re=_FILTER_TOKEN_RE), None
