from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    Select,
    Static,
    Switch,
    Tab,
    Tabs,
)

from ..cache.api import (
    cache_load_reconcile_usage,
    cache_load_rows,
    cache_move_opened_ts,
    cache_save_reconcile_usage,
    cache_set_opened_ts,
)
from ..commands.archive import (
    _policy_reason_archived_dir,
    _policy_reason_archived_entry,
    _policy_reason_not_under_archive,
    _policy_reason_outside_base,
    _policy_reason_packed_archive,
    archive_move_internal,
    archive_pack_internal,
    archive_restore_internal,
    archive_unpack_internal,
    delete_internal,
    is_packed_archive_path,
)
from ..config import cache_profile as cache_profile_config
from ..config.prefs import (
    _merge_table_columns_for_view,
    load_table_behavior_config,
    load_table_columns_config,
    load_table_date_column_styles,
    load_ui_state,
    resolve_filter_expression,
    save_hotbar,
    save_keys,
    save_ui_state,
)
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    ARCHIVE_TZ_PRESETS,
    BASE_MARKER_FILE,
    BUILTIN_ACTIONS,
    BUSY_LABEL_IDLE,
    CACHE_BG_REFRESH_S,
    CACHE_MAX_AGE_S,
    CACHE_SCHEMA_VERSION,
    COLOR_ACCENT_HEX,
    COLOR_ARCHIVE_HEX,
    COLOR_ERROR_HEX,
    COLOR_INTERACTIVE_HEX,
    COLOR_NAV_HEX,
    COLOR_SUCCESS_HEX,
    COLOR_WARN_HEX,
    CURSOR_BG_HEX,
    CURSOR_FG_HEX,
    LEGACY_BASE_MARKER_FILE,
    LEVEL_INFO,
    LEVEL_WARN,
    MODE_ACTIVE,
    MODE_ARCHIVE,
    OPEN_MODE_PROFILES,
    PACKED_ARCHIVE_SUFFIX,
    PREVIEW_ENTRIES_LIMIT_MAX,
    PREVIEW_ENTRIES_LIMIT_MIN,
    PROFILE_GIT_REFRESH_ACTIVE,
    PROFILE_GIT_REFRESH_ARCHIVE,
    PROFILE_METADATA_HEALTH_ACTIVE,
    PROFILE_METADATA_HEALTH_ARCHIVE,
    PROFILE_PANE_PROBE_ACTIVE,
    PROFILE_PANE_PROBE_ARCHIVE,
    SIDE_CHILD_TABS,
    SIDE_TOP_TABS,
    STATE_KEY_HOTBAR_SELECTED_INDEX,
    STATE_KEY_SIDE_INFO,
    STATE_KEY_SIDE_MAIN,
    STATE_KEY_SIDE_SELECTED,
    STATE_KEY_SIDE_SETTINGS,
    TABLE_COLUMN_VIEWS,
    TABLE_SIDE_WIDTH_PRESETS,
    UI_TICK_BUSY_S,
    UI_TICK_GIT_REFRESH_S,
    UI_TICK_HOOK_REFRESH_S,
    UI_TICK_MICRO_RECONCILE_S,
    UI_TICK_PANE_PROBE_S,
    UI_TICK_QUERY_FLUSH_S,
    UI_TICK_RECONCILE_USAGE_FLUSH_S,
    UI_TICK_STATE_FLUSH_S,
    UI_TICK_WORKTREE_HEALTH_S,
    WIDGET_PROJECTS,
)
from ..core.models import (
    Action,
    ArchiveActionOutcome,
    CacheRefreshOutcome,
    ManagedProcess,
    PaneRef,
    ProjectRow,
    RestoreTargetExistsError,
)
from ..core.utils import WIDGET_API_ERRORS, fmt_ymd
from ..hooks.runtime import HookRunRecord
from ..metadata.api import (
    all_property_defs,
    base_meta_health,
    base_meta_issues,
    load_base_meta,
    normalize_property_keys,
    open_meta_for_review,
    rename_legacy_base_yaml,
    save_base_description,
    save_base_tags,
    save_base_wip,
)
from ..tmux.flow import (
    _tmux_command_prefix,
    tmux_find_panes_for_cwd,
    tmux_open_new_tab,
    tmux_open_new_tab_with_load_status,
)
from ..workspace.deworktree import deworktree as deworktree_internal
from ..workspace.projects import (
    classify_name,
    project_row,
    refresh_row_caches,
)
from ..workspace.rows import (
    _normalize_sort_mode_for_view,
    _sort_modes_for_view,
    archived_restore_target,
    compile_filter_expr,
    normalize_filter_expression,
    query_uses_filter_syntax,
)
from . import runtime_feedback as textual_ui_runtime_feedback
from .actions import action_items as textual_ui_action_items
from .actions import archive_worker as textual_ui_archive_worker
from .actions import bulk_confirm as textual_ui_bulk_confirm
from .actions import bulk_dispatch as textual_ui_bulk_dispatch
from .actions import bulk_preflight as textual_ui_bulk_preflight
from .actions import dispatch as textual_ui_action_dispatch
from .actions import item_edits as textual_ui_item_edits
from .actions import note_sync as textual_ui_note_sync
from .actions import pick_actions as textual_ui_pick_actions
from .actions import project_create as textual_ui_project_create
from .actions import tag_actions as textual_ui_tag_actions
from .actions import wip_actions as textual_ui_wip_actions
from .app_actions import AppActionsMixin
from .app_display import AppDisplayMixin
from .app_events import AppEventsMixin
from .context import UIContext, build_ui_context
from .query import context_rules as textual_ui_query_context_rules
from .query import edit as textual_ui_query_edit
from .query import notes_paths as textual_ui_notes_paths
from .query import runtime as textual_ui_query_runtime
from .query import selection_events as textual_ui_selection_events
from .query import workspace_guard as textual_ui_workspace_guard
from .screens.actions import ActionPickerScreen
from .screens.basic import (
    ConfirmScreen,
    InputScreen,
    ProcessWaitScreen,
    RuntimeErrorScreen,
)
from .screens.choices import FuzzyChoiceScreen, SingleChoiceScreen
from .screens.command_palette import BCommandPalette
from .screens.filter_manage import (
    FilterManageScreen,
    set_filter_manage_base_dir,
)
from .screens.filter_query import (
    set_filter_query_base_dir,
)
from .screens.new_project import NewProjectScreen  # noqa: F401
from .screens.panes import PaneChoiceScreen
from .screens.restore import RestorePathScreen
from .screens.tag_plan import TagPlanScreen  # noqa: F401
from .side import content as textual_ui_side_content
from .side import effects as textual_ui_side_effects
from .side import panel as textual_ui_side_panel
from .side import settings as textual_ui_settings_panel
from .side import tabs as textual_ui_side_tabs
from .sync import cache_refresh as textual_ui_cache_refresh
from .sync import cache_state as textual_ui_cache_state
from .sync import dynamic_props as textual_ui_dynamic_props
from .sync import git_refresh as textual_ui_git_refresh
from .sync import indicator_queries as textual_ui_indicator_queries
from .sync import metadata_health as textual_ui_metadata_health
from .sync import pane_probe as textual_ui_pane_probe
from .sync import reconcile as textual_ui_reconcile
from .sync import reconcile_worker as textual_ui_reconcile_worker
from .sync import sync as textual_ui_sync
from .sync import worktree_health as textual_ui_worktree_health
from .system_commands_provider import get_homebase_system_commands_provider
from .table import nav as textual_ui_table_nav
from .table import row_helpers as textual_ui_row_helpers
from .table import rows_view as textual_ui_rows_view
from .table import tabs_state as textual_ui_tabs_state
from .table import view_actions as textual_ui_view_actions
from .table import view_state as textual_ui_view_state
from .widgets import ReadmeMarkdownViewer, SafeDataTable

# Catch-all for "row construction may legitimately fail; skip the upsert"
# call sites in BApp action handlers.
_ROW_BUILD_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    subprocess.SubprocessError,
    sqlite3.Error,
)

_HOTBAR_PALETTE_TAG = f" \\[[{COLOR_ERROR_HEX}]@hotbar[/]]"

def _build_view_config_default() -> dict[str, dict[str, list[tuple[str, str]]]]:
    ordered_ids = {
        "active": (
            "new_worktree",
            "deworktree",
            "fix_worktrees",
            "archive",
            "set_desc",
            "delete",
        ),
        "archive": ("toggle_pack", "pack", "unpack", "restore", "set_desc", "delete"),
    }
    out: dict[str, dict[str, list[tuple[str, str]]]] = {"active": {"actions": []}, "archive": {"actions": []}}
    for view_mode, action_ids in ordered_ids.items():
        rows: list[tuple[str, str]] = []
        for action_id in action_ids:
            meta = BUILTIN_ACTIONS.get(action_id)
            if meta is None or view_mode not in meta.view_scope:
                continue
            rows.append((action_id, meta.default_label))
        out[view_mode]["actions"] = rows
    return out


_VIEW_CONFIG_DEFAULT: dict[str, dict[str, list[tuple[str, str]]]] = _build_view_config_default()


class BApp(AppActionsMixin, AppDisplayMixin, AppEventsMixin, App[tuple[str, Path | None, list[str]]]):
    COMMANDS = {get_homebase_system_commands_provider}
    CSS = """
    Screen { layout: vertical; }
    #toolbar { height: 5; border: round $accent; padding: 0 1; }
    #global_meta_left { content-align: left top; width: 4fr; }
    #global_meta_right { content-align: left top; width: 2fr; }
    #worktree_health_banner {
        height: 0;
        padding: 0 1;
        background: $warning-darken-2;
        color: $text;
        display: none;
    }
    #worktree_health_banner.visible {
        display: block;
        height: 1;
    }
    #main { height: 1fr; }
    #projects { width: 4fr; height: 1fr; border: round $surface; scrollbar-gutter: stable; }
    #side { width: 2fr; height: 1fr; border: round $surface; padding: 0 1; }
    #side_main_tabs { height: 3; margin: 0 0 1 0; }
    #side_selected_tabs { height: 3; margin: 0 0 1 0; }
    #side_info_tabs { height: 3; margin: 0 0 1 0; }
    #side_settings_tabs { height: 3; margin: 0 0 1 0; }
    #side_settings_table { height: 1fr; display: none; }
    #side_settings_notes { height: 15; display: none; color: $text-muted; }
    #side_settings_config_panel { height: 1fr; display: none; padding: 0 1; }
    #side_settings_config_panel .cfg-row { height: 3; align: left middle; }
    #side_settings_config_panel .cfg-label { width: 1fr; padding: 1 1 0 0; }
    #side_settings_config_panel Switch { width: auto; }
    #side_settings_config_panel Select { width: 28; }
    #side_settings_config_panel Input { width: 12; }
    #side_settings_config_help { height: auto; color: $text-muted; padding: 1 1 0 1; }
    #side_scroll { height: 1fr; }
    #side_body { padding: 0 1; }
    #side_readme_panel { height: 1fr; display: none; }
    #side_readme { height: 1fr; }
    #side_readme_create { width: 1fr; margin: 1 1 0 1; }
    #side_readme_edit { width: 1fr; margin: 1 1 0 1; }
    #side_notes_panel { height: 1fr; display: none; }
    #side_notes { height: 1fr; }
    #side_notes_create { width: 1fr; margin: 1 1 0 1; }
    #side_notes_open { width: 1fr; margin: 1 1 0 1; }
    #side_global_panel { height: 1fr; display: none; }
    #side_global_info { height: 1fr; }
    #side_global_config_reload { width: 1fr; margin: 1 1 0 1; }
    #side_global_config_edit { width: 1fr; margin: 1 1 0 1; }
    #wip_bar { height: 1; background: $surface-darken-1; color: $text; content-align: left middle; }
    #confirm_box { width: 70; height: 16; border: round $warning; background: $surface; padding: 1 2; }
    #new_project_box { width: 100%; height: 100%; border: round $accent; background: $surface; padding: 1 2; }
    #new_body { height: 1fr; }
    #new_left { width: 2fr; border: round $surface-lighten-1; padding: 0 1; }
    #new_right { width: 1fr; border: round $surface-lighten-1; padding: 0 1; }
    #new_plan { height: 3; border: round $accent-darken-1; padding: 0 1; }
    #new_hotkeys { height: 1; color: $text-muted; }
    #tag_plan_box { width: 70%; height: 100%; border: round $accent; background: $surface; padding: 1 2; }
    #tag_list { height: 1fr; }
    #tag_help { height: 5; color: $text-muted; }
    #tag_status { height: 1; }
    #tag_hotkeys { height: 1; color: $text-muted; }
    #filter_mgmt_input { border: none; margin: 0 0 1 0; }
    #filter_query { border: none; margin: 0 0 1 0; }
    Input .input--cursor { background: __CURSOR_BG__; color: __CURSOR_FG__; text-style: bold; }
    """.replace("__CURSOR_BG__", CURSOR_BG_HEX).replace("__CURSOR_FG__", CURSOR_FG_HEX)
    BINDINGS = [
        ("ctrl+n", "new_project", "New"),
        ("ctrl+p", "command_palette", "Command palette"),
        ("ctrl+s", "pick_sort", "Sort picker"),
        ("ctrl+f", "pick_filters", "Saved filters"),
        ("ctrl+c", "reset_view", "Reset view"),
        ("ctrl+l", "cycle_tabs", "tabs >"),
        ("ctrl+k", "cycle_tabs_prev", "tabs <"),
        ("ctrl+d", "toggle_view", "Toggle view"),
        ("ctrl+w", "toggle_wip", "Toggle WIP"),
        Binding("left", "route_left", "Left", show=False, priority=True),
        Binding("right", "route_right", "Right", show=False, priority=True),
        Binding("home", "route_home", "Home", show=False, priority=True),
        Binding("end", "route_end", "End", show=False, priority=True),
        Binding(
            "alt+left",
            "table_scroll_left",
            "Scroll left",
            show=False,
            priority=True,
        ),
        Binding(
            "alt+right",
            "table_scroll_right",
            "Scroll right",
            show=False,
            priority=True,
        ),
        ("ctrl+a", "pick_actions", "Actions"),
        ("ctrl+o", "toggle_select_mode", "Select mode"),
        Binding("ctrl+x", "dismiss_worktree_health", "Dismiss banner", show=False),
        Binding("ctrl+@", "cycle_hotbar", "Next hotbar", show=False, priority=True),
        ("enter", "open_selected", "Open"),
        ("ctrl+q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        base_dir: Path,
        ctx: UIContext | None = None,
        start_new_mode: bool = False,
        initial_filter: str = "",
    ) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.ctx = ctx if ctx is not None else build_ui_context(base_dir)
        self._confirm_screen_cls = ConfirmScreen
        self._process_wait_screen_cls = ProcessWaitScreen
        self._input_screen_cls = InputScreen
        self._action_picker_screen_cls = ActionPickerScreen
        self._fuzzy_choice_screen_cls = FuzzyChoiceScreen
        self._single_choice_screen_cls = SingleChoiceScreen
        self.start_new_mode = start_new_mode
        persisted = load_ui_state(self.base_dir)
        self._init_rows_state(initial_filter, persisted)
        self._init_side_state(persisted)
        self._init_view_state(persisted)
        self._init_message_state()
        self._init_worker_state()
        self._init_pane_state()
        self._init_query_state()
        self._init_busy_state()
        self._init_hooks_state()
        self._init_settings_state()
        self._init_reconcile_state()
        self.view_config = _VIEW_CONFIG_DEFAULT

    def _init_rows_state(self, initial_filter: str, persisted: dict[str, object]) -> None:
        cached_active, cached_archived, cache_refreshed = cache_load_rows(
            self.base_dir, CACHE_MAX_AGE_S
        )
        self.active_rows = cached_active
        self.archived_rows = cached_archived
        self._rows_state_token = 1
        self._rows_cache_token = 0
        self._rows_cache_view = ""
        self._rows_cache_sort = ""
        self._rows_cache_query = ""
        self._rows_cache: list[ProjectRow] = []
        self._rows_index_by_path: dict[Path, int] = {}
        self.view_mode = persisted.get("view", "active")
        self.sort_mode = _normalize_sort_mode_for_view(
            self.view_mode, persisted.get("sort", "last")
        )
        self.query = initial_filter or persisted.get("query", "")
        self.query_cursor = len(self.query)
        self.filter_expr = initial_filter
        self.cache_last_refresh_ts = cache_refreshed

    def _init_side_state(self, persisted: dict[str, object]) -> None:
        top_default = SIDE_TOP_TABS[0][0] if SIDE_TOP_TABS else "selected"
        selected_default = SIDE_CHILD_TABS.get(
            "selected", [("overview", "Overview")]
        )[0][0]
        info_default = SIDE_CHILD_TABS.get("info", [("events", "Events")])[0][0]
        settings_default = SIDE_CHILD_TABS.get("settings", [("table", "Table")])[0][0]
        self.side_main_tab = str(persisted.get(STATE_KEY_SIDE_MAIN, top_default))
        self.side_selected_tab = str(persisted.get(STATE_KEY_SIDE_SELECTED, selected_default))
        self.side_info_tab = str(persisted.get(STATE_KEY_SIDE_INFO, info_default))
        self.side_settings_tab = str(persisted.get(STATE_KEY_SIDE_SETTINGS, settings_default))
        valid_top = {key for key, _label in SIDE_TOP_TABS}
        valid_selected = {key for key, _label in SIDE_CHILD_TABS.get("selected", [])}
        valid_info = {key for key, _label in SIDE_CHILD_TABS.get("info", [])}
        valid_settings = {key for key, _label in SIDE_CHILD_TABS.get("settings", [])}
        if self.side_main_tab not in valid_top:
            self.side_main_tab = top_default
        if self.side_selected_tab not in valid_selected:
            self.side_selected_tab = selected_default
        if self.side_info_tab == "processes":
            self.side_info_tab = "cache"
        if self.side_info_tab not in valid_info:
            self.side_info_tab = info_default
        if self.side_settings_tab not in valid_settings:
            self.side_settings_tab = settings_default
        try:
            hotbar_idx = int(persisted.get(STATE_KEY_HOTBAR_SELECTED_INDEX, 0) or 0)
        except (TypeError, ValueError):
            hotbar_idx = 0
        self.hotbar_selected_index = max(0, hotbar_idx)
        self.side_detail_row: Path | None = None
        self.side_git_text = ""
        self.side_files_text = ""
        self.side_readme_source_path: Path | None = None
        self.side_readme_rendered_path: Path | None = None
        self.side_readme_rendered_text = ""
        self.side_notes_source_path: Path | None = None
        self.side_notes_rendered_path: Path | None = None
        self.side_notes_rendered_text = ""
        self._suspend_project_row_highlight = False
        self._readme_nav_allow_until = 0.0

    def _init_view_state(self, persisted: dict[str, object]) -> None:
        def persisted_path(key: str) -> Path | None:
            value = str(persisted.get(key, "")).strip()
            return Path(value) if value else None

        def persisted_int(key: str) -> int:
            return int(persisted.get(key, 0) or 0)

        self._view_selected_path: dict[str, Path | None] = {
            "active": persisted_path("selected_path_active"),
            "archive": persisted_path("selected_path_archive"),
        }
        self._view_cursor_row: dict[str, int] = {
            "active": persisted_int("cursor_row_active"),
            "archive": persisted_int("cursor_row_archive"),
        }
        self._view_scroll_y: dict[str, int] = {
            "active": persisted_int("scroll_y_active"),
            "archive": persisted_int("scroll_y_archive"),
        }
        self._view_row_offset: dict[str, int] = {
            "active": persisted_int("row_offset_active"),
            "archive": persisted_int("row_offset_archive"),
        }
        self._restore_target_path: dict[str, Path | None] = {
            "active": self._view_selected_path["active"],
            "archive": self._view_selected_path["archive"],
        }
        self._restore_pending: dict[str, bool] = {
            mode: self._restore_target_path[mode] is not None
            for mode in ("active", "archive")
        }
        self._restore_apply_scroll: dict[str, bool] = dict(self._restore_pending)
        self._restore_retry_left = 32
        self.selected_path = self._view_selected_path.get(self.view_mode)
        self._state_cursor_row = self._view_cursor_row.get(self.view_mode, 0)
        self._state_scroll_y = self._view_scroll_y.get(self.view_mode, 0)

    def _init_message_state(self) -> None:
        self.multi_selected: set[Path] = set()
        self.pending_desc_targets: list[Path] = []
        self.pending_rename_target: Path | None = None
        self.actions = dict(self.ctx.actions)
        self.custom_actions = [
            action for action in self.actions.values() if action.source != "builtin"
        ]
        self.custom_hotkeys = self._bindings_from_ctx()
        self.pending_tag_updates: set[Path] = set()
        self._visible_column_effective_width_by_id: dict[str, int] = {}
        self.managed_processes: list[ManagedProcess] = []
        self._managed_processes_lock = threading.Lock()
        self._wait_process_modal_pid: int | None = None
        self.messages: list[tuple[str, str, str]] = []
        self._health_issue_seen: dict[Path, str] = {}
        self.pending_restore_queue: list[Path] = []
        self.pending_restore_ok = 0
        self.pending_restore_failed = 0
        self.error_counts: dict[str, int] = {}
        self.worker_debug_events: list[tuple[str, str]] = []
        self._main_table_was_locked = False
        self._table_render_signature: tuple[object, ...] | None = None
        self._table_column_signature: tuple[object, ...] | None = None
        self._property_cell_cache: dict[tuple[str, ...], object] = {}
        self._property_cell_cache_sig: int = -1
        self._state_dirty = False
        self._state_due_at = 0.0
        self._state_last_json = ""
        self.runtime_status_text = ""
        self.runtime_status_level = "info"
        self.runtime_status_until_ts = 0.0

    def _init_worker_state(self) -> None:
        self.cache_worker_running = False
        self.cache_worker_note = ""
        self.cache_worker_started_ts = 0.0
        self.cache_worker_last_done_ts = 0.0
        self.cache_refresh_epoch = 0
        self.cache_refresh_pending = False
        self.cache_refresh_pending_force = False
        self.cache_refresh_pending_reason = ""
        self.workspace_sig_last = ""
        self.workspace_sig_last_ts = 0.0
        self.workspace_sig_due_at = 0.0
        self.reconcile_inconsistency_streak = 0
        self.tag_sync_running = False
        self.tag_sync_pending = False
        self.tag_sync_pending_reason = ""
        self.action_worker_running = False
        self.action_worker_action = ""
        self.action_worker_total = 0
        self.action_worker_done = 0
        self.action_worker_current = ""
        self.action_worker_stage = ""
        self.action_worker_command = ""
        self.action_worker_started_ts = 0
        self.git_refresh_running = False
        self.git_refresh_paths: set[Path] = set()
        self.git_refresh_last_ts = 0.0
        self.git_refresh_next_due_at = 0.0
        self.git_refresh_reason = ""
        self.metadata_health_cache: dict[Path, tuple[str, str, float]] = {}
        self.metadata_health_refresh_running = False
        self.metadata_health_refresh_last_ts = 0.0
        self.metadata_health_refresh_next_due_at = 0.0
        self.worktree_health_issues: list[dict[str, object]] = []
        self.worktree_health_last_scan_ts = 0
        self.worktree_health_refresh_running = False
        self.worktree_health_refresh_last_ts = 0.0
        self.worktree_health_dismissed = False
        self.worktree_health_scan_cursor: list[str] = []
        self.detail_worker_running = False
        self.detail_worker_path: Path | None = None
        self.detail_worker_token = 0
        self.fast_exit_requested = False

    def _init_pane_state(self) -> None:
        self.open_panes_by_project: dict[Path, list[PaneRef]] = {}
        self.open_pane_count_by_project: dict[Path, int] = {}
        self.open_pane_overflow_projects: set[Path] = set()
        self.pane_probe_running = False
        self.pane_state_sig = ""
        self.pane_probe_next_due_at = 0.0
        self.pane_probe_last_done_ts = 0.0
        self.pane_probe_fast_until_ts = 0.0
        self.pending_pane_choices: dict[str, PaneRef] = {}
        self.dynamic_indicator_cache: dict[str, tuple[float, set[Path]]] = {}
        self.dynamic_indicator_row_cache: dict[tuple[str, Path], tuple[float, bool]] = {}
        self.dynamic_property_refresh_queue: list[Path] = []
        self.dynamic_property_refresh_next_due_at = 0.0

    def _init_query_state(self) -> None:
        self.select_mode = False
        self.query_complete_index = -1
        self.query_complete_candidates: list[str] = []
        self.query_complete_head = ""
        self.query_complete_tail = ""
        self.query_apply_pending = False
        self.query_apply_due_at = 0.0
        self.query_apply_debounce_s = 0.12
        self.query_last_rows_count = 0
        self.query_eval_cache: dict[
            str,
            tuple[bool, str, str | None, Callable[[ProjectRow], bool], str | None],
        ] = {}
        self.query_eval_cache_order: list[str] = []
        self.query_named_sig = ""
        self.completion_counts_token = -1
        self.completion_tag_counts: list[tuple[str, int]] = []
        self.completion_prop_counts: list[tuple[str, int]] = []
        if not hasattr(self, "hotbar_selected_index"):
            self.hotbar_selected_index = 0
        self._resize_refresh_token = 0

    def _init_busy_state(self) -> None:
        self._busy_depth = 0
        self._busy_label = BUSY_LABEL_IDLE
        self._busy_frames = ["|", "/", "-", "\\"]
        self._busy_frame_index = 0

    def _init_settings_state(self) -> None:
        self.table_columns_by_view = load_table_columns_config(self.base_dir)
        self.table_settings_index = 0
        self.table_behavior = load_table_behavior_config(self.base_dir)
        self.table_date_color_ranges = load_table_date_column_styles(self.base_dir)
        self._settings_config_loading = True
        self.open_mode = dict(self.ctx.open_mode_config)
        self.notes_config = dict(self.ctx.notes_config)
        self.open_settings_index = 0

    def _init_hooks_state(self) -> None:
        self.hook_recent: dict[tuple[str, str], list[HookRunRecord]] = {}
        self.hook_running: dict[str, float] = {}
        self.hook_refresh_last: dict[tuple[Path, str], float] = {}

    def _init_reconcile_state(self) -> None:
        self.reconcile_config = {
            "active": dict(self.ctx.reconcile_config.get("active", {})),
            "archive": dict(self.ctx.reconcile_config.get("archive", {})),
        }
        now_ts = time.time()
        self.reconcile_next_due: dict[str, float] = {
            mode: now_ts + float(self.reconcile_config[mode].get("interval_s", 5.0))
            for mode in ("active", "archive")
        }
        self.reconcile_worker_running = False
        self.reconcile_worker_mode = ""
        self.reconcile_worker_reason = ""
        self.reconcile_worker_started_ts = 0.0
        self.reconcile_worker_last_done_ts = 0.0
        self.reconcile_last_skip_reason = ""
        self.reconcile_last_skip_ts = 0.0
        self.reconcile_queue: list[tuple[int, str, str, list[Path]]] = []
        usage_score, usage_hits, usage_last = cache_load_reconcile_usage(self.base_dir)
        self.row_usage_score: dict[Path, float] = usage_score
        self.row_usage_hits: dict[Path, int] = usage_hits
        self.row_usage_last_used_ts: dict[Path, int] = usage_last
        self.reconcile_usage_dirty = False
        self.reconcile_usage_due_at = 0.0
        self.reconcile_recent: dict[str, list[tuple[str, str]]] = {
            "active": [],
            "archive": [],
        }

    def _log(self, msg: str, level: str = "info") -> None:
        textual_ui_runtime_feedback.log(self, msg, level=level)

    def _log_error_counted(self, key: str, msg: str, level: str = "warn") -> None:
        textual_ui_runtime_feedback.log_error_counted(
            self,
            key,
            msg,
            level=level,
        )

    def _show_runtime_error(
        self, context: str, exc: BaseException, traceback_tail: str = ""
    ) -> None:
        textual_ui_runtime_feedback.show_runtime_error(
            self,
            context,
            exc,
            traceback_tail=traceback_tail,
            runtime_error_screen=RuntimeErrorScreen,
        )

    def _log_row_health_issues(self, rows: list[ProjectRow]) -> None:
        textual_ui_runtime_feedback.log_row_health_issues(
            self,
            rows,
            base_meta_health=base_meta_health,
        )

    def _capture_table_position(self) -> bool:
        return textual_ui_view_state.capture_table_position(
            self,
            widget_projects=WIDGET_PROJECTS,
        )

    def _retry_pending_restore(self) -> None:
        textual_ui_view_state.retry_pending_restore(self)

    def _cancel_restore_for_current_view(self) -> None:
        textual_ui_view_state.cancel_restore_for_current_view(self)

    def _apply_view_state(self, view: str) -> None:
        textual_ui_view_state.apply_view_state(self, view)

    def _state_snapshot(self) -> dict[str, object]:
        return textual_ui_view_state.state_snapshot(
            self,
            state_key_side_main=STATE_KEY_SIDE_MAIN,
            state_key_side_selected=STATE_KEY_SIDE_SELECTED,
            state_key_side_info=STATE_KEY_SIDE_INFO,
            state_key_side_settings=STATE_KEY_SIDE_SETTINGS,
            state_key_hotbar_selected_index=STATE_KEY_HOTBAR_SELECTED_INDEX,
        )

    def _restore_table_position(self) -> None:
        textual_ui_view_state.restore_table_position(
            self,
            widget_projects=WIDGET_PROJECTS,
        )

    def _mark_state_dirty(self) -> None:
        textual_ui_runtime_feedback.mark_state_dirty(self)

    def _flush_state_if_due(self, force: bool = False) -> None:
        textual_ui_runtime_feedback.flush_state_if_due(
            self,
            force=force,
            base_dir=self.base_dir,
            save_ui_state=save_ui_state,
        )

    def _persist_state_now(self) -> None:
        textual_ui_runtime_feedback.persist_state_now(self)

    def _busy_start(self, label: str) -> None:
        textual_ui_runtime_feedback.busy_start(self, label)

    def _busy_stop(self) -> None:
        textual_ui_runtime_feedback.busy_stop(self)

    def _busy_tick(self) -> None:
        textual_ui_runtime_feedback.busy_tick(self)

    def _set_runtime_status(
        self, text: str, level: str = "info", ttl_s: float = 12.0
    ) -> None:
        textual_ui_runtime_feedback.set_runtime_status(
            self,
            text,
            level=level,
            ttl_s=ttl_s,
        )

    def _critical_job_active(self) -> bool:
        return textual_ui_runtime_feedback.critical_job_active(self)

    def _critical_job_label(self) -> str:
        return textual_ui_runtime_feedback.critical_job_label(self)

    def _worker_debug(self, message: str) -> None:
        textual_ui_runtime_feedback.worker_debug(self, message)

    def _set_reconcile_skip_reason(self, reason: str) -> None:
        textual_ui_runtime_feedback.set_reconcile_skip_reason(self, reason)

    def compose(self) -> ComposeResult:
        with Horizontal(id="toolbar"):
            yield Static("", id="global_meta_left")
            yield Static("", id="global_meta_right")
        yield Static("", id="worktree_health_banner")
        with Horizontal(id="main"):
            yield SafeDataTable(id="projects", cursor_type="row")
            with Vertical(id="side"):
                yield Tabs(
                    *[Tab(label, id=key) for key, label in SIDE_TOP_TABS],
                    id="side_main_tabs",
                )
                yield Tabs(
                    *[
                        Tab(label, id=key)
                        for key, label in SIDE_CHILD_TABS.get("selected", [])
                    ],
                    id="side_selected_tabs",
                )
                yield Tabs(
                    *[
                        Tab(label, id=key)
                        for key, label in SIDE_CHILD_TABS.get("info", [])
                    ],
                    id="side_info_tabs",
                )
                yield Tabs(
                    *[
                        Tab(label, id=key)
                        for key, label in SIDE_CHILD_TABS.get("settings", [])
                    ],
                    id="side_settings_tabs",
                )
                with VerticalScroll(id="side_scroll"):
                    yield Static("", id="side_body")
                    with Vertical(id="side_readme_panel"):
                        yield ReadmeMarkdownViewer(
                            "",
                            show_table_of_contents=False,
                            open_links=False,
                            id="side_readme",
                        )
                        yield Button(
                            "Create README.md in $EDITOR",
                            id="side_readme_create",
                            variant="primary",
                            compact=True,
                            flat=True,
                        )
                    with Vertical(id="side_notes_panel"):
                        yield ReadmeMarkdownViewer(
                            "",
                            show_table_of_contents=False,
                            open_links=False,
                            id="side_notes",
                        )
                        yield Button(
                            "Create note",
                            id="side_notes_create",
                            variant="primary",
                            compact=True,
                            flat=True,
                        )
                        yield Button(
                            "Open note",
                            id="side_notes_open",
                            variant="primary",
                            compact=True,
                            flat=True,
                        )
                        yield Button(
                            "Edit README.md in $EDITOR",
                            id="side_readme_edit",
                            variant="primary",
                            compact=True,
                            flat=True,
                        )
                    with Vertical(id="side_global_panel"):
                        yield Static("", id="side_global_info")
                        yield Button(
                            "Reload global config",
                            id="side_global_config_reload",
                            variant="default",
                            compact=True,
                            flat=True,
                        )
                        yield Button(
                            "Edit global config in $EDITOR",
                            id="side_global_config_edit",
                            variant="primary",
                            compact=True,
                            flat=True,
                        )
                yield Static("", id="side_settings_notes")
                yield DataTable(id="side_settings_table", cursor_type="row")
                with Vertical(id="side_settings_config_panel"):
                    with Horizontal(classes="cfg-row"):
                        yield Label("Pin WIP rows at top", classes="cfg-label")
                        yield Switch(id="cfg_pin_wip", value=False)
                    with Horizontal(classes="cfg-row"):
                        yield Label("Info panel width", classes="cfg-label")
                        yield Select(
                            options=[(f"{p}%", p) for p in TABLE_SIDE_WIDTH_PRESETS],
                            id="cfg_side_width",
                            allow_blank=False,
                            compact=True,
                            type_to_search=True,
                        )
                    with Horizontal(classes="cfg-row"):
                        yield Label("Preview files (overview)", classes="cfg-label")
                        yield Input(
                            id="cfg_preview_limit",
                            value="8",
                            type="integer",
                            max_length=4,
                            compact=True,
                        )
                    with Horizontal(classes="cfg-row"):
                        yield Label("Archive timezone", classes="cfg-label")
                        yield Select(
                            options=[(tz, tz) for tz in ARCHIVE_TZ_PRESETS],
                            id="cfg_archive_tz",
                            allow_blank=False,
                            compact=True,
                            type_to_search=True,
                        )
                    yield Static(
                        "[dim]tab: next field   space/enter: toggle/open   "
                        "type to filter dropdowns   enter on number: commit[/]",
                        id="side_settings_config_help",
                    )
        yield Static("", id="wip_bar")
        yield Footer()

    def on_mount(self) -> None:
        self._configure_inputs()
        self._state_last_json = json.dumps(self._state_snapshot(), sort_keys=True)
        table = self.query_one(WIDGET_PROJECTS, DataTable)
        table.zebra_stripes = True
        table.focus()
        settings_table = self.query_one("#side_settings_table", DataTable)
        settings_table.zebra_stripes = True
        self.set_interval(UI_TICK_BUSY_S, self._busy_tick)
        self.set_interval(UI_TICK_QUERY_FLUSH_S, self._flush_query_apply_if_due)
        self.set_interval(UI_TICK_STATE_FLUSH_S, self._flush_state_if_due)
        self.set_interval(UI_TICK_RECONCILE_USAGE_FLUSH_S, self._flush_reconcile_usage_if_due)
        self.set_interval(UI_TICK_PANE_PROBE_S, self._maybe_probe_open_panes)
        self.set_interval(UI_TICK_GIT_REFRESH_S, self._maybe_refresh_visible_git)
        self.set_interval(UI_TICK_MICRO_RECONCILE_S, self._maybe_run_micro_reconcile)
        self.set_interval(UI_TICK_HOOK_REFRESH_S, self._maybe_run_hook_refresh)
        self.set_interval(
            UI_TICK_WORKTREE_HEALTH_S, self._maybe_refresh_worktree_health
        )
        self.call_after_refresh(self._initial_worktree_health_scan)
        for wid in (
            self.query_one("#side", Vertical),
            self.query_one("#side_main_tabs", Tabs),
            self.query_one("#side_selected_tabs", Tabs),
            self.query_one("#side_info_tabs", Tabs),
            self.query_one("#side_settings_tabs", Tabs),
            self.query_one("#side_scroll", VerticalScroll),
            self.query_one("#side_body", Static),
            self.query_one("#side_readme_panel", Vertical),
            self.query_one("#side_readme", ReadmeMarkdownViewer),
            self.query_one("#side_notes_panel", Vertical),
            self.query_one("#side_notes", ReadmeMarkdownViewer),
            self.query_one("#side_global_panel", Vertical),
            self.query_one("#side_global_info", Static),
            self.query_one("#side_settings_table", DataTable),
            self.query_one("#side_settings_notes", Static),
            self.query_one("#wip_bar", Static),
            self.query_one("#global_meta_left", Static),
            self.query_one("#global_meta_right", Static),
        ):
            if hasattr(wid, "can_focus"):
                try:
                    wid.can_focus = False
                except WIDGET_API_ERRORS:
                    pass
        self._busy_start("initializing view")
        try:
            self._configure_table_columns()
            self._refresh_table()
            self._restore_table_position()
            self._sync_side_tab_visibility()
            self._apply_side_tab_state_to_widgets()
            self._refresh_side()
            self.workspace_sig_last = self._workspace_quick_signature()
            self.workspace_sig_last_ts = time.time()
        finally:
            self._busy_stop()
        self.set_interval(CACHE_BG_REFRESH_S, self._maybe_refresh_cache)
        if not self.active_rows and not self.archived_rows:
            self.call_after_refresh(
                lambda: self._start_cache_refresh("cold start", force=True)
            )
        elif int(time.time()) - self.cache_last_refresh_ts > CACHE_MAX_AGE_S:
            self.call_after_refresh(
                lambda: self._start_cache_refresh("stale cache", force=False)
            )
        if self.start_new_mode:
            self.call_after_refresh(self.action_new_project)
        self.call_after_refresh(self._startup_quick_active_dir_check)
        self.call_after_refresh(self._start_probe_open_panes)
        self.set_timer(0.12, self._retry_pending_restore)
        self.set_timer(0.18, self._reflow_table_columns_after_layout)
        self.call_after_refresh(self._settings_config_finish_boot)

    def _settings_config_finish_boot(self) -> None:
        self._settings_config_loading = False

    def _reflow_table_columns_after_layout(self) -> None:
        self._configure_table_columns()
        self._refresh_table()

    def _refresh_after_resize(self, token: int) -> None:
        if token != self._resize_refresh_token:
            return
        self._configure_table_columns()
        self._refresh_table()

    def on_resize(self, _event) -> None:
        self._resize_refresh_token += 1
        token = self._resize_refresh_token
        self._configure_table_columns()
        self._refresh_table()
        self.set_timer(0.12, lambda: self._refresh_after_resize(token))
        self.set_timer(0.32, lambda: self._refresh_after_resize(token))

    def _modal_active(self) -> bool:
        return isinstance(self.screen, ModalScreen)

    def check_action(
        self, action: str, parameters: tuple[object, ...]
    ) -> bool | None:
        # Prevent app-level actions from firing while a modal dialog is open.
        # Dialog screens should own key handling in that state.
        if self._modal_active():
            return False
        return True

    def _configure_inputs(self) -> None:
        for inp in self.screen.query(Input):
            inp.cursor_blink = False
            inp.compact = True

    def on_descendant_focus(self, event) -> None:
        widget = getattr(event, "widget", None)
        if isinstance(widget, Input):
            widget.cursor_blink = False
            return
        if self._main_table_interaction_locked():
            return
        if isinstance(widget, DataTable):
            return
        table = self.query_one(WIDGET_PROJECTS, DataTable)
        if widget is not None and table is not widget:
            self.call_after_refresh(table.focus)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        textual_ui_tabs_state.on_tabs_tab_activated(
            self,
            event,
            side_top_tabs=SIDE_TOP_TABS,
            side_child_tabs=SIDE_CHILD_TABS,
        )

    def _sync_side_tab_visibility(self) -> None:
        textual_ui_tabs_state.sync_side_tab_visibility(
            self,
            widget_projects=WIDGET_PROJECTS,
        )

    def _refresh_settings_tab_labels(self, settings_tabs: Tabs) -> None:
        textual_ui_tabs_state.refresh_settings_tab_labels(self, settings_tabs)

    def _set_tabs_active_safe(self, tabs: Tabs, tab_id: str) -> None:
        textual_ui_tabs_state.set_tabs_active_safe(tabs, tab_id)

    def _main_table_interaction_locked(self) -> bool:
        return textual_ui_tabs_state.main_table_interaction_locked(self)

    def _child_key_for_top(self, top_key: str) -> str:
        return textual_ui_tabs_state.child_key_for_top(self, top_key)

    def _set_child_key_for_top(self, top_key: str, child_key: str) -> None:
        textual_ui_tabs_state.set_child_key_for_top(self, top_key, child_key)

    def _jump_to_side_tab(self, top_key: str, child_key: str = "") -> None:
        textual_ui_tabs_state.jump_to_side_tab(
            self,
            top_key,
            child_key=child_key,
            side_top_tabs=SIDE_TOP_TABS,
            side_child_tabs=SIDE_CHILD_TABS,
        )

    def get_system_commands(self, screen) -> Iterable[SystemCommand]:
        # Command palette includes tab navigation and currently valid actions.

        for top_key, top_label in SIDE_TOP_TABS:
            command_id = f"tab:{top_key}"
            is_top_active = self.side_main_tab == top_key
            top_title = (
                f"Tab: {top_label}"
                if not is_top_active
                else f"Tab: {top_label} (active)"
            )
            starred = self._target_is_hotbar(command_id)
            yield SystemCommand(
                top_title + (_HOTBAR_PALETTE_TAG if starred else ""),
                f"Go to main tab: {top_label} (id={command_id})",
                lambda top=top_key: self._jump_to_side_tab(top),
            )

            for child_key, child_label in SIDE_CHILD_TABS.get(top_key, []):
                command_id = f"tab:{top_key}/{child_key}"
                is_active = (
                    self.side_main_tab == top_key
                    and self._child_key_for_top(top_key) == child_key
                )
                title = (
                    f"Tab: {top_label} / {child_label}"
                    if not is_active
                    else f"Tab: {top_label} / {child_label} (active)"
                )
                starred = self._target_is_hotbar(command_id)
                yield SystemCommand(
                    title + (_HOTBAR_PALETTE_TAG if starred else ""),
                    f"Go to tab: {top_label} / {child_label} (id={command_id})",
                    lambda top=top_key, child=child_key: self._jump_to_side_tab(
                        top, child
                    ),
                )

        grouped: dict[str, list[tuple[str, str]]] = {"target": [], "global": []}
        if self._target_rows():
            grouped["target"].append(("open_selected", "[white]Open selected (default)[/]"))

        custom_scope_by_id: dict[str, str] = {}
        custom_list_action_ids: set[str] = set()
        for action in self.ctx.actions.values():
            if action.source == "builtin":
                continue
            scope = "global" if action.scope == "workspace" else "target"
            custom_scope_by_id[action.id] = scope
            if action.kind == "filepicker":
                custom_list_action_ids.add(action.id)

        target_actions = {
            "readme_create",
            "readme_edit",
            "notes_create",
            "notes_open",
            "tags_set",
            "reconcile_selection_cache",
            "hooks_refresh",
            "suffix_set",
            "rename_item",
            "review_meta",
            "rename_meta_ext",
            "archive",
            "restore",
            "pack",
            "unpack",
            "toggle_pack",
            "delete",
            "set_desc",
        }
        global_actions = {
            "refresh_cache",
            "full_reconcile",
            "reconcile_all_cache",
            "reload_global_config",
            "edit_global_config",
            "hooks_refresh_view",
        }

        def _scope_for_action(action_id: str) -> str:
            if action_id in custom_scope_by_id:
                scope = custom_scope_by_id[action_id]
                if scope in {"target", "global"}:
                    return scope
            if action_id in target_actions:
                return "target"
            if action_id in global_actions:
                return "global"
            return "target"

        def _natural_key(text: str) -> tuple[object, ...]:
            parts = re.split(r"(\d+)", text.lower())
            out: list[object] = []
            for part in parts:
                if part.isdigit():
                    out.append(int(part))
                else:
                    out.append(part)
            return tuple(out)

        for action_id, label in self._valid_action_items():
            grouped[_scope_for_action(action_id)].append((action_id, label))
        for scope in ("target", "global"):
            for action_id, label in sorted(
                grouped[scope],
                key=lambda pair: (
                    1 if pair[0] in custom_list_action_ids else 0,
                    _natural_key(self._label_plain(pair[1])),
                ),
            ):
                plain = self._label_plain(label)
                if action_id in custom_list_action_ids and plain.endswith(" (filepicker)"):
                    plain = plain[: -len(" (filepicker)")]
                if scope == "target":
                    scope_prefix = "[#7DFF9B]Action > Target[/]"
                else:
                    scope_prefix = "[#ffb347]Action > Global[/]"
                if action_id in custom_list_action_ids:
                    scope_prefix = scope_prefix.replace("[/]", " (filepicker)[/]")
                title = f"{scope_prefix}: {plain}"
                starred = self._target_is_hotbar(f"action:{action_id}")
                yield SystemCommand(
                    title + (_HOTBAR_PALETTE_TAG if starred else ""),
                    f"{self._action_help_text(action_id, label)} (id=action:{action_id})",
                    (
                        self.action_open_selected
                        if action_id == "open_selected"
                        else (lambda aid=action_id: self._on_pick_actions(aid))
                    ),
                )

    def action_command_palette(self) -> None:
        if not CommandPalette.is_open(self):
            self.push_screen(BCommandPalette(id="--command-palette"))

    def _dispatch_hotkey_target(self, target: str) -> None:
        normalized = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
        if not normalized:
            return
        textual_ui_action_dispatch.dispatch_action(self, normalized)

    def _bindings_from_ctx(self) -> list[dict[str, object]]:
        if not self.ctx.hotbar and not self.ctx.keys and self.ctx.custom_hotkeys:
            return [dict(item) for item in self.ctx.custom_hotkeys]
        bindings: list[dict[str, object]] = []
        for idx, item in enumerate(self.ctx.hotbar, start=1):
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
            raw_style = item.get("style", [])
            if isinstance(raw_style, list) and raw_style:
                style_rows: list[dict[str, str]] = []
                for raw_rule in raw_style:
                    if not isinstance(raw_rule, dict):
                        continue
                    bg_color = str(raw_rule.get("bg_color", "")).strip()
                    fg_color = str(raw_rule.get("fg_color", "")).strip()
                    when = str(raw_rule.get("when", "")).strip()
                    bold = bool(raw_rule.get("bold", False))
                    underline = bool(raw_rule.get("underline", False))
                    italic = bool(raw_rule.get("italic", False))
                    if not when:
                        continue
                    if not bg_color and not fg_color and not (bold or underline or italic):
                        continue
                    style_rule: dict[str, object] = {"when": when}
                    if bg_color:
                        style_rule["bg_color"] = bg_color
                    if fg_color:
                        style_rule["fg_color"] = fg_color
                    if bold:
                        style_rule["bold"] = True
                    if underline:
                        style_rule["underline"] = True
                    if italic:
                        style_rule["italic"] = True
                    style_rows.append(style_rule)
                if style_rows:
                    row["style"] = style_rows
            bindings.append(row)
        for idx, (hotkey, entry) in enumerate(self.ctx.keys.items(), start=1):
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

    def _save_bindings(self, bindings: list[dict[str, object]]) -> None:
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
                raw_style = row.get("style", [])
                if isinstance(raw_style, list) and raw_style:
                    style_rows: list[dict[str, str]] = []
                    for raw_rule in raw_style:
                        if not isinstance(raw_rule, dict):
                            continue
                        bg_color = str(raw_rule.get("bg_color", "")).strip()
                        fg_color = str(raw_rule.get("fg_color", "")).strip()
                        when = str(raw_rule.get("when", "")).strip()
                        bold = bool(raw_rule.get("bold", False))
                        underline = bool(raw_rule.get("underline", False))
                        italic = bool(raw_rule.get("italic", False))
                        if not when:
                            continue
                        if not bg_color and not fg_color and not (bold or underline or italic):
                            continue
                        style_rule: dict[str, object] = {"when": when}
                        if bg_color:
                            style_rule["bg_color"] = bg_color
                        if fg_color:
                            style_rule["fg_color"] = fg_color
                        if bold:
                            style_rule["bold"] = True
                        if underline:
                            style_rule["underline"] = True
                        if italic:
                            style_rule["italic"] = True
                        style_rows.append(style_rule)
                    if style_rows:
                        payload["style"] = style_rows
                hotbar_payload.append(payload)
            hotkey = str(row.get("hotkey", "")).strip().lower()
            if hotkey:
                keys_payload[hotkey] = {"action": target, **({"label": label} if label else {})}
        save_hotbar(self.base_dir, hotbar_payload)
        save_keys(self.base_dir, keys_payload)

    def _hotbar_targets(self) -> list[str]:
        return textual_ui_action_items.hotbar_targets(self)

    def _hotbar_visible(self) -> bool:
        return bool(self._hotbar_targets())

    def _normalize_hotbar_index(self) -> None:
        targets = self._hotbar_targets()
        if not targets:
            self.hotbar_selected_index = 0
            return
        self.hotbar_selected_index = max(0, min(self.hotbar_selected_index, len(targets) - 1))

    def _selected_hotbar_target(self) -> str:
        targets = self._hotbar_targets()
        if not targets:
            return ""
        self._normalize_hotbar_index()
        return str(targets[self.hotbar_selected_index])

    def _cycle_hotbar(self, delta: int) -> bool:
        targets = self._hotbar_targets()
        if not targets:
            return False
        self._normalize_hotbar_index()
        self.hotbar_selected_index = (self.hotbar_selected_index + delta) % len(targets)
        self._mark_state_dirty()
        self._refresh_search_display()
        return True

    def _toggle_hotbar_target_from_palette(self, target: str) -> bool:
        value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
        if not value:
            return False
        action = self.actions.get(value)
        if action is not None and action.scope != "target":
            self._log(
                f"{value} cannot be on hotbar: only target-scope actions are eligible",
                "warn",
            )
            return False
        bindings: list[dict[str, object]] = [dict(row) for row in self.custom_hotkeys]
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
                        self._save_bindings(bindings)
                        self.custom_hotkeys = bindings
                        self._normalize_hotbar_index()
                        self._mark_state_dirty()
                        self._refresh_search_display()
                        return True
                    except (OSError, TypeError, ValueError) as exc:
                        self._show_runtime_error("save bindings", exc)
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
            self._save_bindings(bindings)
            self.custom_hotkeys = bindings
        except (OSError, TypeError, ValueError) as exc:
            self._show_runtime_error("save bindings", exc)
            return False
        self._normalize_hotbar_index()
        self._mark_state_dirty()
        self._refresh_search_display()
        return True

    def _target_is_hotbar(self, target: str) -> bool:
        value = textual_ui_action_dispatch.normalize_action_target(str(target or ""))
        if not value:
            return False
        return value in {textual_ui_action_dispatch.normalize_action_target(t) for t in self._hotbar_targets()}

    def _hotbar_target_label(self, target: str) -> str:
        value = str(target or "").strip()
        if not value:
            return ""
        custom_label = self._hotbar_target_custom_label_map().get(value, "")
        if custom_label:
            return custom_label
        if value.startswith("tab:"):
            return value.split(":", 1)[1]
        if value.startswith("tab."):
            return value.split(".", 1)[1]
        action_id = value.split(":", 1)[1] if value.startswith("action:") else value
        for aid, label in self._valid_action_items():
            if aid == action_id:
                return self._label_plain(label)
        if action_id in self.actions:
            return self.actions[action_id].label
        return value

    def _apply_side_tab_state_to_widgets(self) -> None:
        textual_ui_tabs_state.apply_side_tab_state_to_widgets(self)

    def _cycle_tabs(self, reverse: bool = False) -> None:
        textual_ui_tabs_state.cycle_tabs(
            self,
            reverse=reverse,
            side_top_tabs=SIDE_TOP_TABS,
            side_child_tabs=SIDE_CHILD_TABS,
        )

    def _named_filters_sig(self) -> str:
        return textual_ui_query_runtime.named_filters_sig(self.ctx.named_filters)

    def _query_eval(
        self, query_text: str
    ) -> tuple[bool, str, str | None, Callable[[ProjectRow], bool], str | None]:
        return textual_ui_query_runtime.query_eval(
            self,
            query_text,
            named_filters=self.ctx.named_filters,
            base_dir=self.base_dir,
            query_uses_filter_syntax=query_uses_filter_syntax,
            resolve_filter_expression=resolve_filter_expression,
            compile_filter_expr=compile_filter_expr,
        )

    def _queue_query_apply(self) -> None:
        textual_ui_query_runtime.queue_query_apply(self)

    def _flush_query_apply_if_due(self) -> None:
        textual_ui_query_runtime.flush_query_apply_if_due(self)

    def _refresh_search_display(self) -> None:
        textual_ui_query_runtime.refresh_search_display(
            self,
            color_interactive_hex=COLOR_INTERACTIVE_HEX,
            color_nav_hex=COLOR_NAV_HEX,
            color_archive_hex=COLOR_ARCHIVE_HEX,
            color_success_hex=COLOR_SUCCESS_HEX,
            color_error_hex=COLOR_ERROR_HEX,
            color_warn_hex=COLOR_WARN_HEX,
            mode_active=MODE_ACTIVE,
        )

    def _property_count_map(self) -> dict[str, int]:
        return textual_ui_side_content.property_count_map(
            self,
            all_property_defs=all_property_defs,
        )

    def _tag_count_map(self, limit: int = 12) -> list[tuple[str, int]]:
        return textual_ui_side_content.tag_count_map(self, limit=limit)

    def _global_info_lines(self) -> list[str]:
        return textual_ui_side_content.global_info_lines(self)

    def _cheat_columns(self) -> tuple[str, str]:
        return textual_ui_side_content.cheat_columns(
            self,
            all_property_defs=all_property_defs,
        )

    def _action_context_lines(self) -> list[str]:
        return textual_ui_side_content.action_context_lines(self, base_dir=self.base_dir)

    def _stats_and_context_lines(self) -> list[str]:
        return textual_ui_side_content.stats_and_context_lines(self, base_dir=self.base_dir)

    def _preview_entries(self, path: Path, limit: int | None = None) -> list[str]:
        if limit is None:
            limit = self._preview_entries_limit()
        return textual_ui_side_content.preview_entries(path, limit=limit)

    def _preview_entries_limit(self) -> int:
        try:
            raw = int(self.table_behavior.get("preview_entries_limit", 8))
        except (TypeError, ValueError):
            raw = 8
        return max(PREVIEW_ENTRIES_LIMIT_MIN, min(PREVIEW_ENTRIES_LIMIT_MAX, raw))

    @staticmethod
    def _esc(text: object) -> str:
        return str(text).replace("[", "\\[").replace("]", "\\]")

    @staticmethod
    def _run_cmd(cwd: Path, *cmd: str) -> tuple[str, str | None]:
        return textual_ui_side_content.run_cmd(cwd, *cmd)

    def _table_visible_columns_for_view(
        self, view_mode: str
    ) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for col in self._table_columns_for_view(view_mode):
            if not bool(col.get("enabled", True)):
                continue
            out.append(col)
        return out

    def _table_columns_for_view(self, view_mode: str) -> list[dict[str, object]]:
        v = str(view_mode).strip()
        if v not in TABLE_COLUMN_VIEWS:
            v = MODE_ACTIVE
        cols = self.table_columns_by_view.get(v)
        if isinstance(cols, list):
            return cols
        fallback = _merge_table_columns_for_view(v, [])
        self.table_columns_by_view[v] = fallback
        return fallback

    def _refresh_data(self) -> None:
        # Keep UI responsive: never do a full filesystem/git scan on the UI thread.
        # Use whatever is currently cached, then warm/refresh cache in background.
        self._reload_rows_from_cache()
        self._start_cache_refresh("refresh requested", force=True)

    def _rows_for_view(self, archived: bool) -> list[ProjectRow]:
        return self.archived_rows if archived else self.active_rows

    def _invalidate_current_rows_cache(self) -> None:
        self._rows_state_token += 1

    def _match_query_lower(self, row: ProjectRow, q_lower: str) -> bool:
        return textual_ui_row_helpers.match_query_lower(row, q_lower)

    def _same_path(self, a: Path | None, b: Path | None) -> bool:
        return textual_ui_row_helpers.same_path(a, b)

    def _has_open_pane(self, path: Path) -> bool:
        return textual_ui_row_helpers.has_open_pane(path, self.open_pane_count_by_project)

    def _dynamic_indicator_matches(self, key: str, row: ProjectRow) -> bool:
        pdef = next((p for p in self.ctx.property_defs if str(p.key) == key), None)
        if pdef is None or not pdef.queries:
            return False
        path_query_types = {"tmux_open_panes", "tmux_editor_commands", "sqlite_recent_paths"}
        view = MODE_ARCHIVE if row.archived else MODE_ACTIVE
        ttl_s = pdef.cache_ttl_for_view(view)
        cached = self.dynamic_indicator_cache.get(key)
        if cached is None or textual_ui_indicator_queries.cache_due(cached[0]):
            paths: set[Path] = set()
            for query in pdef.queries:
                qtype = str(query.get("type", "")).strip()
                if qtype in path_query_types:
                    paths.update(textual_ui_indicator_queries.evaluate_query_paths(self, query))
            self.dynamic_indicator_cache[key] = (time.time() + ttl_s, paths)
            cached = self.dynamic_indicator_cache[key]
        if row.path in cached[1]:
            return True
        row_cache_key = (key, row.path)
        row_cached = self.dynamic_indicator_row_cache.get(row_cache_key)
        if row_cached is not None and not textual_ui_indicator_queries.cache_due(row_cached[0]):
            return bool(row_cached[1])
        matched = False
        for query in pdef.queries:
            qtype = str(query.get("type", "")).strip()
            if qtype in path_query_types:
                continue
            if textual_ui_indicator_queries.evaluate_query_match(self, row, query):
                matched = True
                break
        self.dynamic_indicator_row_cache[row_cache_key] = (
            time.time() + ttl_s,
            matched,
        )
        return matched

    def _apply_dynamic_properties_to_row(self, row: ProjectRow) -> None:
        dynamic_keys = {str(p.key) for p in self.ctx.property_defs if p.queries}
        props = [p for p in row.properties if p not in dynamic_keys]
        for key in sorted(dynamic_keys):
            if self._dynamic_indicator_matches(key, row):
                props.append(key)
        row.properties = normalize_property_keys(props)
        refresh_row_caches(row)

    def _apply_dynamic_properties_all_rows(self) -> None:
        self.dynamic_indicator_cache = {}
        now = time.time()
        self.dynamic_indicator_row_cache = {
            k: v for k, v in self.dynamic_indicator_row_cache.items() if v[0] > now
        }
        for row in self.active_rows:
            self._apply_dynamic_properties_to_row(row)
        for row in self.archived_rows:
            self._apply_dynamic_properties_to_row(row)
        self._invalidate_current_rows_cache()

    def _queue_dynamic_property_refresh(self, paths: list[Path]) -> None:
        textual_ui_dynamic_props.queue_dynamic_property_refresh(self, paths)
        if paths:
            self.dynamic_property_refresh_next_due_at = 0.0

    def _run_dynamic_property_refresh_tick(self) -> None:
        now = time.time()
        if now < float(self.dynamic_property_refresh_next_due_at):
            return
        textual_ui_dynamic_props.run_dynamic_property_refresh_tick(
            self,
            batch_size=self._dynamic_property_refresh_batch_size(),
        )
        if self.dynamic_property_refresh_queue:
            self.dynamic_property_refresh_next_due_at = (
                now + self._dynamic_property_refresh_interval_s()
            )
        else:
            self.dynamic_property_refresh_next_due_at = 0.0

    def _dynamic_property_refresh_batch_size(self) -> int:
        view = MODE_ACTIVE if self.view_mode == MODE_ACTIVE else MODE_ARCHIVE
        batch_size = 24
        for pdef in self.ctx.property_defs:
            if not pdef.queries:
                continue
            if not isinstance(pdef.cache_profiles_by_view, dict):
                continue
            profile = pdef.cache_profiles_by_view.get(view, {})
            if not isinstance(profile, dict):
                continue
            try:
                batch_size = max(
                    batch_size,
                    max(1, int(profile.get("update_batch_size", batch_size))),
                )
            except (TypeError, ValueError):
                continue
        return batch_size

    def _dynamic_property_refresh_interval_s(self) -> float:
        view = MODE_ACTIVE if self.view_mode == MODE_ACTIVE else MODE_ARCHIVE
        interval_s: float | None = None
        for pdef in self.ctx.property_defs:
            if not pdef.queries:
                continue
            if not isinstance(pdef.cache_profiles_by_view, dict):
                continue
            profile = pdef.cache_profiles_by_view.get(view, {})
            if not isinstance(profile, dict):
                continue
            try:
                candidate = max(0.05, float(profile.get("update_interval_s", 0.25)))
                interval_s = candidate if interval_s is None else min(interval_s, candidate)
            except (TypeError, ValueError):
                continue
        return interval_s if interval_s is not None else 0.25

    def _find_row(self, path: Path) -> tuple[list[ProjectRow], int] | None:
        for rows in (self.active_rows, self.archived_rows):
            for idx, row in enumerate(rows):
                if row.path == path:
                    return rows, idx
        return None

    def _upsert_row_local(self, row: ProjectRow, *, invalidate_cache: bool = True) -> None:
        self._apply_dynamic_properties_to_row(row)
        now_ts = int(time.time())
        if row.last_cached_ts <= 0:
            row.last_cached_ts = now_ts
        if row.last_reconciled_ts <= 0:
            row.last_reconciled_ts = row.last_cached_ts
        target_rows = self._rows_for_view(row.archived)
        for idx, cur in enumerate(target_rows):
            if cur.path == row.path:
                row.stale = False
                row.cache_age_s = 0
                target_rows[idx] = row
                if invalidate_cache:
                    self._invalidate_current_rows_cache()
                return
        row.stale = False
        row.cache_age_s = 0
        target_rows.append(row)
        if invalidate_cache:
            self._invalidate_current_rows_cache()

    def _remove_paths_local(self, paths: list[Path]) -> None:
        remove = {p.resolve() for p in paths}
        self.active_rows = [
            r for r in self.active_rows if r.path.resolve() not in remove
        ]
        self.archived_rows = [
            r for r in self.archived_rows if r.path.resolve() not in remove
        ]
        self.multi_selected = {
            p for p in self.multi_selected if p.resolve() not in remove
        }
        if (
            self.selected_path is not None
            and self.selected_path.resolve() in remove
        ):
            self.selected_path = None
        self._invalidate_current_rows_cache()

    def _touch_rows_cache(
        self, rows: list[ProjectRow], removed: list[Path] | None = None
    ) -> None:
        textual_ui_cache_state.touch_rows_cache(
            self,
            base_dir=self.base_dir,
            rows=rows,
            removed=removed,
        )

    def _set_opened_ts_local(self, path: Path, opened_ts: int) -> None:
        try:
            cache_set_opened_ts(self.base_dir, path, opened_ts)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return

    def _mark_row_active(self, path: Path) -> None:
        opened_ts = int(time.time())
        self._set_opened_ts_local(path, opened_ts)
        try:
            hit = self._find_row(path)
            if hit is None:
                return
            rows, idx = hit
            rows[idx].opened_ts = opened_ts
            rows[idx].stale = False
            rows[idx].cache_age_s = 0
            self._touch_rows_cache([rows[idx]])
        except (IndexError, AttributeError, TypeError, ValueError):
            return

    def _move_opened_ts_local(self, src: Path, dst: Path) -> None:
        try:
            cache_move_opened_ts(self.base_dir, src, dst)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return

    def _reload_rows_from_cache(self) -> bool:
        return textual_ui_cache_state.reload_rows_from_cache(
            self,
            base_dir=self.base_dir,
            cache_max_age_s=CACHE_MAX_AGE_S,
        )

    def _start_cache_refresh(self, reason: str, force: bool = False) -> None:
        textual_ui_cache_refresh.start_cache_refresh(
            self,
            base_dir=self.base_dir,
            cache_max_age_s=CACHE_MAX_AGE_S,
            reason=reason,
            force=force,
        )

    def _on_cache_refresh_done(self, outcome: CacheRefreshOutcome) -> None:
        textual_ui_cache_refresh.on_cache_refresh_done(
            self,
            base_dir=self.base_dir,
            outcome=outcome,
        )

    def _request_tag_sync(self, reason: str) -> None:
        textual_ui_sync.request_tag_sync(self, base_dir=self.base_dir, reason=reason)

    def _on_tag_sync_done(self, reason: str, err: str | None) -> None:
        textual_ui_sync.on_tag_sync_done(self, reason=reason, err=err)

    def _maybe_refresh_cache(self) -> None:
        textual_ui_sync.maybe_refresh_cache(self)

    def _workspace_quick_signature(self) -> str:
        return textual_ui_sync.workspace_quick_signature(
            base_dir=self.base_dir,
            archive_dir_name=ARCHIVE_DIR_NAME,
            packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
        )

    def _cached_top_active_names(self) -> set[str]:
        return textual_ui_workspace_guard.cached_top_active_names(
            base_dir=self.base_dir,
            active_rows=self.active_rows,
        )

    def _quick_active_dir_names(self) -> set[str]:
        return textual_ui_workspace_guard.quick_active_dir_names(base_dir=self.base_dir)

    def _startup_quick_active_dir_check(self) -> None:
        textual_ui_workspace_guard.startup_quick_active_dir_check(
            self,
            level_info=LEVEL_INFO,
        )

    def _mode_has_stale_rows(self, mode: str) -> bool:
        return textual_ui_reconcile.mode_has_stale_rows(self, mode)

    def _effective_reconcile_wait_s(self, mode: str) -> float:
        return textual_ui_reconcile.effective_reconcile_wait_s(self, mode)

    def _effective_reconcile_parallelism(self, mode: str) -> int:
        return textual_ui_reconcile.effective_reconcile_parallelism(self, mode)

    def _effective_reconcile_batch_size(self, mode: str) -> int:
        return textual_ui_reconcile.effective_reconcile_batch_size(self, mode)

    def _bump_row_usage(self, path: Path | None, weight: float = 1.0) -> None:
        textual_ui_reconcile.bump_row_usage(self, path, weight=weight)

    def _decay_row_usage(self) -> None:
        textual_ui_reconcile.decay_row_usage(self)

    def _flush_reconcile_usage_if_due(self) -> None:
        textual_ui_reconcile.flush_reconcile_usage_if_due(
            self,
            base_dir=self.base_dir,
            cache_save_reconcile_usage=cache_save_reconcile_usage,
        )

    def _pick_reconcile_candidates(
        self, mode: str, batch_size: int
    ) -> list[ProjectRow]:
        return textual_ui_reconcile.pick_reconcile_candidates(
            self,
            mode,
            batch_size,
            mode_active=MODE_ACTIVE,
            now_ts=int(time.time()),
            random_choices=random.choices,
        )

    def _queue_reconcile_request(
        self, mode: str, reason: str, paths: list[Path], priority: int
    ) -> None:
        textual_ui_reconcile_worker.queue_reconcile_request(
            self,
            mode=mode,
            reason=reason,
            paths=paths,
            priority=priority,
        )

    def _run_next_reconcile_from_queue(self) -> None:
        textual_ui_reconcile_worker.run_next_reconcile_from_queue(self)

    def _start_reconcile_rows(
        self, mode: str, reason: str, paths: list[Path]
    ) -> None:
        textual_ui_reconcile_worker.start_reconcile_rows(self, mode, reason, paths)

    def _record_reconcile_recent(self, kind: str, label: str) -> None:
        textual_ui_reconcile_worker.record_reconcile_recent(self, kind, label)

    def _on_reconcile_rows_done(
        self,
        mode: str,
        reason: str,
        refreshed_rows: list[ProjectRow],
        removed_paths: list[Path],
        failed: int,
        fatal_error: str = "",
    ) -> None:
        textual_ui_reconcile_worker.on_reconcile_rows_done(
            self,
            mode=mode,
            reason=reason,
            refreshed_rows=refreshed_rows,
            removed_paths=removed_paths,
            failed=failed,
            fatal_error=fatal_error,
            base_dir=self.base_dir,
            archive_dir_name=ARCHIVE_DIR_NAME,
            mode_active=MODE_ACTIVE,
            mode_archive=MODE_ARCHIVE,
            level_warn=LEVEL_WARN,
            is_under=core_utils.is_under,
        )

    def _maybe_run_micro_reconcile(self) -> None:
        if self.fast_exit_requested:
            self._set_reconcile_skip_reason("fast exit")
            return
        self._maybe_refresh_metadata_health()
        self._run_dynamic_property_refresh_tick()
        if self._critical_job_active():
            self._set_reconcile_skip_reason(
                f"blocked by critical job ({self._critical_job_label()})"
            )
            return
        if self.cache_worker_running or self.reconcile_worker_running:
            if self.cache_worker_running:
                self._set_reconcile_skip_reason("blocked by cache refresh")
            else:
                self._set_reconcile_skip_reason("blocked by reconcile worker")
            return
        self._decay_row_usage()
        now = time.time()
        for mode in (MODE_ACTIVE, MODE_ARCHIVE):
            cfg = self.reconcile_config.get(mode, {})
            if not bool(cfg.get("enabled", True)):
                continue
            if self._mode_has_stale_rows(mode):
                due_now = float(self.reconcile_next_due.get(mode, now))
                if due_now > now:
                    self.reconcile_next_due[mode] = now
        due_modes: list[str] = []
        for mode in (MODE_ACTIVE, MODE_ARCHIVE):
            cfg = self.reconcile_config.get(mode, {})
            if not bool(cfg.get("enabled", True)):
                continue
            if now >= float(self.reconcile_next_due.get(mode, now + 9999)):
                due_modes.append(mode)
        if not due_modes:
            self._set_reconcile_skip_reason("not due")
            return
        mode = sorted(
            due_modes, key=lambda m: float(self.reconcile_next_due.get(m, now))
        )[0]
        batch_size = self._effective_reconcile_batch_size(mode)
        rows = self._pick_reconcile_candidates(mode, batch_size)
        if not rows:
            interval_s = self._effective_reconcile_wait_s(mode)
            self.reconcile_next_due[mode] = now + interval_s
            self._set_reconcile_skip_reason(f"no candidates for {mode}")
            return
        self._set_reconcile_skip_reason(f"running {mode} micro batch={len(rows)}")
        self._start_reconcile_rows(mode, "micro", [r.path for r in rows])

    def _maybe_run_hook_refresh(self) -> None:
        if self.fast_exit_requested:
            return
        cfg = getattr(self.ctx, "hook_refresh_config", None)
        if cfg is None or not bool(getattr(cfg, "enabled", False)):
            return
        worker = getattr(cfg, "worker", None)
        skip_when_busy = bool(getattr(worker, "skip_when_busy", True))
        if skip_when_busy and (
            self._critical_job_active()
            or self.cache_worker_running
            or self.reconcile_worker_running
        ):
            return
        from ..hooks.refresh import dispatch_refresh_tui
        from ..hooks.snapshot import snapshot_target

        rows = self.active_rows if self.view_mode == MODE_ACTIVE else self.archived_rows
        if not rows:
            return
        now = time.time()
        candidates: list[tuple[object, object]] = []
        for (timing, _event), specs in self.ctx.hook_specs.items():
            if timing != "post":
                continue
            for spec in specs:
                if not getattr(spec, "enabled", False):
                    continue
                if not getattr(spec, "refresh_enabled", False):
                    continue
                if spec.views and self.view_mode not in spec.views:
                    continue
                min_interval = float(getattr(spec, "refresh_min_interval_s", 60.0))
                for row in rows:
                    if spec.event == "tag_change" and not row.tags:
                        continue
                    last = self.hook_refresh_last.get((row.path, spec.name), 0.0)
                    if last + min_interval > now:
                        continue
                    candidates.append((row, spec))
        if not candidates:
            return
        batch_size = max(1, int(getattr(worker, "batch_size", 4)))
        candidates.sort(key=lambda rs: self.hook_refresh_last.get((rs[0].path, rs[1].name), 0.0))
        batch = candidates[:batch_size]
        grouped: dict[tuple[str, str], list[object]] = {}
        for row, spec in batch:
            key = (spec.name, spec.event)
            grouped.setdefault(key, []).append(
                snapshot_target(row, dict(row.base_meta if hasattr(row, "base_meta") else {}))
            )
            self.hook_refresh_last[(row.path, spec.name)] = now
        for (spec_name, spec_event), targets in grouped.items():
            dispatch_refresh_tui(
                self,
                targets=targets,
                view=self.view_mode,
                hook_filter=(spec_name,),
                event_filter=(spec_event,),
                source="worker",
                require_refresh_enabled=True,
            )

    def _hooks_refresh_action(self, *, workspace_scope: bool) -> None:
        from ..hooks.refresh import dispatch_refresh_tui
        from ..hooks.snapshot import snapshot_target

        if workspace_scope:
            rows = self.active_rows if self.view_mode == MODE_ACTIVE else self.archived_rows
        else:
            rows = self._target_rows()
        if not rows:
            self._log("hooks refresh skipped: no target", "warn")
            self._refresh_side()
            return
        targets = [
            snapshot_target(r, dict(r.base_meta if hasattr(r, "base_meta") else {}))
            for r in rows
        ]
        dispatch_refresh_tui(
            self,
            targets=targets,
            view=self.view_mode,
            source="tui-action",
            require_refresh_enabled=False,
        )
        self._log(f"hooks refresh requested for {len(targets)} target(s)", "info")
        self._refresh_side()

    def _maybe_refresh_visible_git(self) -> None:
        textual_ui_git_refresh.maybe_refresh_visible_git(self)

    def _git_refresh_profile_name(self) -> str:
        return (
            PROFILE_GIT_REFRESH_ACTIVE
            if self.view_mode == MODE_ACTIVE
            else PROFILE_GIT_REFRESH_ARCHIVE
        )

    def _git_refresh_profile(self) -> dict[str, object]:
        try:
            return cache_profile_config.resolve_cache_profile(
                profile_name=self._git_refresh_profile_name(),
                view=MODE_ACTIVE if self.view_mode == MODE_ACTIVE else MODE_ARCHIVE,
                profile_table=self.ctx.cache_profile_table,
            )
        except ValueError:
            return {}

    def _git_refresh_interval_s(self) -> float:
        profile = self._git_refresh_profile()
        try:
            return max(0.05, float(profile.get("update_interval_s", 0.8)))
        except (TypeError, ValueError):
            return 0.8

    def _git_refresh_min_interval_s(self) -> float:
        profile = self._git_refresh_profile()
        try:
            return max(
                0.05,
                float(profile.get("min_interval_s", profile.get("update_interval_s", 0.5))),
            )
        except (TypeError, ValueError):
            return 0.5

    def _git_refresh_batch_size(self) -> int:
        profile = self._git_refresh_profile()
        try:
            return max(1, int(profile.get("update_batch_size", 8)))
        except (TypeError, ValueError):
            return 8

    def _metadata_health_profile_name(self) -> str:
        return (
            PROFILE_METADATA_HEALTH_ACTIVE
            if self.view_mode == MODE_ACTIVE
            else PROFILE_METADATA_HEALTH_ARCHIVE
        )

    def _metadata_health_profile(self) -> dict[str, object]:
        try:
            return cache_profile_config.resolve_cache_profile(
                profile_name=self._metadata_health_profile_name(),
                view=MODE_ACTIVE if self.view_mode == MODE_ACTIVE else MODE_ARCHIVE,
                profile_table=self.ctx.cache_profile_table,
            )
        except ValueError:
            return {}

    def _metadata_health_interval_s(self) -> float:
        profile = self._metadata_health_profile()
        try:
            return max(0.05, float(profile.get("update_interval_s", 1.0)))
        except (TypeError, ValueError):
            return 1.0

    def _metadata_health_min_interval_s(self) -> float:
        profile = self._metadata_health_profile()
        try:
            return max(
                0.05,
                float(profile.get("min_interval_s", profile.get("update_interval_s", 0.4))),
            )
        except (TypeError, ValueError):
            return 0.4

    def _metadata_health_batch_size(self) -> int:
        profile = self._metadata_health_profile()
        try:
            return max(1, int(profile.get("update_batch_size", 12)))
        except (TypeError, ValueError):
            return 12

    def _metadata_health_ttl_s(self) -> float:
        profile = self._metadata_health_profile()
        try:
            return max(0.2, float(profile.get("cache_ttl_s", 8.0)))
        except (TypeError, ValueError):
            return 8.0

    def _maybe_refresh_metadata_health(self) -> None:
        textual_ui_metadata_health.maybe_refresh_metadata_health(
            self,
            base_meta_health=base_meta_health,
        )

    def _maybe_refresh_worktree_health(self) -> None:
        textual_ui_worktree_health.maybe_refresh_worktree_health(
            self,
            interval_s=UI_TICK_WORKTREE_HEALTH_S,
        )

    def _initial_worktree_health_scan(self) -> None:
        textual_ui_worktree_health.load_initial_health(self)
        self._maybe_refresh_worktree_health()

    def action_dismiss_worktree_health(self) -> None:
        textual_ui_worktree_health.dismiss_worktree_health(self)

    def _action_fix_worktrees(self) -> None:
        textual_ui_worktree_health.action_fix_worktrees(self)

    def _run_family_deworktree_then(
        self,
        followup: str,
        worktrees: list[Path],
        original_paths: list[Path],
    ) -> None:
        from ..workspace.worktree_families import deworktree_family

        try:
            self._busy_start(f"de-worktree before {followup}")
            deworktree_family(self.base_dir, worktrees)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._show_runtime_error(f"de-worktree before {followup}", exc)
            self._busy_stop()
            return
        finally:
            if self._busy_depth > 0:
                self._busy_stop()
        for wt in worktrees:
            try:
                new_row = project_row(wt, archived=False)
                self._upsert_row_local(new_row)
            except _ROW_BUILD_ERRORS:
                pass
        self._log(
            f"de-worktreed {len(worktrees)} worktree(s); proceeding with {followup}",
            "info",
        )
        title, details = self._build_bulk_confirm_payload(followup, original_paths)
        self.push_screen(
            self._confirm_screen_cls(title, details),
            lambda ok: self._on_confirm_bulk(ok, followup, original_paths),
        )

    def _run_family_archive_together(
        self,
        parent_path: Path,
        worktrees: list[Path],
    ) -> None:
        from ..workspace.worktree_families import archive_family_together

        def _archive(base_dir: Path, src: Path) -> Path:
            return archive_move_internal(
                base_dir, src, sync_tags=False, allow_worktree_children=True
            )

        try:
            self._busy_start("archive family together")
            archived_parent, archived_worktrees = archive_family_together(
                self.base_dir, parent_path, worktrees, archive_move=_archive
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self._show_runtime_error("archive family together", exc)
            return
        finally:
            if self._busy_depth > 0:
                self._busy_stop()
        moved = [parent_path, *worktrees]
        self._remove_paths_local(moved)
        for archived in (archived_parent, *archived_worktrees):
            try:
                self._upsert_row_local(self._build_archived_row_from_entry(archived))
            except _ROW_BUILD_ERRORS:
                pass
        self._request_tag_sync("archive family together")
        self._touch_rows_cache([], removed=moved)
        self._start_cache_refresh("archive family together", force=False)
        self._log(
            f"archived family: {parent_path.name} + {len(worktrees)} worktree(s)",
            "info",
        )
        self._refresh_table()
        self._refresh_side()

    def _on_metadata_health_refresh_done(
        self,
        updated: list[tuple[Path, str, float]],
    ) -> None:
        textual_ui_metadata_health.on_metadata_health_refresh_done(self, updated)

    def _start_git_refresh(self, paths: list[Path], reason: str) -> None:
        textual_ui_git_refresh.start_git_refresh(self, paths, reason)

    def _on_git_refresh_done(
        self, updated: list[tuple[Path, str, str, int]]
    ) -> None:
        textual_ui_git_refresh.on_git_refresh_done(self, updated)

    def _start_probe_open_panes(self) -> None:
        textual_ui_pane_probe.start_probe_open_panes(self)

    def _on_probe_open_panes_done(self, mapping: dict[Path, list[PaneRef]]) -> None:
        textual_ui_pane_probe.on_probe_open_panes_done(self, mapping)

    def _pane_probe_desired_interval_s(self) -> float:
        return textual_ui_pane_probe.pane_probe_desired_interval_s(self)

    def _pane_probe_profile_name(self) -> str:
        return (
            PROFILE_PANE_PROBE_ACTIVE
            if self.view_mode == MODE_ACTIVE
            else PROFILE_PANE_PROBE_ARCHIVE
        )

    def _pane_probe_profile(self) -> dict[str, object]:
        try:
            return cache_profile_config.resolve_cache_profile(
                profile_name=self._pane_probe_profile_name(),
                view=MODE_ACTIVE if self.view_mode == MODE_ACTIVE else MODE_ARCHIVE,
                profile_table=self.ctx.cache_profile_table,
            )
        except ValueError:
            return {}

    def _pane_probe_project_scan_limit(self) -> int:
        profile = self._pane_probe_profile()
        try:
            return max(1, int(profile.get("update_batch_size", 400)))
        except (TypeError, ValueError):
            return 400

    def _pane_probe_profile_min_interval_s(self) -> float:
        probe_profile = self._pane_probe_profile()
        try:
            return max(
                0.05,
                float(
                    probe_profile.get(
                        "min_interval_s",
                        probe_profile.get("update_interval_s", 0.5),
                    )
                ),
            )
        except (TypeError, ValueError):
            return 0.5

    def _pane_probe_profile_slow_interval_s(self) -> float:
        probe_profile = self._pane_probe_profile()
        try:
            return max(0.05, float(probe_profile.get("update_interval_s", 6.0)))
        except (TypeError, ValueError):
            return 6.0

    def _pane_probe_profile_fast_interval_s(self) -> float:
        min_interval_s = self._pane_probe_profile_min_interval_s()
        slow_interval_s = self._pane_probe_profile_slow_interval_s()
        return min(min_interval_s, slow_interval_s)

    def _maybe_probe_open_panes(self) -> None:
        textual_ui_pane_probe.maybe_probe_open_panes(self)

    def _all_tags(self) -> list[str]:
        return textual_ui_rows_view.all_tags(self)

    def _current_rows(self) -> list[ProjectRow]:
        return textual_ui_rows_view.current_rows(self, mode_active=MODE_ACTIVE)

    def _selected_row(self) -> ProjectRow | None:
        return textual_ui_rows_view.selected_row(self)

    def _move_selection(self, delta: int) -> ProjectRow | None:
        return textual_ui_rows_view.move_selection(
            self,
            delta,
            widget_projects=WIDGET_PROJECTS,
        )

    def _target_rows(self) -> list[ProjectRow]:
        return textual_ui_rows_view.target_rows(self)

    def _wip_rows_sorted(self) -> list[ProjectRow]:
        return textual_ui_rows_view.wip_rows_sorted(self)

    def _normalize_query_cursor(self) -> None:
        textual_ui_query_edit.normalize_query_cursor(self)

    def _reset_query_completion(self) -> None:
        textual_ui_query_edit.reset_query_completion(self)

    def _query_token_bounds(self, value: str) -> tuple[int, int, str]:
        return textual_ui_query_edit.query_token_bounds(self, value)

    def _completion_counts(
        self,
    ) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        return textual_ui_query_edit.completion_counts(self)

    def _query_completion_candidates(self, token: str) -> list[str]:
        return textual_ui_query_edit.query_completion_candidates(self, token)

    def _apply_query_completion(self, forward: bool) -> None:
        textual_ui_query_edit.apply_query_completion(self, forward)

    def _open_wip_index(self, idx: int) -> None:
        rows = self._wip_rows_sorted()
        if idx < 1 or idx > len(rows):
            self._log(f"wip quick open: no entry {idx}", "warn")
            self._refresh_side()
            return
        self.exit(("open", rows[idx - 1].path, []))

    def _scroll_table_x(self, delta: int) -> None:
        textual_ui_table_nav.scroll_table_x(
            self,
            delta,
            widget_projects=WIDGET_PROJECTS,
        )

    def _table_is_active_focus(self) -> bool:
        return textual_ui_table_nav.table_is_active_focus(
            self,
            widget_projects=WIDGET_PROJECTS,
        )


    def _clear_project_row_highlight_suspend(self) -> None:
        self._suspend_project_row_highlight = False

    def _selected_readme_path(self) -> Path | None:
        return textual_ui_notes_paths.selected_readme_path(self)

    def _notes_template_context(self, row: ProjectRow) -> dict[str, str]:
        return textual_ui_notes_paths.notes_template_context(
            self,
            row,
            base_dir=self.base_dir,
            fmt_ymd=fmt_ymd,
        )

    def _resolve_notes_path_for_row(self, row: ProjectRow) -> Path:
        return textual_ui_notes_paths.resolve_notes_path_for_row(
            self,
            row,
            base_dir=self.base_dir,
        )

    def _selected_notes_path(self) -> Path | None:
        return textual_ui_notes_paths.selected_notes_path(self)


    def _update_readme_tab_state(self) -> None:
        textual_ui_side_tabs.update_readme_tab_state(self)

    def _open_editor_for_path(
        self,
        path: Path,
        *,
        wait: bool = False,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        textual_ui_side_effects.open_editor_for_path(
            self,
            path,
            wait=wait,
            on_done=on_done,
        )

    def _start_managed_process(
        self,
        argv: list[str],
        *,
        cwd: Path,
        label: str,
        command_display: str,
        wait: bool,
        terminate_on_quit: bool,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        proc = subprocess.Popen(argv, cwd=str(cwd))
        info = ManagedProcess(
            pid=int(proc.pid),
            label=label,
            command=command_display,
            cwd=cwd,
            started_ts=time.time(),
            wait_mode=wait,
            terminate_on_quit=terminate_on_quit,
        )
        with self._managed_processes_lock:
            self.managed_processes.append(info)
        self._refresh_side()

        def _waiter() -> None:
            rc = proc.wait()

            def _done() -> None:
                ended_ts = time.time()
                with self._managed_processes_lock:
                    for row in self.managed_processes:
                        if row.pid == info.pid and row.ended_ts <= 0:
                            row.returncode = int(rc)
                            row.ended_ts = ended_ts
                            break
                if self._wait_process_modal_pid == info.pid:
                    self._wait_process_modal_pid = None
                    try:
                        self.pop_screen()
                    except WIDGET_API_ERRORS:
                        pass
                if on_done is not None:
                    on_done()
                self._refresh_side()

            self.call_from_thread(_done)

        threading.Thread(target=_waiter, daemon=True).start()

        if wait:
            def _show_wait() -> None:
                if self._process_running(info.pid):
                    self._wait_process_modal_pid = info.pid
                    details = (
                        f"[cyan]label[/]: {self._esc(label)}\n"
                        f"[cyan]pid[/]: {info.pid}\n"
                        f"[cyan]cwd[/]: {self._esc(cwd)}\n"
                        f"[cyan]command[/]: [dim]{self._esc(command_display)}[/]"
                    )
                    self.push_screen(self._process_wait_screen_cls("Waiting for process", details))

            self.set_timer(0.25, _show_wait)

    def _start_managed_shell_command(
        self,
        command: str,
        *,
        cwd: Path,
        label: str,
        wait: bool,
        terminate_on_quit: bool,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self._start_managed_process(
            ["sh", "-lc", command],
            cwd=cwd,
            label=label,
            command_display=command,
            wait=wait,
            terminate_on_quit=terminate_on_quit,
            on_done=on_done,
        )

    def _process_running(self, pid: int) -> bool:
        with self._managed_processes_lock:
            return any(p.pid == pid and p.ended_ts <= 0 for p in self.managed_processes)

    def _running_terminating_processes(self) -> list[ManagedProcess]:
        with self._managed_processes_lock:
            return [p for p in self.managed_processes if p.ended_ts <= 0 and p.terminate_on_quit]

    def _terminate_running_managed_processes(self) -> None:
        running = self._running_terminating_processes()
        for proc in running:
            try:
                os.kill(proc.pid, 15)
            except OSError:
                continue

    def _managed_process_info_lines(self) -> list[str]:
        with self._managed_processes_lock:
            rows = list(self.managed_processes)
        if not rows:
            return ["[dim]no managed processes[/]"]
        out: list[str] = []
        running = [p for p in rows if p.ended_ts <= 0]
        done = [p for p in rows if p.ended_ts > 0]
        out.append(f"running: {len(running)}  done: {len(done)}")
        out.append("[dim]on quit, running managed processes are terminated[/]")
        for proc in sorted(rows, key=lambda p: p.started_ts, reverse=True)[:20]:
            status = "running" if proc.ended_ts <= 0 else f"done rc={proc.returncode}"
            out.append(
                f"[{self._esc(str(proc.pid))}] {self._esc(proc.label)} - {status}"
            )
            out.append(f"  cwd: {self._esc(proc.cwd)}")
            out.append(f"  cmd: [dim]{self._esc(proc.command)}[/]")
        return out

    def _readme_button_actions(self) -> list[tuple[str, str]]:
        return textual_ui_side_effects.readme_button_actions(self._selected_row())

    def _notes_button_actions(self) -> list[tuple[str, str]]:
        return textual_ui_side_effects.notes_button_actions(
            self._selected_row(),
            resolve_notes_path_for_row=self._resolve_notes_path_for_row,
        )

    def _run_notes_command(
        self,
        command_template: str,
        note_path: Path,
        row: ProjectRow,
        op: str,
    ) -> None:
        textual_ui_side_tabs.run_notes_command(
            self,
            command_template,
            note_path,
            row,
            op,
            base_dir=self.base_dir,
        )

    def _run_notes_button_action(self, action_id: str) -> None:
        textual_ui_side_tabs.run_notes_button_action(
            self,
            action_id,
            level_warn=LEVEL_WARN,
        )

    def _run_readme_button_action(self, action_id: str) -> None:
        textual_ui_side_tabs.run_readme_button_action(
            self,
            action_id,
            level_warn=LEVEL_WARN,
        )

    def _handle_side_markdown_link(self, href: str) -> None:
        textual_ui_side_effects.handle_side_markdown_link(
            href,
            side_selected_tab=self.side_selected_tab,
            side_readme_source_path=self.side_readme_source_path,
            side_notes_source_path=self.side_notes_source_path,
            show_runtime_error=self._show_runtime_error,
            set_runtime_status=self._set_runtime_status,
            level_warn=LEVEL_WARN,
        )

    def _refresh_settings_table(self) -> None:
        textual_ui_settings_panel.refresh_settings_table(self)

    def _update_open_settings_details(
        self, rows: list[tuple[str, str, str]] | None = None
    ) -> None:
        textual_ui_settings_panel.update_open_settings_details(self, rows)

    def _table_pin_wip_top_enabled(self) -> bool:
        return bool(self.table_behavior.get("pin_wip_top", False))

    def _table_side_width_pct(self) -> int:
        try:
            raw = int(self.table_behavior.get("side_width_pct", 33))
        except (TypeError, ValueError):
            raw = 33
        presets = list(TABLE_SIDE_WIDTH_PRESETS) or [raw]
        return min(presets, key=lambda pct: abs(pct - raw))

    def _table_config_save(self) -> None:
        textual_ui_settings_panel.table_config_save(self, base_dir=self.base_dir)

    def _table_settings_save(self) -> None:
        textual_ui_settings_panel.table_settings_save(self, base_dir=self.base_dir)

    def _table_settings_adjust_width(self, delta: int) -> None:
        textual_ui_settings_panel.table_settings_adjust_width(
            self,
            delta,
            base_dir=self.base_dir,
        )

    def _table_settings_toggle_enabled(self) -> None:
        textual_ui_settings_panel.table_settings_toggle_enabled(self, base_dir=self.base_dir)

    def _open_mode_save(self) -> None:
        textual_ui_settings_panel.open_mode_save(self, base_dir=self.base_dir)

    def _open_mode_rows(self) -> list[tuple[str, str, str]]:
        return textual_ui_settings_panel.open_mode_rows()

    def _open_mode_select_selected(self) -> None:
        textual_ui_settings_panel.open_mode_select_selected(self, base_dir=self.base_dir)

    def _table_settings_reorder(self, delta: int) -> None:
        textual_ui_settings_panel.table_settings_reorder(
            self,
            delta,
            base_dir=self.base_dir,
        )

    def _handle_settings_table_key(self, event: Key) -> bool:
        return textual_ui_settings_panel.handle_settings_table_key(
            self,
            event,
            base_dir=self.base_dir,
        )

    def _edit_global_config_and_reload(self) -> None:
        textual_ui_settings_panel.edit_global_config_and_reload(self, base_dir=self.base_dir)

    def _reload_global_config(self) -> None:
        textual_ui_settings_panel.reload_global_config(self, base_dir=self.base_dir)

    def _global_config_status_text(self) -> str:
        return textual_ui_settings_panel.global_config_status_text(self, base_dir=self.base_dir)

    def _cache_info_lines(self) -> list[str]:
        return textual_ui_side_panel.cache_info_lines(
            self,
            base_dir=self.base_dir,
            cache_schema_version=CACHE_SCHEMA_VERSION,
            cache_max_age_s=CACHE_MAX_AGE_S,
            cache_bg_refresh_s=CACHE_BG_REFRESH_S,
            mode_active=MODE_ACTIVE,
            mode_archive=MODE_ARCHIVE,
            archive_dir_name=ARCHIVE_DIR_NAME,
        )

    def _refresh_selected_details(self, log_success: bool = False) -> None:
        textual_ui_side_panel.refresh_selected_details(self, log_success=log_success)

    def _selected_details_worker(
        self,
        token: int,
        path: Path,
        archived: bool,
        restore_target: Path | None,
        archived_ts: int,
        prev_size_bytes: int,
        prev_size_refresh_count: int,
        log_success: bool,
    ) -> None:
        textual_ui_side_panel.selected_details_worker(
            self,
            token=token,
            path=path,
            archived=archived,
            restore_target=restore_target,
            archived_ts=archived_ts,
            prev_size_bytes=prev_size_bytes,
            prev_size_refresh_count=prev_size_refresh_count,
            log_success=log_success,
        )

    def _on_selected_details_done(
        self,
        token: int,
        path: Path,
        refreshed: ProjectRow | None,
        git_text: str,
        files_text: str,
        err_exc: BaseException | None,
        err_tail: str,
        log_success: bool,
    ) -> None:
        textual_ui_side_panel.on_selected_details_done(
            self,
            token=token,
            path=path,
            refreshed=refreshed,
            git_text=git_text,
            files_text=files_text,
            err_exc=err_exc,
            err_tail=err_tail,
            log_success=log_success,
        )

    def _refresh_wip_bar(self) -> None:
        textual_ui_side_panel.refresh_wip_bar(self)

    def _apply_category(self, row: ProjectRow, suffix: str | None) -> Path | None:
        return textual_ui_selection_events.apply_category(
            row,
            suffix,
            suffixes=self.ctx.suffixes,
        )

    def action_toggle_wip(self) -> None:
        textual_ui_wip_actions.action_toggle_wip(
            self,
            mode_active=MODE_ACTIVE,
            save_base_wip=save_base_wip,
        )

    def action_new_project(self) -> None:
        textual_ui_project_create.action_new_project(
            self,
            base_dir=self.base_dir,
            new_project_screen=NewProjectScreen,
        )

    def _action_new_worktree(self, parent_name: str) -> None:
        textual_ui_project_create.action_new_worktree(
            self,
            base_dir=self.base_dir,
            new_project_screen=NewProjectScreen,
            parent_name=parent_name,
        )

    def _on_new_project_submit(self, payload: dict[str, str | None] | None) -> None:
        textual_ui_project_create.on_new_project_submit(
            self,
            payload,
            base_dir=self.base_dir,
        )

    def action_pick_sort(self) -> None:
        textual_ui_view_actions.action_pick_sort(
            self,
            sort_modes_for_view=_sort_modes_for_view,
            single_choice_screen=SingleChoiceScreen,
        )

    def _on_pick_sort(self, value: str | None) -> None:
        textual_ui_view_actions.on_pick_sort(
            self,
            value,
            sort_modes_for_view=_sort_modes_for_view,
        )

    def action_pick_filters(self) -> None:
        textual_ui_view_actions.action_pick_filters(
            self,
            mode_active=MODE_ACTIVE,
            filter_manage_screen=FilterManageScreen,
        )

    def _on_pick_filters(self, value: str | None) -> None:
        textual_ui_view_actions.on_pick_filters(
            self,
            value,
            normalize_filter_expression=normalize_filter_expression,
        )

    def action_pick_category(self) -> None:
        textual_ui_view_actions.action_pick_category(
            self,
            suffixes=self.ctx.suffixes,
            single_choice_screen=SingleChoiceScreen,
        )

    def _on_pick_category(self, value: str | None) -> None:
        textual_ui_view_actions.on_pick_category(
            self,
            value,
            project_row=project_row,
        )

    def action_toggle_view(self) -> None:
        textual_ui_view_actions.action_toggle_view(
            self,
            normalize_sort_mode_for_view=_normalize_sort_mode_for_view,
        )

    def action_reset_view(self) -> None:
        textual_ui_view_actions.action_reset_view(
            self,
            widget_projects=WIDGET_PROJECTS,
        )


    def _tag_plan_model_for_paths(
        self, paths: list[Path], view_mode: str
    ) -> tuple[list[str], dict[str, str], dict[str, int]]:
        return textual_ui_tag_actions.tag_plan_model_for_paths(self, paths, view_mode)

    def _rename_tag_globally(
        self, old_tag: str, new_tag: str
    ) -> tuple[bool, str, bool]:
        return textual_ui_tag_actions.rename_tag_globally(
            self,
            old_tag,
            new_tag,
            base_dir=self.base_dir,
            save_base_tags=save_base_tags,
        )

    def _delete_tag_globally(self, tag: str) -> tuple[bool, str]:
        return textual_ui_tag_actions.delete_tag_globally(
            self,
            tag,
            base_dir=self.base_dir,
            save_base_tags=save_base_tags,
        )

    def _custom_actions_for_scope(self, scope: str) -> list[tuple[str, str]]:
        return textual_ui_action_items.custom_actions_for_scope(
            self,
            scope,
            color_accent_hex=COLOR_ACCENT_HEX,
        )

    def _hotkey_target_label_map(self) -> dict[str, str]:
        return textual_ui_action_items.hotkey_target_label_map(self)

    def _hotbar_target_custom_label_map(self) -> dict[str, str]:
        return textual_ui_action_items.hotbar_target_custom_label_map(self)

    def _hotbar_target_style_rules_map(self) -> dict[str, list[dict[str, str]]]:
        return textual_ui_action_items.hotbar_target_style_rules_map(self)

    def _resolve_hotbar_target_style(self, target: str) -> dict[str, str]:
        rules = self._hotbar_target_style_rules_map().get(str(target), [])
        if not rules:
            return {}
        return textual_ui_query_context_rules.resolve_style_rules(
            rules,
            row=self._selected_row(),
        )

    def _valid_action_items(self) -> list[tuple[str, str]]:
        return textual_ui_action_items.valid_action_items(
            self,
            color_accent_hex=COLOR_ACCENT_HEX,
            base_meta_issues=base_meta_issues,
        )

    def _label_plain(self, label: str) -> str:
        return textual_ui_action_items.label_plain(label)

    def _action_help_text(self, action_id: str, label: str) -> str:
        return textual_ui_action_items.action_help_text(
            action_id,
            label,
            action_short_help={
                aid: meta.help_text for aid, meta in BUILTIN_ACTIONS.items()
            },
        )

    def _custom_action_by_id(self, cid: str) -> Action | None:
        return textual_ui_action_items.custom_action_by_id(self, cid)

    def _custom_hotkey_target_map(self) -> dict[str, str]:
        return textual_ui_action_items.custom_hotkey_target_map(self)

    def _custom_action_context(
        self,
        row: ProjectRow | None,
        index: int = 0,
        total: int = 1,
    ) -> dict[str, str]:
        return textual_ui_action_items.custom_action_context(
            self,
            row,
            base_dir=self.base_dir,
            fmt_ymd=fmt_ymd,
            index=index,
            total=total,
        )

    def _render_custom_command(
        self, template_text: str, context: dict[str, str]
    ) -> str:
        return textual_ui_action_items.render_custom_command(template_text, context)

    def _run_custom_action(self, action_id: str) -> None:
        textual_ui_action_items.run_custom_action(
            self,
            action_id,
            base_dir=self.base_dir,
            fmt_ymd=fmt_ymd,
        )

    def _preflight_bulk_action(
        self, action: str, paths: list[Path]
    ) -> tuple[list[Path], list[tuple[Path, str]]]:
        return textual_ui_bulk_preflight.preflight_bulk_action(
            action,
            paths,
            base_dir=self.base_dir,
            base_marker_file=BASE_MARKER_FILE,
            legacy_base_marker_file=LEGACY_BASE_MARKER_FILE,
            is_packed_archive_path=is_packed_archive_path,
            packed_archive_dir_name=lambda path: core_utils.packed_archive_dir_name(
                path,
                PACKED_ARCHIVE_SUFFIX,
            ),
            policy_reason_outside_base=_policy_reason_outside_base,
            policy_reason_not_under_archive=_policy_reason_not_under_archive,
            policy_reason_archived_entry=_policy_reason_archived_entry,
            policy_reason_archived_dir=_policy_reason_archived_dir,
            policy_reason_packed_archive=_policy_reason_packed_archive,
        )

    def _preflight_skip_summary(self, skipped: list[tuple[Path, str]]) -> str:
        return textual_ui_bulk_preflight.preflight_skip_summary(skipped)

    def action_pick_tags(self) -> None:
        textual_ui_tag_actions.action_pick_tags(self, tag_plan_screen=TagPlanScreen)

    def _on_pick_tags(self, plan: dict[str, str] | None, paths: list[Path]) -> None:
        textual_ui_tag_actions.on_pick_tags(
            self,
            plan,
            paths,
            base_dir=self.base_dir,
            is_packed_archive_path=is_packed_archive_path,
            load_base_meta=load_base_meta,
            save_base_tags=save_base_tags,
        )

    def action_pick_actions(self) -> None:
        targets = self._target_rows()
        hotkey_map = self._hotkey_target_label_map()

        def with_hotkeys(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for aid, label in items:
                hotkey = hotkey_map.get(aid, "")
                if hotkey:
                    out.append((aid, f"{label} [dim]({self._esc(hotkey)})[/]"))
                else:
                    out.append((aid, label))
            return out

        button_actions = with_hotkeys(
            self._readme_button_actions() + self._notes_button_actions()
        )

        target_actions: list[tuple[str, str]] = [
            ("tags_set", "[white]Tags...[/]"),
            ("reconcile_selection_cache", "[white]Reconcile target cache now[/]"),
        ]
        if self.view_mode == "active":
            target_actions.append(("suffix_set", "[white]Suffix...[/]"))
        for k, v in self.view_config[self.view_mode]["actions"]:
            label = f"[white]{v}[/]"
            if targets and k in {
                "archive",
                "restore",
                "pack",
                "unpack",
                "toggle_pack",
                "delete",
            }:
                runnable, skipped = self._preflight_bulk_action(
                    k, [r.path for r in targets]
                )
                if skipped:
                    label += f" [dim]({len(runnable)}/{len(targets)} ready)[/]"
            target_actions.append((k, label))

        if targets:
            target_actions.append(("rename_item", "[white]Rename item...[/]"))
            has_review_meta = False
            has_legacy_meta = False
            for row in targets:
                issue_codes = {code for _lvl, code, _msg in base_meta_issues(row.path)}
                if issue_codes and not row.packed:
                    has_review_meta = True
                if (
                    ("legacy_only" in issue_codes or "legacy_conflict" in issue_codes)
                    and not row.packed
                ):
                    has_legacy_meta = True
            if has_review_meta:
                target_actions.append(
                    ("review_meta", "[white]Open .base.yaml and review warnings[/]")
                )
            if has_legacy_meta:
                target_actions.append(
                    ("rename_meta_ext", "[white]Rename .base.yml -> .base.yaml[/]")
                )

        global_actions: list[tuple[str, str]] = [
            ("refresh_cache", "[white]Refresh cache[/]"),
            ("full_reconcile", "[white]Full reconcile (force rescan)[/]"),
            ("reconcile_all_cache", "[white]Reconcile all cached rows now[/]"),
            ("reload_global_config", "[white]Reload global config[/]"),
            ("edit_global_config", "[white]Edit global config in $EDITOR[/]"),
        ]

        target_actions.extend(self._custom_actions_for_scope("target"))
        global_actions.extend(self._custom_actions_for_scope("global"))

        if not targets:
            target_actions = [("noop", "[dim]No target actions available[/]")]

        self.push_screen(
            ActionPickerScreen(
                button_actions,
                with_hotkeys(target_actions),
                with_hotkeys(global_actions),
            ),
            self._on_pick_actions,
        )

    def _on_pick_actions(self, value: str | None) -> None:
        textual_ui_pick_actions.on_pick_actions(self, value)

    def _build_bulk_confirm_payload(
        self, action: str, paths: list[Path]
    ) -> tuple[str, str]:
        return textual_ui_bulk_confirm.build_bulk_confirm_payload(
            self,
            action,
            paths,
            base_dir=self.base_dir,
            archived_restore_target=archived_restore_target,
            is_under=core_utils.is_under,
            is_packed_archive_path=is_packed_archive_path,
        )

    def _on_set_description(self, value: str | None) -> None:
        textual_ui_item_edits.on_set_description(
            self,
            value,
            save_base_description=save_base_description,
        )

    def _on_rename_item(self, value: str | None) -> None:
        textual_ui_item_edits.on_rename_item(
            self,
            value,
            project_row=project_row,
        )

    def _build_archived_row_from_entry(self, path: Path) -> ProjectRow:
        restore = archived_restore_target(self.base_dir, path)
        stem, archived_ts = core_utils.split_archive_entry_name(
            path,
            packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        )
        row = project_row(
            path,
            archived=True,
            restore_target=restore,
            archived_ts=archived_ts,
        )
        row.name = stem
        row.is_fork, row.is_tmp, row.suffix = classify_name(row.name)
        refresh_row_caches(row)
        return row

    def _start_archive_action_worker(self, action: str, paths: list[Path]) -> None:
        textual_ui_archive_worker.start_archive_action_worker(
            self,
            action,
            paths,
            archive_pack_internal=archive_pack_internal,
            archive_unpack_internal=archive_unpack_internal,
            is_packed_archive_path=is_packed_archive_path,
        )

    def _on_archive_action_worker_progress(
        self, done: int, current: str, stage: str, command: str
    ) -> None:
        textual_ui_archive_worker.on_archive_action_worker_progress(
            self,
            done,
            current,
            stage,
            command,
        )

    def _on_archive_action_worker_done(self, outcome: ArchiveActionOutcome) -> None:
        textual_ui_archive_worker.on_archive_action_worker_done(self, outcome)

    def _on_confirm_bulk(self, ok: bool, action: str, paths: list[Path]) -> None:
        textual_ui_bulk_dispatch.on_confirm_bulk(
            self,
            ok,
            action,
            paths,
            archive_move_internal=archive_move_internal,
            archive_restore_internal=archive_restore_internal,
            archive_pack_internal=archive_pack_internal,
            archive_unpack_internal=archive_unpack_internal,
            delete_internal=delete_internal,
            is_packed_archive_path=is_packed_archive_path,
            open_meta_for_review=open_meta_for_review,
            rename_legacy_base_yaml=rename_legacy_base_yaml,
            project_row=project_row,
            row_build_errors=_ROW_BUILD_ERRORS,
            deworktree_internal=deworktree_internal,
        )

    def _restore_note_sync_precheck(
        self,
        archived_path: Path,
        restore_target: Path,
    ) -> tuple[bool, str, Path | None, Path | None, str]:
        resolve_notes = getattr(self, "_resolve_notes_path_for_row", None)
        enabled, command_template = textual_ui_note_sync.note_sync_config(self, "restore")
        if not enabled:
            return True, "", None, None, ""
        if not callable(resolve_notes):
            return True, "", None, None, ""
        hit = self._find_row(archived_path)
        if hit is None:
            return True, "", None, None, ""
        rows, idx = hit
        archived_row = rows[idx]
        try:
            old_note_path = resolve_notes(archived_row)
        except (OSError, ValueError, RuntimeError):
            return True, "", None, None, ""
        try:
            if not old_note_path.is_file():
                return True, "", None, None, ""
        except OSError as exc:
            return False, str(exc), None, None, ""

        restored_row = ProjectRow(
            path=restore_target,
            name=restore_target.name,
            branch=archived_row.branch,
            dirty=archived_row.dirty,
            last=archived_row.last,
            src=archived_row.src,
            created=archived_row.created,
            tags=list(archived_row.tags),
            properties=list(archived_row.properties),
            description=archived_row.description,
            created_ts=archived_row.created_ts,
            last_ts=archived_row.last_ts,
            git_ts=archived_row.git_ts,
            opened_ts=archived_row.opened_ts,
            is_fork=archived_row.is_fork,
            is_tmp=archived_row.is_tmp,
            archived=False,
            restore_target=None,
            archived_ts=0,
            wip=archived_row.wip,
            suffix=archived_row.suffix,
            packed=False,
        )
        try:
            new_note_path = resolve_notes(restored_row)
        except (OSError, ValueError, RuntimeError) as exc:
            return False, f"new note path resolution failed ({exc})", None, None, ""
        if new_note_path != old_note_path and new_note_path.exists():
            return False, f"target note exists ({new_note_path})", None, None, ""
        try:
            if not new_note_path.parent.is_dir() or not os.access(
                new_note_path.parent, os.W_OK | os.X_OK
            ):
                return (
                    False,
                    f"no write permission for note destination ({new_note_path.parent})",
                    None,
                    None,
                    "",
                )
        except OSError as exc:
            return False, str(exc), None, None, ""
        rendered = ""
        if command_template:
            try:
                rendered = textual_ui_note_sync.build_note_sync_command(
                    self,
                    source_row=archived_row,
                    target_row=restored_row,
                    old_note_path=old_note_path,
                    new_note_path=new_note_path,
                    command_template=command_template,
                )
            except (TypeError, ValueError) as exc:
                return False, f"restore note command render failed ({exc})", None, None, ""
            if not rendered:
                return False, "restore note command rendered empty", None, None, ""
        return True, "", old_note_path, new_note_path, rendered

    def _sync_note_after_restore(
        self,
        old_note_path: Path | None,
        new_note_path: Path | None,
        rendered_command: str,
    ) -> tuple[bool, str]:
        if old_note_path is None or new_note_path is None:
            return True, ""
        if old_note_path == new_note_path:
            return True, ""
        try:
            if rendered_command:
                proc = subprocess.run(
                    ["sh", "-lc", rendered_command],
                    cwd=str(self.base_dir),
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                    check=False,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or "").strip() or f"exit={proc.returncode}"
                    return False, err
            else:
                new_note_path.parent.mkdir(parents=True, exist_ok=True)
                old_note_path.rename(new_note_path)
        except OSError as exc:
            return False, str(exc)
        return True, ""

    def _process_next_restore(self) -> None:
        if not self.pending_restore_queue:
            self._busy_stop()
            self._request_tag_sync("restore batch")
            self._refresh_data()
            self.selected_path = None
            self._refresh_table()
            self._log(
                f"restore finished: ok={self.pending_restore_ok}, failed={self.pending_restore_failed}",
                "info",
            )
            self._refresh_side()
            return

        path = self.pending_restore_queue[0]
        restore_target = archived_restore_target(self.base_dir, path)
        ok_note, note_reason, old_note_path, new_note_path, rendered_note_cmd = self._restore_note_sync_precheck(
            path,
            restore_target,
        )
        if not ok_note:
            self._log(f"restore skipped for {path.name}: {note_reason}", "warn")
            self.notify(f"Restore skipped: {note_reason}", severity="warning")
            self.pending_restore_failed += 1
            self.multi_selected.discard(path)
            self.pending_restore_queue.pop(0)
            self._process_next_restore()
            return
        try:
            restored = archive_restore_internal(self.base_dir, path, sync_tags=False)
            note_ok, note_err = self._sync_note_after_restore(old_note_path, new_note_path, rendered_note_cmd)
            if not note_ok:
                raise ValueError(f"note sync failed ({note_err})")
            self._log(f"restored: {path.name} -> {restored}", "info")
            self.pending_restore_ok += 1
            self._remove_paths_local([path])
            try:
                restored_row = project_row(restored, archived=False)
                self._upsert_row_local(restored_row)
                self._touch_rows_cache([restored_row], removed=[path])
            except (
                OSError,
                ValueError,
                TypeError,
                subprocess.SubprocessError,
                sqlite3.Error,
            ):
                pass
            self.multi_selected.discard(path)
            self.pending_restore_queue.pop(0)
            self._process_next_restore()
        except RestoreTargetExistsError as exc:
            self._busy_stop()
            self.push_screen(
                SingleChoiceScreen(
                    f"Restore conflict for {path.name}",
                    [
                        ("skip", "skip this item"),
                        ("other", "restore to another location"),
                    ],
                ),
                lambda choice, conflict=exc: self._on_restore_conflict_choice(
                    choice, conflict
                ),
            )
        except ValueError as exc:
            self._log(f"restore failed for {path.name}: {exc}", "error")
            self.pending_restore_failed += 1
            self.multi_selected.discard(path)
            self.pending_restore_queue.pop(0)
            self._process_next_restore()

    def _on_restore_conflict_choice(
        self, choice: str | None, exc: RestoreTargetExistsError
    ) -> None:
        if not self.pending_restore_queue:
            return
        path = self.pending_restore_queue[0]
        if choice == "other":
            self.push_screen(
                RestorePathScreen(exc.target, self.base_dir),
                lambda target: self._on_restore_other_target(target, path),
            )
            return

        self._log(f"restore skipped for {path.name}: target exists", "warn")
        self.pending_restore_failed += 1
        self.multi_selected.discard(path)
        self.pending_restore_queue.pop(0)
        self._busy_start("restoring target items")
        self._process_next_restore()

    def _on_restore_other_target(
        self, target: Path | None, archived_path: Path
    ) -> None:
        if not self.pending_restore_queue:
            return
        if target is None:
            self._log(
                f"restore skipped for {archived_path.name}: no alternate target",
                "warn",
            )
            self.pending_restore_failed += 1
            self.multi_selected.discard(archived_path)
            self.pending_restore_queue.pop(0)
            self._busy_start("restoring target items")
            self._process_next_restore()
            return

        ok_note, note_reason, old_note_path, new_note_path, rendered_note_cmd = self._restore_note_sync_precheck(
            archived_path,
            target,
        )
        if not ok_note:
            self._log(f"restore skipped for {archived_path.name}: {note_reason}", "warn")
            self.notify(f"Restore skipped: {note_reason}", severity="warning")
            self.pending_restore_failed += 1
            self.multi_selected.discard(archived_path)
            self.pending_restore_queue.pop(0)
            self._busy_start("restoring target items")
            self._process_next_restore()
            return

        try:
            self._busy_start("restoring target items")
            restored = archive_restore_internal(
                self.base_dir,
                archived_path,
                target_override=target,
                sync_tags=False,
            )
            note_ok, note_err = self._sync_note_after_restore(old_note_path, new_note_path, rendered_note_cmd)
            if not note_ok:
                raise ValueError(f"note sync failed ({note_err})")
            self._log(f"restored: {archived_path.name} -> {restored}", "info")
            self.pending_restore_ok += 1
            self._remove_paths_local([archived_path])
            try:
                restored_row = project_row(restored, archived=False)
                self._upsert_row_local(restored_row)
                self._touch_rows_cache([restored_row], removed=[archived_path])
            except (
                OSError,
                ValueError,
                TypeError,
                subprocess.SubprocessError,
                sqlite3.Error,
            ):
                pass
        except ValueError as exc:
            self._log(f"restore failed for {archived_path.name}: {exc}", "error")
            self.pending_restore_failed += 1
        finally:
            self._busy_stop()

        self.multi_selected.discard(archived_path)
        self.pending_restore_queue.pop(0)
        self._busy_start("restoring target items")
        self._process_next_restore()

    def _jump_to_tmux_pane(self, pane: PaneRef) -> bool:
        target_window = pane.target.rsplit(".", 1)[0]
        p1 = subprocess.run(
            [*_tmux_command_prefix(), "select-window", "-t", target_window],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        p2 = subprocess.run(
            [*_tmux_command_prefix(), "select-pane", "-t", pane.pane_id],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if p1.returncode != 0 or p2.returncode != 0:
            err = (
                (p1.stderr or "").strip()
                or (p2.stderr or "").strip()
                or "unknown tmux error"
            )
            self._log(f"tmux pane jump failed: {err}", "warn")
            self._refresh_side()
            return False
        self._log(f"jumped to pane {pane.pane_id} ({pane.target})", "info")
        self._set_runtime_status(f"goto pane {pane.target}", "info", ttl_s=10.0)
        self._refresh_side()
        return True

    def _open_profile_spec(self) -> dict[str, object]:
        profile = str(self.open_mode.get("profile", self.ctx.open_mode_config["profile"]))
        spec = next(
            (p for p in OPEN_MODE_PROFILES if str(p.get("id")) == profile), None
        )
        return spec or OPEN_MODE_PROFILES[0]

    def _open_selected_in_tmux_mode(self, row: ProjectRow) -> bool:
        spec = self._open_profile_spec()
        use_tmux = bool(spec.get("use_tmux", False))
        if not use_tmux:
            return False
        self.pane_probe_fast_until_ts = max(
            self.pane_probe_fast_until_ts, time.time() + 20.0
        )

        if not os.getenv("TMUX"):
            self._log("tmux not running; fallback to close + shell open", "warn")
            self._set_runtime_status(
                "tmux not running -> fallback shell open", "warn"
            )
            self._refresh_side()
            return False

        if bool(spec.get("goto_loaded", False)):
            panes = tmux_find_panes_for_cwd(row.path)
            if len(panes) == 1:
                self._jump_to_tmux_pane(panes[0])
                return True
            if len(panes) > 1:
                self.pending_pane_choices = {pane.pane_id: pane for pane in panes}
                self.push_screen(
                    PaneChoiceScreen(f"Open pane for {row.name}", panes),
                    self._on_pick_open_pane,
                )
                return True

        load_status: str | None = None
        if bool(spec.get("run_load", False)):
            rc, load_status = tmux_open_new_tab_with_load_status(row.path)
        else:
            rc = tmux_open_new_tab(row.path)
        if rc == 0:
            self._log(
                "opened in tmux: new tab"
                + (" + load" if bool(spec.get("run_load", False)) else ""),
                "info",
            )
            if load_status:
                self._set_runtime_status(load_status, "info", ttl_s=14.0)
            else:
                self._set_runtime_status(
                    "opened in tmux: new tab"
                    + (" + load" if bool(spec.get("run_load", False)) else ""),
                    "info",
                    ttl_s=10.0,
                )
        else:
            self._log("tmux open failed", "error")
            self._set_runtime_status("tmux open failed", "error", ttl_s=14.0)
        self._refresh_side()
        return True

    def _on_pick_open_pane(self, value: str | None) -> None:
        if not value:
            self.pending_pane_choices = {}
            return
        pane = self.pending_pane_choices.get(value)
        self.pending_pane_choices = {}
        if pane is None:
            self._log("pane choice missing", "warn")
            self._refresh_side()
            return
        self._jump_to_tmux_pane(pane)

    def action_open_selected(self) -> None:
        if self._table_is_active_focus() and self._hotbar_visible():
            target = self._selected_hotbar_target()
            if target and target not in {"open_selected", "action:open_selected"}:
                self._dispatch_hotkey_target(target)
                return
        if self._critical_job_active():
            self._log(
                f"cannot open while critical job is running: {self._critical_job_label()}",
                "warn",
            )
            self._refresh_side()
            return
        row = self._selected_row()
        if not row:
            return
        self._bump_row_usage(row.path, 2.5)
        if row.packed:
            self._log("cannot open packed archive directly; unpack first", "warn")
            self._refresh_side()
            return
        # Enter should always open the currently selected directory as-is.
        # In archive view this means opening the archived folder itself,
        # not the restore target.
        self._mark_row_active(row.path)

        if self._open_selected_in_tmux_mode(row):
            return

        self._flush_reconcile_usage_if_due()
        if self.reconcile_usage_dirty:
            self.reconcile_usage_due_at = 0.0
            self._flush_reconcile_usage_if_due()
        self._persist_state_now()
        self.fast_exit_requested = True
        self.exit(("open", row.path, []))

    def action_cycle_hotbar(self) -> None:
        if not self._table_is_active_focus():
            return
        if self._hotbar_visible():
            self._cycle_hotbar(1)

    def action_quit_app(self) -> None:
        running_managed = self._running_terminating_processes()
        if running_managed:
            sample = running_managed[:3]
            details = [
                f"[cyan]running managed processes[/]: {len(running_managed)}",
                "[bold yellow]warning[/]: quitting will terminate them",
            ]
            for proc in sample:
                details.append(f"- [cyan]pid[/]={proc.pid} [cyan]label[/]={self._esc(proc.label)}")
                details.append(
                    f"  [cyan]running[/]: {max(0.0, time.time() - float(proc.started_ts)):.1f}s"
                )
                details.append(f"  [cyan]cwd[/]: {self._esc(proc.cwd)}")
                details.append(f"  [cyan]command[/]: [dim]{self._esc(proc.command)}[/]")
            if len(running_managed) > len(sample):
                details.append(f"- ... and {len(running_managed) - len(sample)} more")
            self.push_screen(
                ConfirmScreen("Quit and terminate running processes?", "\n".join(details)),
                self._on_quit_while_busy,
            )
            return
        if self._critical_job_active():
            details = (
                f"[cyan]critical job[/]: {self._esc(self._critical_job_label())}\n"
                "[bold red]warning[/]: exiting now may interrupt this operation"
            )
            self.push_screen(
                ConfirmScreen("Quit while critical job is running?", details),
                self._on_quit_while_busy,
            )
            return
        self._flush_reconcile_usage_if_due()
        if self.reconcile_usage_dirty:
            self.reconcile_usage_due_at = 0.0
            self._flush_reconcile_usage_if_due()
        self._persist_state_now()
        self._terminate_running_managed_processes()
        self.fast_exit_requested = True
        self.exit(("quit", None, []))

    def _on_quit_while_busy(self, ok: bool) -> None:
        if not ok:
            self._log("quit cancelled", "warn")
            self._refresh_side()
            return
        self._flush_reconcile_usage_if_due()
        if self.reconcile_usage_dirty:
            self.reconcile_usage_due_at = 0.0
            self._flush_reconcile_usage_if_due()
        self._persist_state_now()
        self._terminate_running_managed_processes()
        self.fast_exit_requested = True
        self.exit(("quit", None, []))



def run_textual_ui(
    base_dir: Path,
    cwd: Path,
    ctx: UIContext | None = None,
    start_new: bool = False,
    initial_filter_expr: str = "",
) -> tuple[str, Path | None, list[str]]:
    set_filter_query_base_dir(base_dir)
    set_filter_manage_base_dir(base_dir)
    app = BApp(
        base_dir,
        ctx=ctx,
        start_new_mode=start_new,
        initial_filter=initial_filter_expr,
    )
    result = app.run() or ("quit", None, [])
    # After the TUI returns the terminal is restored; flush any
    # deferred summary or error captured by the new-project flow so
    # the user actually sees what happened (success or failure).
    summary = getattr(app, "last_new_summary", None)
    if summary:
        print(summary)
    error = getattr(app, "last_new_error", None)
    if error:
        print(f"b new failed:\n{error}", file=sys.stderr)
    return result
