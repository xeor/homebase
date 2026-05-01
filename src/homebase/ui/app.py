from __future__ import annotations

import json
import os
import random
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

import yaml
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Static,
    Tab,
    Tabs,
)

from ..cache.api import (
    cache_load_reconcile_usage,
    cache_load_rows,
    cache_save_reconcile_usage,
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
from ..config.prefs import (
    _merge_table_columns_for_view,
    load_table_behavior_config,
    load_table_columns_config,
    load_ui_state,
    resolve_filter_expression,
    save_ui_state,
)
from ..core.constants import (
    ACTION_SHORT_HELP,
    ARCHIVE_DIR_NAME,
    BASE_MARKER_FILE,
    BUSY_LABEL_IDLE,
    CACHE_BG_REFRESH_S,
    CACHE_MAX_AGE_S,
    CACHE_SCHEMA_VERSION,
    COLOR_ACCENT_HEX,
    COLOR_ARCHIVE_HEX,
    COLOR_ERROR_HEX,
    COLOR_INFO_HEX,
    COLOR_INTERACTIVE_HEX,
    COLOR_NAV_HEX,
    COLOR_SUCCESS_HEX,
    COLOR_WARN_HEX,
    CURSOR_BG_HEX,
    CURSOR_FG_HEX,
    CUSTOM_ACTIONS,
    DYNAMIC_PROPERTY_DEFS,
    FILE_VIEW_EXCLUDE_PATTERNS,
    LEGACY_BASE_MARKER_FILE,
    LEVEL_INFO,
    LEVEL_WARN,
    MODE_ACTIVE,
    MODE_ARCHIVE,
    NAMED_FILTERS,
    NOTES_CONFIG,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    PACKED_ARCHIVE_SUFFIX,
    RECONCILE_CONFIG,
    RECONCILE_STALE_BATCH_SIZE,
    RECONCILE_STALE_INTERVAL_S,
    RECONCILE_STALE_PARALLELISM,
    SIDE_CHILD_TABS,
    SIDE_TOP_TABS,
    STATE_KEY_SIDE_INFO,
    STATE_KEY_SIDE_MAIN,
    STATE_KEY_SIDE_SELECTED,
    STATE_KEY_SIDE_SETTINGS,
    SUFFIXES,
    TABLE_COLUMN_VIEWS,
    UI_TICK_BUSY_S,
    UI_TICK_GIT_REFRESH_S,
    UI_TICK_MICRO_RECONCILE_S,
    UI_TICK_PANE_PROBE_S,
    UI_TICK_QUERY_FLUSH_S,
    UI_TICK_RECONCILE_USAGE_FLUSH_S,
    UI_TICK_STATE_FLUSH_S,
    WIDGET_PROJECTS,
    WIP_OPEN_SYMBOL_MAP,
)
from ..core.models import (
    ArchiveActionOutcome,
    CacheRefreshOutcome,
    PaneRef,
    ProjectRow,
    RestoreTargetExistsError,
)
from ..core.utils import WIDGET_API_ERRORS, fmt_age_short_from_iso, fmt_size_human
from ..metadata.api import (
    all_property_defs,
    base_meta_health,
    base_meta_issues,
    load_base_data,
    load_base_meta,
    normalize_property_keys,
    open_meta_for_review,
    property_tokens_text,
    rename_legacy_base_yaml,
    save_base_description,
    save_base_opened,
    save_base_tags,
    save_base_wip,
)
from ..tmux.flow import (
    _tmux_command_prefix,
    tmux_find_panes_for_cwd,
    tmux_open_new_tab,
    tmux_open_new_tab_with_load_status,
)
from ..workspace.projects import (
    classify_name,
    project_row,
)
from ..workspace.rows import (
    _normalize_sort_mode_for_view,
    _sort_modes_for_view,
    archived_restore_target,
    compile_filter_expr,
    fmt_ymd,
    is_under,
    normalize_filter_expression,
    packed_archive_dir_name,
    query_uses_filter_syntax,
    split_archive_entry_name,
)
from . import runtime_feedback as textual_ui_runtime_feedback
from .actions import action_items as textual_ui_action_items
from .actions import bulk_confirm as textual_ui_bulk_confirm
from .actions import bulk_preflight as textual_ui_bulk_preflight
from .actions import item_edits as textual_ui_item_edits
from .actions import project_create as textual_ui_project_create
from .actions import tag_actions as textual_ui_tag_actions
from .actions import wip_actions as textual_ui_wip_actions
from .query import edit as textual_ui_query_edit
from .query import key_input as textual_ui_key_input
from .query import notes_paths as textual_ui_notes_paths
from .query import runtime as textual_ui_query_runtime
from .query import selection_events as textual_ui_selection_events
from .query import workspace_guard as textual_ui_workspace_guard
from .screens.actions import ActionPickerScreen
from .screens.basic import (
    ConfirmScreen,
    InputScreen,
    RuntimeErrorScreen,
)
from .screens.choices import SingleChoiceScreen
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
from .sync import git_refresh as textual_ui_git_refresh
from .sync import pane_probe as textual_ui_pane_probe
from .sync import reconcile as textual_ui_reconcile
from .sync import reconcile_worker as textual_ui_reconcile_worker
from .sync import sync as textual_ui_sync
from .table import nav as textual_ui_table_nav
from .table import render as textual_ui_table_render
from .table import row_helpers as textual_ui_row_helpers
from .table import rows_view as textual_ui_rows_view
from .table import tabs_state as textual_ui_tabs_state
from .table import view_actions as textual_ui_view_actions
from .table import view_state as textual_ui_view_state
from .widgets import ReadmeMarkdownViewer

# Catch-all for "row construction may legitimately fail; skip the upsert"
# call sites in BApp action handlers.
_ROW_BUILD_ERRORS = (
    OSError,
    ValueError,
    TypeError,
    subprocess.SubprocessError,
    sqlite3.Error,
)

_VIEW_CONFIG_DEFAULT: dict[str, dict[str, list[tuple[str, str]]]] = {
    "active": {
        "actions": [
            ("archive", "archive selected"),
            ("set_desc", "set description on selected"),
            ("delete", "delete selected"),
        ],
    },
    "archive": {
        "actions": [
            ("toggle_pack", "toggle pack/unpack selected"),
            ("pack", "pack selected (.base-pkg.tgz)"),
            ("unpack", "unpack selected"),
            ("restore", "restore selected"),
            ("set_desc", "set description on selected"),
            ("delete", "delete selected"),
        ],
    },
}


class BApp(App[tuple[str, Path | None, list[str]]]):
    CSS = """
    Screen { layout: vertical; }
    #toolbar { height: 5; border: round $accent; padding: 0 1; }
    #global_meta { content-align: left top; }
    #main { height: 1fr; }
    #projects { width: 4fr; height: 1fr; border: round $surface; }
    #side { width: 2fr; height: 1fr; border: round $surface; padding: 0 1; }
    #side_main_tabs { height: 3; margin: 0 0 1 0; }
    #side_selected_tabs { height: 3; margin: 0 0 1 0; }
    #side_info_tabs { height: 3; margin: 0 0 1 0; }
    #side_settings_tabs { height: 3; margin: 0 0 1 0; }
    #side_settings_table { height: 1fr; display: none; }
    #side_settings_notes { height: 15; display: none; color: $text-muted; }
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
        ("enter", "open_selected", "Open"),
        ("ctrl+g", "open_existing_pane", "Goto tmux-tab"),
        ("ctrl+q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        base_dir: Path,
        start_new_mode: bool = False,
        initial_filter: str = "",
    ) -> None:
        super().__init__()
        self.base_dir = base_dir
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
        self.side_selected_tab = str(
            persisted.get(STATE_KEY_SIDE_SELECTED, selected_default)
        )
        self.side_info_tab = str(persisted.get(STATE_KEY_SIDE_INFO, info_default))
        self.side_settings_tab = str(
            persisted.get(STATE_KEY_SIDE_SETTINGS, settings_default)
        )
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
        self.custom_actions = list(CUSTOM_ACTIONS)
        self.pending_tag_updates: set[Path] = set()
        self.messages: list[tuple[str, str, str]] = []
        self._health_issue_seen: dict[Path, str] = {}
        self.pending_restore_queue: list[Path] = []
        self.pending_restore_ok = 0
        self.pending_restore_failed = 0
        self.error_counts: dict[str, int] = {}
        self.worker_debug_events: list[tuple[str, str]] = []
        self._settings_table_was_active = False
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
        self.git_refresh_reason = ""
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
        self.pane_probe_fast_until_ts = 0.0
        self.pane_probe_interval_fast_s = 1.0
        self.pane_probe_interval_slow_s = 6.0
        self.pending_pane_choices: dict[str, PaneRef] = {}

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

    def _init_busy_state(self) -> None:
        self._busy_depth = 0
        self._busy_label = BUSY_LABEL_IDLE
        self._busy_frames = ["|", "/", "-", "\\"]
        self._busy_frame_index = 0

    def _init_settings_state(self) -> None:
        self.table_columns_by_view = load_table_columns_config(self.base_dir)
        self.table_settings_index = 0
        self.table_behavior = load_table_behavior_config(self.base_dir)
        self.table_config_index = 0
        self.open_mode = dict(OPEN_MODE_CONFIG)
        self.notes_config = dict(NOTES_CONFIG)
        self.open_settings_index = 0

    def _init_reconcile_state(self) -> None:
        self.reconcile_config = {
            "active": dict(RECONCILE_CONFIG.get("active", {})),
            "archive": dict(RECONCILE_CONFIG.get("archive", {})),
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
            yield Static("", id="global_meta")
        with Horizontal(id="main"):
            yield DataTable(id="projects", cursor_type="row")
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
                yield Static("", id="side_settings_notes")
                yield DataTable(id="side_settings_table", cursor_type="row")
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
            self.query_one("#side_settings_table", DataTable),
            self.query_one("#side_settings_notes", Static),
            self.query_one("#wip_bar", Static),
            self.query_one("#global_meta", Static),
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
            is_top_active = self.side_main_tab == top_key
            top_title = (
                f"Tab: {top_label}"
                if not is_top_active
                else f"Tab: {top_label} (active)"
            )
            yield SystemCommand(
                top_title,
                f"Go to main tab: {top_label}",
                lambda top=top_key: self._jump_to_side_tab(top),
            )

            for child_key, child_label in SIDE_CHILD_TABS.get(top_key, []):
                is_active = (
                    self.side_main_tab == top_key
                    and self._child_key_for_top(top_key) == child_key
                )
                title = (
                    f"Tab: {top_label} / {child_label}"
                    if not is_active
                    else f"Tab: {top_label} / {child_label} (active)"
                )
                yield SystemCommand(
                    title,
                    f"Go to tab: {top_label} / {child_label}",
                    lambda top=top_key, child=child_key: self._jump_to_side_tab(
                        top, child
                    ),
                )

        for action_id, label in self._valid_action_items():
            plain = self._label_plain(label)
            yield SystemCommand(
                f"Action: {plain}",
                self._action_help_text(action_id, label),
                lambda aid=action_id: self._on_pick_actions(aid),
            )

    def _apply_side_tab_state_to_widgets(self) -> None:
        textual_ui_tabs_state.apply_side_tab_state_to_widgets(self)

    def _cycle_tabs(self, reverse: bool = False) -> None:
        textual_ui_tabs_state.cycle_tabs(
            self,
            reverse=reverse,
            side_top_tabs=SIDE_TOP_TABS,
            side_child_tabs=SIDE_CHILD_TABS,
        )

    def action_cycle_tabs(self) -> None:
        textual_ui_tabs_state.action_cycle_tabs(self)

    def action_cycle_tabs_prev(self) -> None:
        textual_ui_tabs_state.action_cycle_tabs_prev(self)

    def _named_filters_sig(self) -> str:
        return textual_ui_query_runtime.named_filters_sig(NAMED_FILTERS)

    def _query_eval(
        self, query_text: str
    ) -> tuple[bool, str, str | None, Callable[[ProjectRow], bool], str | None]:
        return textual_ui_query_runtime.query_eval(
            self,
            query_text,
            named_filters=NAMED_FILTERS,
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

    def _cheat_columns(self) -> tuple[str, str]:
        return textual_ui_side_content.cheat_columns(
            self,
            all_property_defs=all_property_defs,
            dynamic_property_defs=DYNAMIC_PROPERTY_DEFS,
            color_error_hex=COLOR_ERROR_HEX,
            color_warn_hex=COLOR_WARN_HEX,
            color_info_hex=COLOR_INFO_HEX,
        )

    def _preview_entries(self, path: Path, limit: int = 8) -> list[str]:
        return textual_ui_side_content.preview_entries(path, limit=limit)

    @staticmethod
    def _esc(text: object) -> str:
        return str(text).replace("[", "\\[").replace("]", "\\]")

    @staticmethod
    def _run_cmd(cwd: Path, *cmd: str) -> tuple[str, str | None]:
        return textual_ui_side_content.run_cmd(cwd, *cmd)

    def _build_side_git_text(self, row: ProjectRow) -> str:
        return textual_ui_side_content.build_side_git_text(self, row)

    def _build_side_project_events_text(self, row: ProjectRow) -> str:
        return textual_ui_side_content.build_side_project_events_text(
            self,
            row,
            load_base_data=load_base_data,
            fmt_age_short_from_iso=fmt_age_short_from_iso,
        )

    def _build_side_files_text(self, row: ProjectRow) -> str:
        return textual_ui_side_content.build_side_files_text(
            self,
            row,
            file_view_exclude_patterns=FILE_VIEW_EXCLUDE_PATTERNS,
            fmt_size_human=fmt_size_human,
        )


    def _configure_table_columns(self) -> None:
        table = self.query_one(WIDGET_PROJECTS, DataTable)
        table.clear(columns=True)

        visible = self._table_visible_columns_for_view(self.view_mode)
        if not visible:
            visible = [
                col
                for col in self._table_columns_for_view(self.view_mode)
                if col.get("id") == "name"
            ]
            if not visible:
                visible = [
                    {
                        "id": "name",
                        "label": "NAME",
                        "enabled": True,
                        "width": 34,
                        "views": ["active", "archive"],
                    }
                ]
        for col in visible:
            label = str(col.get("label", ""))
            try:
                width = int(col.get("width", 12))
            except (TypeError, ValueError):
                width = 12
            width = max(4, min(80, width))
            try:
                table.add_column(label, width=width)
            except (RuntimeError, ValueError, TypeError):
                table.add_column(label)

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
        return textual_ui_row_helpers.has_open_pane(
            path,
            self.open_pane_count_by_project,
        )

    def _has_readme_file(self, row: ProjectRow) -> bool:
        return textual_ui_row_helpers.has_readme_file(row)

    def _has_notes_file(self, row: ProjectRow) -> bool:
        return textual_ui_row_helpers.has_notes_file(
            row,
            resolve_notes_path_for_row=self._resolve_notes_path_for_row,
        )

    def _apply_dynamic_properties_to_row(self, row: ProjectRow) -> None:
        props = [p for p in row.properties if p not in {"act", "rm", "n", "pkg"}]
        if self._has_open_pane(row.path):
            props.append("act")
        if self._has_readme_file(row):
            props.append("rm")
        if self._has_notes_file(row):
            props.append("n")
        if row.packed:
            props.append("pkg")
        row.properties = normalize_property_keys(props)

    def _apply_dynamic_properties_all_rows(self) -> None:
        for row in self.active_rows:
            self._apply_dynamic_properties_to_row(row)
        for row in self.archived_rows:
            self._apply_dynamic_properties_to_row(row)
        self._invalidate_current_rows_cache()

    def _find_row(self, path: Path) -> tuple[list[ProjectRow], int] | None:
        for rows in (self.active_rows, self.archived_rows):
            for idx, row in enumerate(rows):
                if row.path == path:
                    return rows, idx
        return None

    def _upsert_row_local(self, row: ProjectRow) -> None:
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
                self._invalidate_current_rows_cache()
                return
        row.stale = False
        row.cache_age_s = 0
        target_rows.append(row)
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
        return textual_ui_reconcile.effective_reconcile_wait_s(
            self,
            mode,
            reconcile_stale_interval_s=RECONCILE_STALE_INTERVAL_S,
        )

    def _effective_reconcile_parallelism(self, mode: str) -> int:
        return textual_ui_reconcile.effective_reconcile_parallelism(
            self,
            mode,
            reconcile_stale_parallelism=RECONCILE_STALE_PARALLELISM,
        )

    def _effective_reconcile_batch_size(self, mode: str) -> int:
        return textual_ui_reconcile.effective_reconcile_batch_size(
            self,
            mode,
            reconcile_stale_batch_size=RECONCILE_STALE_BATCH_SIZE,
        )

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
            is_under=is_under,
        )

    def _maybe_run_micro_reconcile(self) -> None:
        if self.fast_exit_requested:
            self._set_reconcile_skip_reason("fast exit")
            return
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

    def _maybe_refresh_visible_git(self) -> None:
        textual_ui_git_refresh.maybe_refresh_visible_git(self)

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

    def action_query_left(self) -> None:
        textual_ui_table_nav.action_query_left(self)

    def action_query_right(self) -> None:
        textual_ui_table_nav.action_query_right(self)

    def action_query_home(self) -> None:
        textual_ui_table_nav.action_query_home(self)

    def action_query_end(self) -> None:
        textual_ui_table_nav.action_query_end(self)

    def action_table_scroll_left(self) -> None:
        textual_ui_table_nav.action_table_scroll_left(self)

    def action_table_scroll_right(self) -> None:
        textual_ui_table_nav.action_table_scroll_right(self)

    def action_route_left(self) -> None:
        textual_ui_table_nav.action_route_left(self)

    def action_route_right(self) -> None:
        textual_ui_table_nav.action_route_right(self)

    def action_route_home(self) -> None:
        textual_ui_table_nav.action_route_home(self)

    def action_route_end(self) -> None:
        textual_ui_table_nav.action_route_end(self)

    def _refresh_table(self) -> None:
        textual_ui_table_render.refresh_table(
            self,
            widget_projects=WIDGET_PROJECTS,
            mode_active=MODE_ACTIVE,
            base_dir=self.base_dir,
            color_error_hex=COLOR_ERROR_HEX,
            color_success_hex=COLOR_SUCCESS_HEX,
            color_archive_hex=COLOR_ARCHIVE_HEX,
            color_accent_hex=COLOR_ACCENT_HEX,
            color_warn_hex=COLOR_WARN_HEX,
            color_interactive_hex=COLOR_INTERACTIVE_HEX,
            fmt_ymd=fmt_ymd,
            fmt_size_human=fmt_size_human,
            property_tokens_text=property_tokens_text,
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

    def _refresh_side(self) -> None:
        textual_ui_side_tabs.refresh_side(
            self,
            base_dir=self.base_dir,
            color_accent_hex=COLOR_ACCENT_HEX,
            level_warn=LEVEL_WARN,
        )

    def _open_editor_for_path(self, path: Path) -> None:
        textual_ui_side_effects.open_editor_for_path(path)

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

    def on_button_pressed(self, event) -> None:
        textual_ui_side_tabs.on_button_pressed(self, event)

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

    def _table_config_rows(self) -> list[tuple[str, str, str, str]]:
        return textual_ui_settings_panel.table_config_rows(self)

    def _table_config_save(self) -> None:
        textual_ui_settings_panel.table_config_save(self, base_dir=self.base_dir)

    def _table_config_toggle_selected(self) -> None:
        textual_ui_settings_panel.table_config_toggle_selected(self, base_dir=self.base_dir)

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
            suffixes=SUFFIXES,
        )

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        textual_ui_selection_events.on_data_table_row_highlighted(
            self,
            event,
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        textual_ui_selection_events.on_data_table_row_selected(self, event)

    def on_key(self, event: Key) -> None:
        textual_ui_key_input.on_key(
            self,
            event,
            widget_projects=WIDGET_PROJECTS,
            wip_open_symbol_map=WIP_OPEN_SYMBOL_MAP,
        )

    def action_toggle_select_mode(self) -> None:
        textual_ui_selection_events.action_toggle_select_mode(self)

    def action_toggle_selected(self) -> None:
        textual_ui_selection_events.action_toggle_selected(self)

    def action_toggle_wip(self) -> None:
        textual_ui_wip_actions.action_toggle_wip(
            self,
            mode_active=MODE_ACTIVE,
            save_base_wip=save_base_wip,
        )

    def action_refresh_details(self) -> None:
        textual_ui_wip_actions.action_refresh_details(self)

    def action_open_wip_1(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 1)

    def action_open_wip_2(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 2)

    def action_open_wip_3(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 3)

    def action_open_wip_4(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 4)

    def action_open_wip_5(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 5)

    def action_open_wip_6(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 6)

    def action_open_wip_7(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 7)

    def action_open_wip_8(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 8)

    def action_open_wip_9(self) -> None:
        textual_ui_wip_actions.action_open_wip_index(self, 9)

    def action_new_project(self) -> None:
        textual_ui_project_create.action_new_project(
            self,
            base_dir=self.base_dir,
            new_project_screen=NewProjectScreen,
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
            suffixes=SUFFIXES,
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
            action_short_help=ACTION_SHORT_HELP,
        )

    def _custom_action_by_id(self, cid: str) -> dict[str, str] | None:
        return textual_ui_action_items.custom_action_by_id(self, cid)

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
            packed_archive_dir_name=packed_archive_dir_name,
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
        selected = self._selected_row()
        button_actions = self._readme_button_actions() + self._notes_button_actions()

        selection_actions: list[tuple[str, str]] = [
            ("tags_set", "[white]Tags...[/]"),
            ("reconcile_selection_cache", "[white]Reconcile selected cache now[/]"),
        ]
        if self.view_mode == "active":
            selection_actions.append(("suffix_set", "[white]Suffix...[/]"))
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
            selection_actions.append((k, label))

        item_actions: list[tuple[str, str]] = []
        if selected is not None:
            item_actions.append(("rename_item", "[white]Rename item...[/]"))
            issue_codes = {
                code for _lvl, code, _msg in base_meta_issues(selected.path)
            }
            if issue_codes and not selected.packed:
                item_actions.append(
                    ("review_meta", "[white]Open .base.yml and review warnings[/]")
                )
            if (
                "legacy_only" in issue_codes or "legacy_conflict" in issue_codes
            ) and not selected.packed:
                item_actions.append(
                    ("rename_meta_ext", "[white]Rename .base.yaml -> .base.yml[/]")
                )

        global_actions: list[tuple[str, str]] = [
            ("refresh_cache", "[white]Refresh cache[/]"),
            ("full_reconcile", "[white]Full reconcile (force rescan)[/]"),
            ("reconcile_all_cache", "[white]Reconcile all cached rows now[/]"),
        ]

        selection_actions.extend(self._custom_actions_for_scope("selection"))
        item_actions.extend(self._custom_actions_for_scope("item"))
        global_actions.extend(self._custom_actions_for_scope("global"))

        # If nothing is selected, keep selection tab available but mostly empty.
        if not targets:
            selection_actions = [("noop", "[dim]No selection actions available[/]")]

        self.push_screen(
            ActionPickerScreen(
                button_actions,
                selection_actions,
                item_actions,
                global_actions,
            ),
            self._on_pick_actions,
        )

    def _on_pick_actions(self, value: str | None) -> None:
        if not value or value.startswith("__hdr__") or value == "noop":
            return
        if value.startswith("custom:"):
            self._run_custom_action(value.split(":", 1)[1])
            return
        if value in {"readme_create", "readme_edit"}:
            self._run_readme_button_action(value)
            return
        if value in {"notes_create", "notes_open"}:
            self._run_notes_button_action(value)
            return
        targets = self._target_rows()
        if value == "tags_set":
            if not targets:
                return
            if any(r.packed for r in targets):
                self._log(
                    "packed archive selected: tag updates may be slower",
                    "warn",
                )
            self.action_pick_tags()
            return
        if value == "suffix_set":
            if not targets:
                return
            if self.view_mode != "active":
                self._log("suffix update is only available in active view", "warn")
                self._refresh_side()
                return
            self.action_pick_category()
            return
        if value == "refresh_cache":
            self._start_cache_refresh("manual refresh", force=True)
            self._log("cache refresh requested", "info")
            self._refresh_side()
            return
        if value == "full_reconcile":
            self._start_cache_refresh("manual full reconcile", force=True)
            self._log("full reconcile requested", "info")
            self._refresh_side()
            return
        if value == "reconcile_all_cache":
            all_paths = [r.path for r in (self.active_rows + self.archived_rows)]
            if not all_paths:
                self._log("reconcile skipped: no rows", "warn")
                self._refresh_side()
                return
            self._start_reconcile_rows("mixed", "manual-all", all_paths)
            self._log(
                f"reconcile requested for all rows ({len(all_paths)})", "info"
            )
            self._refresh_side()
            return
        if value == "reconcile_selection_cache":
            if not targets:
                self._log("reconcile skipped: no selection", "warn")
                self._refresh_side()
                return
            paths = [r.path for r in targets]
            mode = (
                "archive"
                if all(r.archived for r in targets)
                else ("active" if all(not r.archived for r in targets) else "mixed")
            )
            self._start_reconcile_rows(mode, "manual-selection", paths)
            self._log(f"reconcile requested for selection ({len(paths)})", "info")
            self._refresh_side()
            return
        if value == "rename_item":
            row = self._selected_row()
            if row is None:
                return
            self.pending_rename_target = row.path
            self.push_screen(
                InputScreen("Rename item", "new folder name", row.path.name),
                self._on_rename_item,
            )
            return
        if value in {"review_meta", "rename_meta_ext"}:
            row = self._selected_row()
            if row is None:
                return
            paths = [row.path]
            title, details = self._build_bulk_confirm_payload(value, paths)
            self.push_screen(
                ConfirmScreen(title, details),
                lambda ok: self._on_confirm_bulk(ok, value, paths),
            )
            return
        if value == "set_desc":
            if not targets:
                return
            if any(r.packed for r in targets):
                self._log(
                    "packed archive selected: description updates may be slower",
                    "warn",
                )
            self.pending_desc_targets = [r.path for r in targets]
            initial = targets[0].description if len(targets) == 1 else ""
            self.push_screen(
                InputScreen(
                    "Set description (empty clears)", "short summary", initial
                ),
                self._on_set_description,
            )
            return
        if not targets:
            return
        paths = [r.path for r in targets]
        action = value
        title, details = self._build_bulk_confirm_payload(action, paths)
        self.push_screen(
            ConfirmScreen(title, details),
            lambda ok: self._on_confirm_bulk(ok, action, paths),
        )

    def _build_bulk_confirm_payload(
        self, action: str, paths: list[Path]
    ) -> tuple[str, str]:
        return textual_ui_bulk_confirm.build_bulk_confirm_payload(
            self,
            action,
            paths,
            base_dir=self.base_dir,
            archived_restore_target=archived_restore_target,
            is_under=is_under,
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
        stem, archived_ts = split_archive_entry_name(path)
        row = project_row(
            path,
            archived=True,
            restore_target=restore,
            archived_ts=archived_ts,
        )
        row.name = stem
        row.is_fork, row.is_tmp, row.suffix = classify_name(row.name)
        return row

    def _start_archive_action_worker(self, action: str, paths: list[Path]) -> None:
        if self.action_worker_running:
            self._log("archive action worker is already running", "warn")
            self._refresh_side()
            return
        self.action_worker_running = True
        self.action_worker_action = action
        self.action_worker_total = len(paths)
        self.action_worker_done = 0
        self.action_worker_current = ""
        self.action_worker_stage = "queued"
        self.action_worker_command = ""
        self.action_worker_started_ts = int(time.time())
        self._busy_start(f"running {action} on selection")
        self._worker_debug(
            f"archive worker start: action={action} items={len(paths)}"
        )
        self._refresh_side()

        def worker() -> None:
            success = 0
            failed = 0
            removed_paths: list[Path] = []
            upsert_rows: list[ProjectRow] = []
            logs: list[tuple[str, str]] = []
            total = len(paths)
            for i, path in enumerate(paths, start=1):
                self.call_from_thread(
                    self._on_archive_action_worker_progress,
                    i - 1,
                    path.name,
                    "preparing",
                    "",
                )
                try:
                    if action == "pack":
                        cmd = f"tar -czf <tmp> -C {path.parent} {path.name}"
                        self.call_from_thread(
                            self._on_archive_action_worker_progress,
                            i - 1,
                            path.name,
                            "packing",
                            cmd,
                        )
                        packed_path = archive_pack_internal(self.base_dir, path)
                        logs.append(
                            ("info", f"packed: {path.name} -> {packed_path.name}")
                        )
                        removed_paths.append(path)
                        upsert_rows.append(
                            self._build_archived_row_from_entry(packed_path)
                        )
                    elif action == "unpack":
                        cmd = f"tar -xzf {path.name} -C <tmp>"
                        self.call_from_thread(
                            self._on_archive_action_worker_progress,
                            i - 1,
                            path.name,
                            "unpacking",
                            cmd,
                        )
                        unpacked_path = archive_unpack_internal(self.base_dir, path)
                        logs.append(
                            (
                                "info",
                                f"unpacked: {path.name} -> {unpacked_path.name}",
                            )
                        )
                        removed_paths.append(path)
                        upsert_rows.append(
                            self._build_archived_row_from_entry(unpacked_path)
                        )
                    elif action == "toggle_pack":
                        if is_packed_archive_path(path):
                            stage, verb = "unpacking", "unpacked"
                            cmd = f"tar -xzf {path.name} -C <tmp>"
                            op = archive_unpack_internal
                        else:
                            stage, verb = "packing", "packed"
                            cmd = f"tar -czf <tmp> -C {path.parent} {path.name}"
                            op = archive_pack_internal
                        self.call_from_thread(
                            self._on_archive_action_worker_progress,
                            i - 1,
                            path.name,
                            stage,
                            cmd,
                        )
                        new_path = op(self.base_dir, path)
                        logs.append(("info", f"{verb}: {path.name} -> {new_path.name}"))
                        removed_paths.append(path)
                        upsert_rows.append(
                            self._build_archived_row_from_entry(new_path)
                        )
                    else:
                        logs.append(("error", f"unknown archive action: {action}"))
                        failed += 1
                        continue
                    success += 1
                except (
                    OSError,
                    ValueError,
                    TypeError,
                    sqlite3.Error,
                    subprocess.SubprocessError,
                    yaml.YAMLError,
                    json.JSONDecodeError,
                ) as exc:
                    failed += 1
                    logs.append(
                        ("error", f"{action} failed for {path.name}: {exc}")
                    )

            self.call_from_thread(
                self._on_archive_action_worker_done,
                ArchiveActionOutcome(
                    action=action,
                    total=total,
                    success=success,
                    failed=failed,
                    removed_paths=removed_paths,
                    upsert_rows=upsert_rows,
                    logs=logs,
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_archive_action_worker_progress(
        self, done: int, current: str, stage: str, command: str
    ) -> None:
        self.action_worker_done = done
        self.action_worker_current = current
        self.action_worker_stage = stage
        self.action_worker_command = command
        self._refresh_side()

    def _on_archive_action_worker_done(self, outcome: ArchiveActionOutcome) -> None:
        self.action_worker_done = outcome.total
        self.action_worker_current = ""
        self.action_worker_running = False
        self.action_worker_action = ""
        self.action_worker_total = 0
        self.action_worker_started_ts = 0
        self.action_worker_stage = ""
        self.action_worker_command = ""
        self._busy_stop()

        for level, msg in outcome.logs:
            self._log(msg, level)

        if outcome.removed_paths:
            self._remove_paths_local(outcome.removed_paths)
        for row in outcome.upsert_rows:
            self._upsert_row_local(row)
        if outcome.removed_paths or outcome.upsert_rows:
            self._touch_rows_cache(
                outcome.upsert_rows, removed=outcome.removed_paths
            )
            self._start_cache_refresh(f"{outcome.action} update", force=False)
        else:
            self._refresh_data()
        self._refresh_table()
        self._log(
            f"{outcome.action} finished: ok={outcome.success}, failed={outcome.failed}",
            "info",
        )
        self._worker_debug(
            f"archive worker done: action={outcome.action} ok={outcome.success} failed={outcome.failed}"
        )
        self._refresh_side()

    def _on_confirm_bulk(self, ok: bool, action: str, paths: list[Path]) -> None:
        if not ok:
            self._log(f"{action} cancelled", "warn")
            self._refresh_side()
            return

        runnable_paths, skipped_paths = self._preflight_bulk_action(action, paths)
        if skipped_paths:
            self._log(
                f"{action} preflight skipped {len(skipped_paths)} item(s): {self._preflight_skip_summary(skipped_paths)}",
                "warn",
            )
        if not runnable_paths:
            self._log(f"{action} skipped: no eligible items", "warn")
            self._refresh_side()
            return

        if action == "restore":
            self.pending_restore_queue = list(runnable_paths)
            self.pending_restore_ok = 0
            self.pending_restore_failed = 0
            self._busy_start("restoring selected items")
            self._process_next_restore()
            return

        if action in {"pack", "unpack", "toggle_pack"}:
            self._start_archive_action_worker(action, list(runnable_paths))
            return

        success = 0
        failed = 0
        removed_paths: list[Path] = []
        upsert_rows: list[ProjectRow] = []
        self._busy_start(f"running {action} on selection")
        try:
            for path in runnable_paths:
                self._busy_tick()
                try:
                    if action == "archive":
                        dest = archive_move_internal(
                            self.base_dir, path, sync_tags=False
                        )
                        self._log(f"archived: {path.name} -> {dest}", "info")
                        removed_paths.append(path)
                        try:
                            upsert_rows.append(self._build_archived_row_from_entry(dest))
                        except _ROW_BUILD_ERRORS:
                            pass
                    elif action == "restore":
                        restored = archive_restore_internal(
                            self.base_dir, path, sync_tags=False
                        )
                        self._log(f"restored: {path.name} -> {restored}", "info")
                    elif action == "pack":
                        packed_path = archive_pack_internal(self.base_dir, path)
                        self._log(
                            f"packed: {path.name} -> {packed_path.name}", "info"
                        )
                        removed_paths.append(path)
                        try:
                            upsert_rows.append(
                                self._build_archived_row_from_entry(packed_path)
                            )
                        except _ROW_BUILD_ERRORS:
                            pass
                    elif action == "unpack":
                        unpacked_path = archive_unpack_internal(self.base_dir, path)
                        self._log(
                            f"unpacked: {path.name} -> {unpacked_path.name}", "info"
                        )
                        removed_paths.append(path)
                        try:
                            upsert_rows.append(
                                self._build_archived_row_from_entry(unpacked_path)
                            )
                        except _ROW_BUILD_ERRORS:
                            pass
                    elif action == "toggle_pack":
                        if is_packed_archive_path(path):
                            new_path = archive_unpack_internal(self.base_dir, path)
                            verb = "unpacked"
                        else:
                            new_path = archive_pack_internal(self.base_dir, path)
                            verb = "packed"
                        self._log(f"{verb}: {path.name} -> {new_path.name}", "info")
                        removed_paths.append(path)
                        try:
                            upsert_rows.append(
                                self._build_archived_row_from_entry(new_path)
                            )
                        except _ROW_BUILD_ERRORS:
                            pass
                    elif action == "delete":
                        delete_internal(self.base_dir, path, sync_tags=False)
                        self._log(f"deleted: {path}", "info")
                        removed_paths.append(path)
                    elif action == "review_meta":
                        ok, msg = open_meta_for_review(path)
                        if not ok:
                            failed += 1
                            self._log(
                                f"review failed for {path.name}: {msg}", "error"
                            )
                            continue
                        self._log(f"review opened: {path.name}", "info")
                    elif action == "rename_meta_ext":
                        ok, msg = rename_legacy_base_yaml(path)
                        if not ok:
                            failed += 1
                            self._log(
                                f"rename failed for {path.name}: {msg}", "error"
                            )
                            continue
                        self._log(
                            f"renamed metadata extension: {path.name}", "info"
                        )
                        try:
                            cur = self._find_row(path)
                            if cur is not None:
                                rws, ridx = cur
                                cur_row = rws[ridx]
                                upsert_rows.append(
                                    project_row(
                                        path,
                                        archived=cur_row.archived,
                                        restore_target=cur_row.restore_target,
                                        archived_ts=cur_row.archived_ts,
                                    )
                                )
                            else:
                                upsert_rows.append(
                                    project_row(path, archived=False)
                                )
                        except (
                            OSError,
                            ValueError,
                            TypeError,
                            subprocess.SubprocessError,
                            sqlite3.Error,
                        ):
                            pass
                    else:
                        self._log(f"unknown action: {action}", "error")
                        failed += 1
                        continue
                    success += 1
                    self.multi_selected.discard(path)
                except ValueError as exc:
                    failed += 1
                    self._log(f"{action} failed for {path.name}: {exc}", "error")
        finally:
            self._busy_stop()

        if removed_paths:
            self._remove_paths_local(removed_paths)
        if action in {"archive", "restore", "delete"}:
            self._request_tag_sync(f"{action} update")
        for row in upsert_rows:
            self._upsert_row_local(row)
        if removed_paths or upsert_rows:
            self._touch_rows_cache(upsert_rows, removed=removed_paths)
            self._start_cache_refresh(f"{action} update", force=False)
        else:
            self._refresh_data()
        self._refresh_table()
        self._log(f"{action} finished: ok={success}, failed={failed}", "info")
        self._refresh_side()

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
        try:
            restored = archive_restore_internal(self.base_dir, path, sync_tags=False)
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
        self._busy_start("restoring selected items")
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
            self._busy_start("restoring selected items")
            self._process_next_restore()
            return

        try:
            self._busy_start("restoring selected items")
            restored = archive_restore_internal(
                self.base_dir,
                archived_path,
                target_override=target,
                sync_tags=False,
            )
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
        self._busy_start("restoring selected items")
        self._process_next_restore()

    def _jump_to_tmux_pane(self, pane: PaneRef) -> bool:
        target_window = pane.target.rsplit(".", 1)[0]
        p1 = subprocess.run(
            [*_tmux_command_prefix(), "select-window", "-t", target_window],
            text=True,
            capture_output=True,
            check=False,
        )
        p2 = subprocess.run(
            [*_tmux_command_prefix(), "select-pane", "-t", pane.pane_id],
            text=True,
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
        profile = str(self.open_mode.get("profile", OPEN_MODE_CONFIG["profile"]))
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

    def action_open_existing_pane(self) -> None:
        if self._critical_job_active():
            self._log(
                f"cannot goto while critical job is running: {self._critical_job_label()}",
                "warn",
            )
            self._refresh_side()
            return
        row = self._selected_row()
        if not row:
            return
        self.pane_probe_fast_until_ts = max(
            self.pane_probe_fast_until_ts, time.time() + 25.0
        )
        panes = self.open_panes_by_project.get(row.path, [])
        if not panes:
            self._log(f"no open panes for {row.name}", "warn")
            self._refresh_side()
            return
        if len(panes) == 1:
            self._jump_to_tmux_pane(panes[0])
            return

        self.pending_pane_choices = {pane.pane_id: pane for pane in panes}
        self.push_screen(
            PaneChoiceScreen(f"Open pane for {row.name}", panes),
            self._on_pick_open_pane,
        )

    def action_open_selected(self) -> None:
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
        opened_ts = int(time.time())
        try:
            opened_ts = save_base_opened(row.path, opened_ts)
        except (sqlite3.Error, OSError, ValueError, TypeError):
            pass
        try:
            hit = self._find_row(row.path)
            if hit is not None:
                rows, idx = hit
                rows[idx].opened_ts = opened_ts
                rows[idx].stale = False
                rows[idx].cache_age_s = 0
                self._touch_rows_cache([rows[idx]])
        except (IndexError, AttributeError, TypeError, ValueError):
            pass

        if self._open_selected_in_tmux_mode(row):
            return

        self._flush_reconcile_usage_if_due()
        if self.reconcile_usage_dirty:
            self.reconcile_usage_due_at = 0.0
            self._flush_reconcile_usage_if_due()
        self._persist_state_now()
        self.fast_exit_requested = True
        self.exit(("open", row.path, []))

    def action_quit_app(self) -> None:
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
        self.fast_exit_requested = True
        self.exit(("quit", None, []))



def run_textual_ui(
    base_dir: Path,
    cwd: Path,
    start_new: bool = False,
    initial_filter_expr: str = "",
) -> tuple[str, Path | None, list[str]]:
    set_filter_query_base_dir(base_dir)
    set_filter_manage_base_dir(base_dir)
    return BApp(
        base_dir,
        start_new_mode=start_new,
        initial_filter=initial_filter_expr,
    ).run() or (
        "quit",
        None,
        [],
    )

