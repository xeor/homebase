from __future__ import annotations

from pathlib import Path
from re import Pattern

import yaml

from ..core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME

_GLOBAL_CONFIG_BASE: Path | None = None
_GLOBAL_CONFIG_DATA: dict[str, object] | None = None


def clear_global_config_cache(base_dir: Path | None = None) -> None:
    global _GLOBAL_CONFIG_BASE, _GLOBAL_CONFIG_DATA
    if base_dir is None:
        _GLOBAL_CONFIG_BASE = None
        _GLOBAL_CONFIG_DATA = None
        return
    try:
        base_res = base_dir.resolve()
    except (OSError, RuntimeError, ValueError):
        base_res = base_dir
    if _GLOBAL_CONFIG_BASE == base_res:
        _GLOBAL_CONFIG_BASE = None
        _GLOBAL_CONFIG_DATA = None


def load_global_config_dict(base_dir: Path) -> dict[str, object]:
    global _GLOBAL_CONFIG_BASE, _GLOBAL_CONFIG_DATA

    base_res = base_dir.resolve()
    if _GLOBAL_CONFIG_BASE is not None and _GLOBAL_CONFIG_DATA is not None:
        if _GLOBAL_CONFIG_BASE == base_res:
            return _GLOBAL_CONFIG_DATA

    config = base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    if not config.is_file():
        _GLOBAL_CONFIG_BASE = base_res
        _GLOBAL_CONFIG_DATA = {}
        return {}

    try:
        raw = yaml.safe_load(config.read_text())
    except (OSError, yaml.YAMLError, TypeError, ValueError):
        _GLOBAL_CONFIG_BASE = base_res
        _GLOBAL_CONFIG_DATA = {}
        return {}

    out = raw if isinstance(raw, dict) else {}
    _GLOBAL_CONFIG_BASE = base_res
    _GLOBAL_CONFIG_DATA = out
    return out


def save_global_config_dict(base_dir: Path, data: dict[str, object]) -> None:
    global _GLOBAL_CONFIG_BASE, _GLOBAL_CONFIG_DATA

    config = base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    _GLOBAL_CONFIG_BASE = base_dir.resolve()
    _GLOBAL_CONFIG_DATA = data


def load_saved_filter_queries_from_data(raw: object) -> tuple[dict[str, str], list[str]]:
    if not isinstance(raw, dict):
        return {}, []
    filters = raw.get("filters", {})
    if not isinstance(filters, dict):
        return {}, []

    named_raw = filters.get("named", {})
    named: dict[str, str] = {}
    if isinstance(named_raw, dict):
        for key, value in named_raw.items():
            clean_key = str(key).strip()
            expr = str(value).strip()
            if clean_key and expr:
                named[clean_key] = expr

    entries = filters.get("saved", [])
    if not isinstance(entries, list):
        return named, []
    out = [str(value).strip() for value in entries if str(value).strip()]
    return named, out[:100]


def save_filter_query_to_data(
    data: object,
    expr: str,
    name: str | None = None,
) -> tuple[dict[str, object], dict[str, str], list[str]]:
    text = expr.strip()
    if not text:
        empty = data if isinstance(data, dict) else {}
        named, saved = load_saved_filter_queries_from_data(empty)
        return dict(empty), named, saved

    out: dict[str, object] = dict(data) if isinstance(data, dict) else {}
    filters = out.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}

    saved = filters.get("saved", [])
    if not isinstance(saved, list):
        saved = []
    saved = [str(value).strip() for value in saved if str(value).strip()]
    if text in saved:
        saved.remove(text)
    saved.insert(0, text)
    filters["saved"] = saved[:100]

    if name:
        nm = name.strip()
        if nm:
            named = filters.get("named", {})
            if not isinstance(named, dict):
                named = {}
            named[nm] = text
            filters["named"] = named

    out["filters"] = filters
    named_out = filters.get("named", {})
    named = (
        {str(key): str(value) for key, value in named_out.items()}
        if isinstance(named_out, dict)
        else {}
    )
    return out, named, saved[:100]


def delete_named_filter_from_data(
    data: object,
    name: str,
) -> tuple[dict[str, object], bool, dict[str, str]]:
    nm = name.strip()
    if not nm:
        return (dict(data) if isinstance(data, dict) else {}), False, {}

    out: dict[str, object] = dict(data) if isinstance(data, dict) else {}
    filters = out.get("filters", {})
    if not isinstance(filters, dict):
        return out, False, {}
    named = filters.get("named", {})
    if not isinstance(named, dict):
        return out, False, {}
    if nm not in named:
        named_out = {str(key): str(value) for key, value in named.items()}
        return out, False, named_out

    named.pop(nm, None)
    filters["named"] = named
    out["filters"] = filters
    named_out = {str(key): str(value) for key, value in named.items()}
    return out, True, named_out


def resolve_named_filters_for_display(
    expr: str,
    named_filters: dict[str, str],
    token_finder: Pattern[str],
    depth: int = 0,
) -> str:
    text = expr.strip()
    if not text:
        return "-"
    if depth > 8:
        return text

    parts: list[str] = []
    for token in token_finder.findall(text):
        if token.startswith("@") and len(token) > 1:
            name = token[1:].strip()
            inner = named_filters.get(name)
            if inner:
                resolved = resolve_named_filters_for_display(
                    inner,
                    named_filters,
                    token_finder,
                    depth + 1,
                )
                parts.append(f"({resolved})")
            else:
                parts.append(token)
        else:
            parts.append(token)
    return " ".join(parts)


def load_ui_state_from_data(
    data: object,
    *,
    state_key_side_main: str,
    state_key_side_selected: str,
    state_key_side_info: str,
    state_key_side_settings: str,
    state_key_hotbar_selected_index: str = "hotbar_selected_index",
    side_tab_selected_default: str,
    side_tab_overview_default: str,
    side_tab_events_default: str,
    side_tab_table_default: str,
    side_top_tabs: list[tuple[str, str]],
    side_child_tabs: dict[str, list[tuple[str, str]]],
    sort_mode_ids: set[str],
) -> dict[str, object]:
    state = data.get("state", {}) if isinstance(data, dict) else {}
    if not isinstance(state, dict):
        state = {}

    def as_nonneg_int(value: object, default: int = 0) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return default
        return n if n >= 0 else default

    out: dict[str, object] = {
        "view": str(state.get("view", "active")).strip() or "active",
        "sort": str(state.get("sort", "last")).strip() or "last",
        "query": str(state.get("query", "")).strip(),
        state_key_side_main: str(state.get(state_key_side_main, side_tab_selected_default)).strip()
        or side_tab_selected_default,
        state_key_side_selected: str(
            state.get(state_key_side_selected, side_tab_overview_default)
        ).strip()
        or side_tab_overview_default,
        state_key_side_info: str(state.get(state_key_side_info, side_tab_events_default)).strip()
        or side_tab_events_default,
        state_key_side_settings: str(
            state.get(state_key_side_settings, side_tab_table_default)
        ).strip()
        or side_tab_table_default,
        "selected_path": str(state.get("selected_path", "")).strip(),
        "cursor_row": as_nonneg_int(state.get("cursor_row", 0), 0),
        "scroll_y": as_nonneg_int(state.get("scroll_y", 0), 0),
        "selected_path_active": str(state.get("selected_path_active", "")).strip(),
        "selected_path_archive": str(state.get("selected_path_archive", "")).strip(),
        "cursor_row_active": as_nonneg_int(state.get("cursor_row_active", 0), 0),
        "cursor_row_archive": as_nonneg_int(state.get("cursor_row_archive", 0), 0),
        "scroll_y_active": as_nonneg_int(state.get("scroll_y_active", 0), 0),
        "scroll_y_archive": as_nonneg_int(state.get("scroll_y_archive", 0), 0),
        "row_offset_active": as_nonneg_int(state.get("row_offset_active", 0), 0),
        "row_offset_archive": as_nonneg_int(state.get("row_offset_archive", 0), 0),
        state_key_hotbar_selected_index: as_nonneg_int(
            state.get(state_key_hotbar_selected_index, 0),
            0,
        ),
    }
    if out["view"] not in {"active", "archive"}:
        out["view"] = "active"
    if out["sort"] not in sort_mode_ids:
        out["sort"] = "last"

    top_keys = [key for key, _label in side_top_tabs]
    selected_keys = [key for key, _label in side_child_tabs.get("selected", [])]
    info_keys = [key for key, _label in side_child_tabs.get("info", [])]
    settings_keys = [key for key, _label in side_child_tabs.get("settings", [])]

    if out[state_key_side_main] not in set(top_keys):
        out[state_key_side_main] = top_keys[0] if top_keys else side_tab_selected_default
    if out[state_key_side_selected] not in set(selected_keys):
        out[state_key_side_selected] = (
            selected_keys[0] if selected_keys else side_tab_overview_default
        )
    if out[state_key_side_info] not in set(info_keys):
        out[state_key_side_info] = info_keys[0] if info_keys else side_tab_events_default
    if out[state_key_side_settings] not in set(settings_keys):
        out[state_key_side_settings] = settings_keys[0] if settings_keys else side_tab_table_default

    if not out["selected_path_active"] and out["view"] == "active":
        out["selected_path_active"] = out["selected_path"]
    if not out["selected_path_archive"] and out["view"] == "archive":
        out["selected_path_archive"] = out["selected_path"]
    return out


def save_ui_state_to_data(
    data: object,
    state: dict[str, object],
    *,
    state_key_side_main: str,
    state_key_side_selected: str,
    state_key_side_info: str,
    state_key_side_settings: str,
    state_key_hotbar_selected_index: str = "hotbar_selected_index",
    side_tab_selected_default: str,
    side_tab_overview_default: str,
    side_tab_events_default: str,
    side_tab_table_default: str,
) -> dict[str, object]:
    out: dict[str, object] = dict(data) if isinstance(data, dict) else {}

    def as_nonneg_int(value: object, default: int = 0) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return default
        return n if n >= 0 else default

    out["state"] = {
        "view": state.get("view", "active"),
        "sort": state.get("sort", "last"),
        "query": state.get("query", ""),
        state_key_side_main: state.get(state_key_side_main, side_tab_selected_default),
        state_key_side_selected: state.get(state_key_side_selected, side_tab_overview_default),
        state_key_side_info: state.get(state_key_side_info, side_tab_events_default),
        state_key_side_settings: state.get(state_key_side_settings, side_tab_table_default),
        "selected_path": state.get("selected_path", ""),
        "cursor_row": as_nonneg_int(state.get("cursor_row", 0), 0),
        "scroll_y": as_nonneg_int(state.get("scroll_y", 0), 0),
        "selected_path_active": state.get("selected_path_active", ""),
        "selected_path_archive": state.get("selected_path_archive", ""),
        "cursor_row_active": as_nonneg_int(state.get("cursor_row_active", 0), 0),
        "cursor_row_archive": as_nonneg_int(state.get("cursor_row_archive", 0), 0),
        "scroll_y_active": as_nonneg_int(state.get("scroll_y_active", 0), 0),
        "scroll_y_archive": as_nonneg_int(state.get("scroll_y_archive", 0), 0),
        "row_offset_active": as_nonneg_int(state.get("row_offset_active", 0), 0),
        "row_offset_archive": as_nonneg_int(state.get("row_offset_archive", 0), 0),
        state_key_hotbar_selected_index: as_nonneg_int(
            state.get(state_key_hotbar_selected_index, 0),
            0,
        ),
    }
    return out
