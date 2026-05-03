from __future__ import annotations

import re
from pathlib import Path

from ..core.constants import (
    CACHE_PROFILE_CONFIG,
    DEFAULT_ARCHIVE_TZ_NAME,
    NAMED_FILTERS,
    NEW_PROJECT_DEFAULTS,
    NOTES_CONFIG,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
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
    TABLE_SIDE_WIDTH_PRESETS,
    WIP_OPEN_SYMBOL_MAP,
)
from ..core.models import PostCommandOption
from ..filter import engine as filter_engine
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
    if not isinstance(raw, dict):
        return DEFAULT_ARCHIVE_TZ_NAME
    archive_conf = raw.get("archive", {})
    if not isinstance(archive_conf, dict):
        return DEFAULT_ARCHIVE_TZ_NAME
    name = str(archive_conf.get("timezone", DEFAULT_ARCHIVE_TZ_NAME)).strip()
    return name or DEFAULT_ARCHIVE_TZ_NAME


def load_wip_symbol_map(base_dir: Path) -> dict[str, int]:
    raw = load_global_config_dict(base_dir)
    if not isinstance(raw, dict):
        return dict(WIP_OPEN_SYMBOL_MAP)
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


def load_custom_actions(base_dir: Path) -> list[dict[str, str]]:
    return workspace_settings.load_custom_actions(load_global_config_dict(base_dir))


def load_open_mode_config(base_dir: Path) -> dict[str, str]:
    data = load_global_config_dict(base_dir)
    return open_mode_config.load_open_mode_config(
        data,
        default_profile=str(OPEN_MODE_CONFIG["profile"]),
        known_profiles={str(p.get("id", "")) for p in OPEN_MODE_PROFILES},
    )


def load_notes_config(base_dir: Path) -> dict[str, str]:
    return workspace_settings.load_notes_config(
        load_global_config_dict(base_dir),
        defaults=NOTES_CONFIG,
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
        views = [str(v) for v in col.get("views", []) if str(v).strip()]
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
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("id", "")).strip()
        if not cid or cid not in by_id or cid in seen:
            continue
        seen.add(cid)
        base = dict(by_id[cid])
        enabled = bool(raw.get("enabled", base.get("default", True)))
        base["enabled"] = enabled
        try:
            width = int(raw.get("width", base.get("width", 12)))
            base["width"] = max(1, width)
        except (TypeError, ValueError):
            pass
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
            if not isinstance(col, dict):
                continue
            cid = str(col.get("id", "")).strip()
            if not cid:
                continue
            view_out.append(
                {
                    "id": cid,
                    "enabled": bool(col.get("enabled", True)),
                    "width": max(1, int(col.get("width", 12))),
                }
            )
        serialized[view] = view_out

    table["columns"] = serialized
    data["table"] = table
    save_global_config_dict(base_dir, data)


def _normalize_side_width_pct(value: object) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = int(TABLE_BEHAVIOR_CONFIG["side_width_pct"])
    presets = list(TABLE_SIDE_WIDTH_PRESETS) or [n]
    return min(presets, key=lambda p: abs(p - n))


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
    return out


def save_table_behavior_config(base_dir: Path, conf: dict[str, object]) -> None:
    data = load_global_config_dict(base_dir)
    table = data.get("table", {}) if isinstance(data, dict) else {}
    if not isinstance(table, dict):
        table = {}

    behavior = {
        "pin_wip_top": bool(conf.get("pin_wip_top", False)),
        "side_width_pct": _normalize_side_width_pct(conf.get("side_width_pct")),
    }
    table["behavior"] = behavior
    data["table"] = table
    save_global_config_dict(base_dir, data)


def _sort_mode_ids() -> set[str]:
    return {str(spec.get("id", "")).strip() for spec in SORT_MODE_SPECS if spec.get("id")}


def load_ui_state(base_dir: Path) -> dict[str, object]:
    return config_store.load_ui_state_from_data(
        load_global_config_dict(base_dir),
        state_key_side_main=STATE_KEY_SIDE_MAIN,
        state_key_side_selected=STATE_KEY_SIDE_SELECTED,
        state_key_side_info=STATE_KEY_SIDE_INFO,
        state_key_side_settings=STATE_KEY_SIDE_SETTINGS,
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
    return filter_engine.normalize_filter_expression(expanded, token_re=_FILTER_TOKEN_RE), None
