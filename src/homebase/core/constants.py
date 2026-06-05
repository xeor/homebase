from __future__ import annotations

import re
from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import BuiltinActionMeta, BuiltinHotkey, PropertyDef

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})$")
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_")
ARCHIVE_YEAR_DIR_RE = re.compile(r"^\d{4}$")
ARCHIVE_YEAR_PREFIX_RE = re.compile(r"^\d{4}")

DEFAULT_ARCHIVE_TZ_NAME = "Europe/Oslo"
ARCHIVE_TZ_NAME = DEFAULT_ARCHIVE_TZ_NAME
ARCHIVE_TZ: tzinfo
try:
    ARCHIVE_TZ = ZoneInfo(ARCHIVE_TZ_NAME)
except ZoneInfoNotFoundError:
    ARCHIVE_TZ = timezone.utc

MODE_ACTIVE = "active"
MODE_ARCHIVE = "archive"
LEVEL_INFO = "info"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

PROFILE_RECONCILE_ACTIVE = "reconcile-active"
PROFILE_RECONCILE_ARCHIVE = "reconcile-archive"
PROFILE_GIT_REFRESH_ACTIVE = "git-refresh-active"
PROFILE_GIT_REFRESH_ARCHIVE = "git-refresh-archive"
PROFILE_METADATA_HEALTH_ACTIVE = "metadata-health-active"
PROFILE_METADATA_HEALTH_ARCHIVE = "metadata-health-archive"
PROFILE_PANE_PROBE_ACTIVE = "pane-probe-active"
PROFILE_PANE_PROBE_ARCHIVE = "pane-probe-archive"

BASE_MARKER_FILE = ".base.yaml"
LEGACY_BASE_MARKER_FILE = ".base.yml"
HOMEBASE_DIR_NAME = ".homebase"
GLOBAL_CONFIG_FILE_NAME = "config.yaml"
CACHE_DB_FILE_NAME = "cache.sqlite3"
BENCHMARK_REPORT_FILE_NAME = "benchmark.yaml"
TEST_REPORT_FILE_NAME = "test.yaml"
REGRESSION_TEST_REPORT_FILE_NAME = "regression-test.yaml"
NESTED_DISCOVERY_REPORT_FILE_NAME = "nested-discovery.yaml"
ARCHIVE_DIR_NAME = "_archive"
PACKED_ARCHIVE_SUFFIX = ".tgz"
TMUX_BIN_CANDIDATES = (
    "/opt/homebrew/bin/tmux",
    "/usr/local/bin/tmux",
    "/usr/bin/tmux",
)
TMUX_SHELL_COMMANDS = {"sh", "bash", "zsh", "fish", "nu", "nushell", "tmux"}

COLOR_ERROR_HEX = "#FF6B6B"
COLOR_WARN_HEX = "#FFD166"
COLOR_INFO_HEX = "#7FB8FF"
COLOR_ACCENT_HEX = "#8ECFFF"
COLOR_SUCCESS_HEX = "#7DFF9B"
COLOR_AGE_UNIT_HEX = "#7CFC7C"
COLOR_NAV_HEX = "#4DA3FF"
COLOR_INTERACTIVE_HEX = "#3BC9B5"
COLOR_MUTED_HEX = "#8A94A6"
COLOR_ARCHIVE_HEX = "#8D84C6"
COLOR_DYNAMIC_ENV_HEX = "#FFB347"
COLOR_DYNAMIC_FILE_HEX = "#4DA3FF"
COLOR_DYNAMIC_STATE_HEX = "#8D84C6"
COLOR_PENDING_HEX = "#9AA0A6"
COLOR_WORKTREE_PARENT_HEX = "#8D84C6"

CURSOR_BG_HEX = "#FFFFFF"
CURSOR_FG_HEX = "#000000"

COLLISION_RED_RAMP = (
    COLOR_ERROR_HEX,
    "#FF8787",
    "#FFA8A8",
    "#FFC9C9",
    "#FFE3E3",
    "#D9DDE5",
)

BUILTIN_ACTIONS: dict[str, BuiltinActionMeta] = {
    "open_selected": BuiltinActionMeta(
        id="open_selected",
        default_label="Open selected (default)",
        help_text="Open selected target using current open mode",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "readme_create": BuiltinActionMeta(
        id="readme_create",
        default_label="Create README.md in $EDITOR",
        help_text="Create README.md with editor command",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "readme_edit": BuiltinActionMeta(
        id="readme_edit",
        default_label="Edit README.md in $EDITOR",
        help_text="Open README.md with editor command",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "notes_create": BuiltinActionMeta(
        id="notes_create",
        default_label="Create Notes markdown",
        help_text="Create note file from notes template",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "notes_open": BuiltinActionMeta(
        id="notes_open",
        default_label="Open Notes markdown",
        help_text="Open note file from notes template",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "tags_set": BuiltinActionMeta(
        id="tags_set",
        default_label="Tags...",
        help_text="Batch add/remove tags on target",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "reconcile_selection_cache": BuiltinActionMeta(
        id="reconcile_selection_cache",
        default_label="Reconcile target cache now",
        help_text="Refresh cache entries for target",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "hooks_refresh": BuiltinActionMeta(
        id="hooks_refresh",
        default_label="Refresh hooks on target",
        help_text="Re-run refresh logic for refreshable post-hooks on the target rows",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "hooks_refresh_view": BuiltinActionMeta(
        id="hooks_refresh_view",
        default_label="Refresh hooks for current view",
        help_text="Re-run refresh logic for refreshable post-hooks across all rows in view",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "suffix_set": BuiltinActionMeta(
        id="suffix_set",
        default_label="Suffix...",
        help_text="Set suffix category on target",
        scope="target",
        view_scope=("active",),
        default_confirm_prompt=None,
    ),
    "archive": BuiltinActionMeta(
        id="archive",
        default_label="archive target",
        help_text="Move target projects to archive",
        scope="target",
        view_scope=("active",),
        default_confirm_prompt="Confirm Archive",
    ),
    "restore": BuiltinActionMeta(
        id="restore",
        default_label="restore target",
        help_text="Restore archived projects to workspace",
        scope="target",
        view_scope=("archive",),
        default_confirm_prompt="Confirm Restore",
    ),
    "pack": BuiltinActionMeta(
        id="pack",
        default_label="pack target (.tgz)",
        help_text="Pack archived directories into .tgz",
        scope="target",
        view_scope=("archive",),
        default_confirm_prompt="Confirm Pack",
    ),
    "unpack": BuiltinActionMeta(
        id="unpack",
        default_label="unpack target",
        help_text="Unpack .tgz archive files",
        scope="target",
        view_scope=("archive",),
        default_confirm_prompt="Confirm Unpack",
    ),
    "toggle_pack": BuiltinActionMeta(
        id="toggle_pack",
        default_label="toggle pack/unpack target",
        help_text="Toggle pack/unpack on archive target",
        scope="target",
        view_scope=("archive",),
        default_confirm_prompt="Confirm Toggle Pack",
    ),
    "delete": BuiltinActionMeta(
        id="delete",
        default_label="delete target",
        help_text="Delete target entries permanently",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt="Confirm Delete",
    ),
    "set_desc": BuiltinActionMeta(
        id="set_desc",
        default_label="set description on target",
        help_text="Set description on target entries",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "rename_item": BuiltinActionMeta(
        id="rename_item",
        default_label="Rename item...",
        help_text="Rename target project folder(s)",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "new_worktree": BuiltinActionMeta(
        id="new_worktree",
        default_label="New worktree",
        help_text="Open the new-project dialog pre-filled to make a worktree from this project",
        scope="target",
        view_scope=("active",),
        default_confirm_prompt=None,
    ),
    "deworktree": BuiltinActionMeta(
        id="deworktree",
        default_label="De-worktree (make standalone)",
        help_text="Turn a worktree project into a standalone clone (copies parent .git)",
        scope="target",
        view_scope=("active",),
        default_confirm_prompt="Confirm de-worktree",
    ),
    "fix_worktrees": BuiltinActionMeta(
        id="fix_worktrees",
        default_label="Fix worktree health",
        help_text="Audit and repair worktree pointers across the workspace",
        scope="workspace",
        view_scope=("active",),
        default_confirm_prompt="Confirm worktree fix",
    ),
    "review_meta": BuiltinActionMeta(
        id="review_meta",
        default_label="Open .base.yaml and review warnings",
        help_text="Open metadata file for manual fix",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt="Confirm Metadata Review",
    ),
    "rename_meta_ext": BuiltinActionMeta(
        id="rename_meta_ext",
        default_label="Rename .base.yml -> .base.yaml",
        help_text="Rename .base.yml to .base.yaml",
        scope="target",
        view_scope=("active", "archive"),
        default_confirm_prompt="Confirm Metadata Rename",
    ),
    "refresh_cache": BuiltinActionMeta(
        id="refresh_cache",
        default_label="Refresh cache",
        help_text="Force full cache refresh now",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "full_reconcile": BuiltinActionMeta(
        id="full_reconcile",
        default_label="Full reconcile (force rescan)",
        help_text="Run full reconcile scan now",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "reconcile_all_cache": BuiltinActionMeta(
        id="reconcile_all_cache",
        default_label="Reconcile all cached rows now",
        help_text="Reconcile every cached row now",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "edit_global_config": BuiltinActionMeta(
        id="edit_global_config",
        default_label="Edit global config in $EDITOR",
        help_text="Open global config in editor and reload",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
    "reload_global_config": BuiltinActionMeta(
        id="reload_global_config",
        default_label="Reload global config",
        help_text="Reload global config without opening editor",
        scope="workspace",
        view_scope=("active", "archive"),
        default_confirm_prompt=None,
    ),
}


def discover_tab_actions() -> dict[str, BuiltinActionMeta]:
    out: dict[str, BuiltinActionMeta] = {}
    for top_key, top_label in SIDE_TOP_TABS:
        top_id = f"tab.{top_key}"
        out[top_id] = BuiltinActionMeta(
            id=top_id,
            default_label=str(top_label),
            help_text=f"Jump to {top_label} panel",
            scope="tab",
            view_scope=("active", "archive"),
            default_confirm_prompt=None,
        )
        for child_key, child_label in SIDE_CHILD_TABS.get(top_key, []):
            child_id = f"tab.{top_key}.{child_key}"
            out[child_id] = BuiltinActionMeta(
                id=child_id,
                default_label=str(child_label),
                help_text=f"Jump to {top_label} / {child_label}",
                scope="tab",
                view_scope=("active", "archive"),
                default_confirm_prompt=None,
            )
    return out

BUILTIN_HOTKEYS: tuple[BuiltinHotkey, ...] = (
    BuiltinHotkey("ctrl+n", "new_project", "New"),
    BuiltinHotkey("ctrl+p", "command_palette", "Command palette"),
    BuiltinHotkey("ctrl+s", "pick_sort", "Sort picker"),
    BuiltinHotkey("ctrl+f", "pick_filters", "Saved filters"),
    BuiltinHotkey("ctrl+c", "reset_view", "Reset view"),
    BuiltinHotkey("ctrl+l", "cycle_tabs", "tabs >"),
    BuiltinHotkey("ctrl+k", "cycle_tabs_prev", "tabs <"),
    BuiltinHotkey("ctrl+d", "toggle_view", "Toggle view"),
    BuiltinHotkey("ctrl+w", "toggle_wip", "Toggle WIP"),
    BuiltinHotkey("left", "route_left", "Left", show=False, priority=True),
    BuiltinHotkey("right", "route_right", "Right", show=False, priority=True),
    BuiltinHotkey("home", "route_home", "Home", show=False, priority=True),
    BuiltinHotkey("end", "route_end", "End", show=False, priority=True),
    BuiltinHotkey("alt+left", "table_scroll_left", "Scroll left", show=False, priority=True),
    BuiltinHotkey("alt+right", "table_scroll_right", "Scroll right", show=False, priority=True),
    BuiltinHotkey("ctrl+a", "pick_actions", "Actions"),
    BuiltinHotkey("ctrl+o", "toggle_select_mode", "Select mode"),
    BuiltinHotkey("ctrl+x", "dismiss_worktree_health", "Dismiss banner", show=False),
    BuiltinHotkey(
        "ctrl+y", "dismiss_cache_concurrency", "Dismiss cache drift banner", show=False
    ),
    BuiltinHotkey("ctrl+@", "cycle_hotbar_slot", "Next hotbar slot", show=False, priority=True),
    BuiltinHotkey("enter", "open_selected", "Open"),
    BuiltinHotkey("ctrl+q", "quit_app", "Quit"),
)

# Keys consumed by mode-specific input handlers in `ui/query/key_input.py`.
# They aren't part of the global BINDINGS list, but binding a user key to one
# of them would be confusing — the mode handler swallows the keypress first.
CONTEXT_RESERVED_HOTKEYS: tuple[tuple[str, str, str], ...] = (
    ("backspace",  "filter-edit", "Delete char left"),
    ("delete",     "filter-edit", "Delete char right"),
    ("ctrl+d",     "filter-edit", "Delete char right"),
    ("ctrl+a",     "filter-edit", "Cursor to start"),
    ("ctrl+e",     "filter-edit", "Cursor to end"),
    ("tab",        "completion",  "Apply query completion"),
    ("shift+tab",  "completion",  "Reverse query completion"),
    ("backtab",    "completion",  "Reverse query completion"),
    ("space",      "select-mode", "Toggle selection"),
    ("a",          "select-mode", "Select all"),
    ("c",          "select-mode", "Clear selection"),
    ("u",          "select-mode", "Select untagged"),
)


def reserved_hotkeys() -> dict[str, str]:
    """Map of hotkey -> reason it cannot be used for a user binding."""
    out: dict[str, str] = {}
    for hk in BUILTIN_HOTKEYS:
        out[hk.key] = f"built-in: {hk.action} ({hk.label})"
    for key, mode, label in CONTEXT_RESERVED_HOTKEYS:
        out.setdefault(key, f"{mode}: {label}")
    return out

ENV_BASE_DIR = "BASE_DIR"
WIDGET_PROJECTS = "#projects"
BUSY_LABEL_IDLE = "idle"
ACTION_ACCEPT = "accept"
ACTION_CANCEL = "cancel"

STATE_KEY_SIDE_MAIN = "side_main"
STATE_KEY_SIDE_SELECTED = "side_selected"
STATE_KEY_SIDE_INFO = "side_info"
STATE_KEY_SIDE_SETTINGS = "side_settings"
STATE_KEY_HOTBAR_SLOT_INDEX = "hotbar_selected_index"

SIDE_TAB_SELECTED_DEFAULT = "selected"
SIDE_TAB_OVERVIEW_DEFAULT = "overview"
SIDE_TAB_EVENTS_DEFAULT = "events"
SIDE_TAB_TABLE_DEFAULT = "table"


PROPERTY_DEFS: list[PropertyDef] = []
DYNAMIC_PROPERTY_DEFS: list[PropertyDef] = []
WIP_OPEN_SYMBOL_MAP: dict[str, int] = {
    "©": 1,
    "™": 2,
    "£": 3,
    "€": 4,
    "∞": 5,
    "§": 6,
    "|": 7,
    "[": 8,
    "]": 9,
}
NAMED_FILTERS: dict[str, str] = {}
SAVED_FILTER_QUERIES: list[str] = []
SUFFIXES: list[str] = ["tmp", "fork"]
FILE_VIEW_EXCLUDE_PATTERNS: list[str] = []
CUSTOM_ACTIONS: list[dict[str, str]] = []
CUSTOM_HOTKEYS: list[dict[str, str]] = []
OPEN_MODE_CONFIG: dict[str, str] = {
    "profile": "shell_cd",
}
NOTES_CONFIG: dict[str, object] = {
    "path_template": "{{ PROJECT_PATH }}/NOTES.md",
    "open_command": "${EDITOR:-vi} {{ NOTE_PATH_Q }}",
    "create_command": "mkdir -p \"$(dirname {{ NOTE_PATH_Q }})\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}",
    "log": {
        "section": {
            "title": "Log",
            "level": 2,
        },
        "entry": {
            "timestamp_format": "iso-seconds",
        },
    },
    "rename": {
        "enabled": True,
        "command": "mv {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}",
    },
}
VALID_NOTE_COMMANDS: frozenset[str] = frozenset({"add_log"})
TABLE_BEHAVIOR_CONFIG: dict[str, object] = {
    "pin_wip_top": False,
    "side_width_pct": 33,
    "preview_entries_limit": 8,
}
PREVIEW_ENTRIES_LIMIT_MIN = 1
PREVIEW_ENTRIES_LIMIT_MAX = 100
ARCHIVE_TZ_PRESETS: tuple[str, ...] = (
    "UTC",
    "Europe/Oslo",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
    "America/Los_Angeles",
    "Asia/Tokyo",
)
TABLE_DATE_COLOR_COLUMNS: tuple[str, ...] = (
    "created",
    "modified",
    "active",
    "archived_at",
)
TABLE_SIDE_WIDTH_PRESETS = [20, 25, 30, 33, 35, 40, 45, 50]
NEW_PROJECT_DEFAULTS: dict[str, object] = {
    "name_options": [],
    "template": None,
    "post_commands": [],
    "tags": [],
    "after_create": "open",
}
RECONCILE_USAGE_CACHE_LIMIT = 4000
OPEN_MODE_PROFILES: list[dict[str, object]] = [
    {
        "id": "shell_cd",
        "name": "Close b and cd to project",
        "note": "exit + shell",
        "use_tmux": False,
        "run_load": False,
        "goto_loaded": False,
        "fallback_cd": True,
    },
    {
        "id": "tmux_tab",
        "name": "Open in new tmux tab",
        "note": "tmux new-tab",
        "use_tmux": True,
        "run_load": False,
        "goto_loaded": False,
        "fallback_cd": True,
    },
    {
        "id": "tmux_tab_load",
        "name": "Goto existing tmux tab, else open new tab",
        "note": "goto-or-new",
        "use_tmux": True,
        "run_load": False,
        "goto_loaded": True,
        "fallback_cd": True,
    },
    {
        "id": "tmux_tab_load_or_goto",
        "name": "Open new tab + tmux load, or goto loaded",
        "note": "goto-or-load",
        "use_tmux": True,
        "run_load": True,
        "goto_loaded": True,
        "fallback_cd": True,
    },
]
BASE_META_ALLOWED_KEYS: set[str] = {
    "tags",
    "description",
    "wip",
    "log",
    "worktree",
    "repo_dir",
}
WORKTREE_META_ALLOWED_KEYS: set[str] = {
    "of",
    "branch",
    "parent_path",
    "gitdir_id",
}
HOOK_EVENTS: tuple[str, ...] = (
    "rename",
    "tag_change",
    "new_project",
    "delete",
)
HOOK_TIMINGS: tuple[str, ...] = ("pre", "post")
HOOK_VIEWS: tuple[str, ...] = ("active", "archive")
HOOK_SLOW_WARN_DEFAULT_S: float = 30.0
CACHE_SCHEMA_VERSION = 6
CACHE_MAX_AGE_S = 120
CACHE_BG_REFRESH_S = 30
SIZE_REFRESH_EVERY_N = 10

UI_TICK_BUSY_S = 0.12
UI_TICK_QUERY_FLUSH_S = 0.05
UI_TICK_STATE_FLUSH_S = 0.5
UI_TICK_RECONCILE_USAGE_FLUSH_S = 5.0
UI_TICK_PANE_PROBE_S = 0.5
UI_TICK_GIT_REFRESH_S = 0.8
UI_TICK_MICRO_RECONCILE_S = 0.25
UI_TICK_HOOK_REFRESH_S = 2.0
UI_TICK_WORKTREE_HEALTH_S = 60.0
BENCHMARK_SUITE_VERSION = 1
BENCHMARK_SCORE_MODEL = "pow(day/elapsed, k)"
BENCHMARK_SCORE_REF_SECONDS = 30.0
BENCHMARK_SCORE_REF_DAY_VALUE = 1.0
BENCHMARK_SCORE_WARM_WEIGHT = 0.7
BENCHMARK_SCORE_COLD_WEIGHT = 0.3
RECONCILE_CONFIG: dict[str, dict[str, object]] = {
    "active": {
        "enabled": True,
        "cache_profile": PROFILE_RECONCILE_ACTIVE,
    },
    "archive": {
        "enabled": True,
        "cache_profile": PROFILE_RECONCILE_ARCHIVE,
    },
}

CACHE_PROFILE_CONFIG: dict[str, dict[str, dict[str, object]]] = {
    "all": {
        PROFILE_RECONCILE_ACTIVE: {
            "update_interval_s": 5.0,
            "update_batch_size": 1,
            "update_priority": 30,
            "cache_mode": "ttl",
            "cache_ttl_s": 30.0,
            "use_usage_score": True,
            "usage_weight": 1.0,
            "stale_boost": True,
            "max_parallelism": 1,
        },
        PROFILE_RECONCILE_ARCHIVE: {
            "update_interval_s": 12.0,
            "update_batch_size": 1,
            "update_priority": 60,
            "cache_mode": "ttl",
            "cache_ttl_s": 120.0,
            "use_usage_score": True,
            "usage_weight": 1.0,
            "stale_boost": True,
            "max_parallelism": 1,
        },
        PROFILE_GIT_REFRESH_ACTIVE: {
            "update_interval_s": 0.8,
            "update_batch_size": 8,
            "update_priority": 20,
            "cache_mode": "ttl",
            "cache_ttl_s": 5.0,
            "max_parallelism": 1,
            "min_interval_s": 0.5,
        },
        PROFILE_GIT_REFRESH_ARCHIVE: {
            "update_interval_s": 2.0,
            "update_batch_size": 4,
            "update_priority": 50,
            "cache_mode": "ttl",
            "cache_ttl_s": 20.0,
            "max_parallelism": 1,
            "min_interval_s": 1.0,
        },
        PROFILE_METADATA_HEALTH_ACTIVE: {
            "update_interval_s": 1.0,
            "update_batch_size": 12,
            "update_priority": 25,
            "cache_mode": "ttl",
            "cache_ttl_s": 8.0,
            "max_parallelism": 1,
            "min_interval_s": 0.4,
        },
        PROFILE_METADATA_HEALTH_ARCHIVE: {
            "update_interval_s": 4.0,
            "update_batch_size": 4,
            "update_priority": 70,
            "cache_mode": "ttl",
            "cache_ttl_s": 25.0,
            "max_parallelism": 1,
            "min_interval_s": 1.0,
        },
        PROFILE_PANE_PROBE_ACTIVE: {
            "update_interval_s": 0.5,
            "update_batch_size": 400,
            "update_priority": 15,
            "cache_mode": "ttl",
            "cache_ttl_s": 5.0,
            "max_parallelism": 1,
            "min_interval_s": 0.2,
        },
        PROFILE_PANE_PROBE_ARCHIVE: {
            "update_interval_s": 6.0,
            "update_batch_size": 120,
            "update_priority": 65,
            "cache_mode": "ttl",
            "cache_ttl_s": 30.0,
            "max_parallelism": 1,
            "min_interval_s": 0.8,
        },
    }
}


SIDE_TOP_TABS: list[tuple[str, str]] = [
    ("selected", "Selected"),
    ("info", "Info"),
    ("settings", "Settings"),
]
SIDE_CHILD_TABS: dict[str, list[tuple[str, str]]] = {
    "selected": [
        ("overview", "Overview"),
        ("git", "Git"),
        ("files", "Files"),
        ("events", "Events"),
        ("readme", "README.md"),
        ("notes", "NOTES"),
    ],
    "info": [
        ("global", "Global"),
        ("events", "Events"),
        ("stats", "Stats and context"),
        ("cheat", "Cheat-sheet"),
        ("cache", "Runtime"),
        ("hooks", "Hooks"),
    ],
    "settings": [
        ("table", "Table"),
        ("table_config", "Config"),
        ("open", "Open"),
        ("global", "Config-file"),
    ],
}

TABLE_COLUMN_CATALOG: list[dict[str, object]] = [
    {
        "id": "mark",
        "label": "",
        "default": True,
        "width": 4,
        "views": ["active", "archive"],
    },
    {"id": "name", "default": True, "width": 34, "views": ["active", "archive"]},
    {"id": "git", "default": True, "width": 20, "views": ["active"]},
    {"id": "modified", "default": True, "width": 12, "views": ["active", "archive"]},
    {"id": "created", "default": False, "width": 12, "views": ["active", "archive"]},
    {"id": "active", "default": False, "width": 12, "views": ["active", "archive"]},
    {"id": "properties", "default": True, "width": 16, "views": ["active", "archive"]},
    {"id": "tags", "default": True, "width": 24, "views": ["active", "archive"]},
    {"id": "description", "default": False, "width": 28, "views": ["active", "archive"]},
    {"id": "size", "default": False, "width": 10, "views": ["active", "archive"]},
    {"id": "archived_at", "default": True, "width": 12, "views": ["archive"]},
    {"id": "original_name", "default": True, "width": 30, "views": ["archive"]},
]
TABLE_COLUMN_VIEWS = ("active", "archive")
SORT_MODE_SPECS: list[dict[str, object]] = [
    {"id": "last", "label": "last modified", "views": ["active", "archive"]},
    {"id": "opened", "label": "last active", "views": ["active", "archive"]},
    {"id": "git", "label": "git recency", "views": ["active", "archive"]},
    {"id": "created", "label": "created date", "views": ["active", "archive"]},
    {"id": "name", "label": "name", "views": ["active", "archive"]},
    {"id": "tags", "label": "tags", "views": ["active", "archive"]},
    {
        "id": "properties",
        "label": "properties",
        "views": ["active", "archive"],
    },
    {
        "id": "description",
        "label": "description",
        "views": ["active", "archive"],
    },
    {"id": "size", "label": "size", "views": ["active", "archive"]},
    {"id": "archived", "label": "archived date", "views": ["archive"]},
    {"id": "original_name", "label": "original name", "views": ["archive"]},
]
PROFILE_RECONCILE_ACTIVE = "reconcile-active"
PROFILE_RECONCILE_ARCHIVE = "reconcile-archive"
PROFILE_GIT_REFRESH_ACTIVE = "git-refresh-active"
PROFILE_GIT_REFRESH_ARCHIVE = "git-refresh-archive"
PROFILE_METADATA_HEALTH_ACTIVE = "metadata-health-active"
PROFILE_METADATA_HEALTH_ARCHIVE = "metadata-health-archive"
PROFILE_PANE_PROBE_ACTIVE = "pane-probe-active"
PROFILE_PANE_PROBE_ARCHIVE = "pane-probe-archive"
