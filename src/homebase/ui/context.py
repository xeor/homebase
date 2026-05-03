from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..core.models import PropertyDef


@dataclass(frozen=True)
class UIContext:
    """Runtime config snapshot passed to the textual TUI."""

    base_dir: Path
    archive_tz: ZoneInfo
    archive_tz_name: str
    property_defs: list[PropertyDef] = field(default_factory=list)
    wip_open_symbol_map: dict[str, int] = field(default_factory=dict)
    named_filters: dict[str, str] = field(default_factory=dict)
    saved_filter_queries: list[str] = field(default_factory=list)
    suffixes: list[str] = field(default_factory=list)
    file_view_exclude_patterns: list[str] = field(default_factory=list)
    custom_actions: list[dict[str, Any]] = field(default_factory=list)
    open_mode_config: dict[str, str] = field(default_factory=dict)
    notes_config: dict[str, str] = field(default_factory=dict)
    reconcile_config: dict[str, dict[str, object]] = field(default_factory=dict)
    cache_profile_table: dict[str, dict[str, dict[str, object]]] = field(
        default_factory=dict
    )


def build_ui_context(base_dir: Path) -> UIContext:
    """Snapshot `core.constants` runtime config into a fresh UIContext."""
    from ..core import constants as _const

    return UIContext(
        base_dir=base_dir,
        archive_tz=_const.ARCHIVE_TZ,
        archive_tz_name=_const.ARCHIVE_TZ_NAME,
        property_defs=list(_const.PROPERTY_DEFS),
        wip_open_symbol_map=dict(_const.WIP_OPEN_SYMBOL_MAP),
        named_filters=dict(_const.NAMED_FILTERS),
        saved_filter_queries=list(_const.SAVED_FILTER_QUERIES),
        suffixes=list(_const.SUFFIXES),
        file_view_exclude_patterns=list(_const.FILE_VIEW_EXCLUDE_PATTERNS),
        custom_actions=list(_const.CUSTOM_ACTIONS),
        open_mode_config=dict(_const.OPEN_MODE_CONFIG),
        notes_config=dict(_const.NOTES_CONFIG),
        reconcile_config={
            mode: dict(cfg) for mode, cfg in _const.RECONCILE_CONFIG.items()
        },
        cache_profile_table={
            scope: {name: dict(profile) for name, profile in table.items()}
            for scope, table in _const.CACHE_PROFILE_CONFIG.items()
        },
    )
