from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass
class RuntimeConfig:
    property_defs: list[Any]
    wip_open_symbol_map: dict[str, int]
    named_filters: dict[str, str]
    saved_filter_queries: list[str]
    suffixes: list[str]
    file_view_exclude_patterns: list[str]
    custom_actions: list[Any]
    open_mode_config: dict[str, str]
    notes_config: dict[str, str]
    reconcile_config: dict[str, dict[str, object]]
    archive_tz_name: str
    archive_tz: Any


def load_runtime_config(
    base_dir: Path,
    *,
    default_archive_tz_name: str,
    load_property_defs: Callable[[Path], list[Any]],
    load_wip_symbol_map: Callable[[Path], dict[str, int]],
    load_saved_filter_queries: Callable[[Path], tuple[dict[str, str], list[str]]],
    load_suffixes: Callable[[Path], list[str]],
    load_file_view_exclude_patterns: Callable[[Path], list[str]],
    load_custom_actions: Callable[[Path], list[Any]],
    load_open_mode_config: Callable[[Path], dict[str, str]],
    load_notes_config: Callable[[Path], dict[str, str]],
    load_reconcile_config: Callable[[Path], dict[str, dict[str, object]]],
    load_archive_timezone_name: Callable[[Path], str],
) -> RuntimeConfig:
    archive_tz_name = load_archive_timezone_name(base_dir)
    try:
        archive_tz = ZoneInfo(archive_tz_name)
    except ZoneInfoNotFoundError:
        archive_tz_name = default_archive_tz_name
        try:
            archive_tz = ZoneInfo(archive_tz_name)
        except ZoneInfoNotFoundError:
            archive_tz = ZoneInfo("UTC")

    named_filters, saved_filter_queries = load_saved_filter_queries(base_dir)
    return RuntimeConfig(
        property_defs=load_property_defs(base_dir),
        wip_open_symbol_map=load_wip_symbol_map(base_dir),
        named_filters=named_filters,
        saved_filter_queries=saved_filter_queries,
        suffixes=load_suffixes(base_dir),
        file_view_exclude_patterns=load_file_view_exclude_patterns(base_dir),
        custom_actions=load_custom_actions(base_dir),
        open_mode_config=load_open_mode_config(base_dir),
        notes_config=load_notes_config(base_dir),
        reconcile_config=load_reconcile_config(base_dir),
        archive_tz_name=archive_tz_name,
        archive_tz=archive_tz,
    )


def resolve_initial_filter_expression(
    initial_filter_expr: str,
    *,
    resolve_filter_expression: Callable[[str], tuple[str, str | None]],
) -> str:
    value = str(initial_filter_expr or "").strip()
    if not value:
        return ""
    if value.startswith("@") or any(ch in value for ch in "#!()| "):
        return value
    resolved, err = resolve_filter_expression(f"@{value}")
    if err is None:
        return resolved
    return value
