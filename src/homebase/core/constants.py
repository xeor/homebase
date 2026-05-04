from __future__ import annotations

import re
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import PropertyDef

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})$")
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_")

DEFAULT_ARCHIVE_TZ_NAME = "Europe/Oslo"
ARCHIVE_TZ_NAME = DEFAULT_ARCHIVE_TZ_NAME
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
ARCHIVE_DIR_NAME = "_archive"
PACKED_ARCHIVE_SUFFIX = ".base-pkg.tgz"
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

ACTION_SHORT_HELP: dict[str, str] = {
    "readme_create": "Create README.md with editor command",
    "readme_edit": "Open README.md with editor command",
    "notes_create": "Create note file from notes template",
    "notes_open": "Open note file from notes template",
    "tags_set": "Batch add/remove tags on selection",
    "reconcile_selection_cache": "Refresh cache entries for selection",
    "suffix_set": "Set suffix category on selection",
    "archive": "Move selected projects to archive",
    "restore": "Restore archived projects to workspace",
    "pack": "Pack archived directories into .base-pkg.tgz",
    "unpack": "Unpack .base-pkg.tgz archive files",
    "toggle_pack": "Toggle pack/unpack on archive selection",
    "delete": "Delete selected entries permanently",
    "set_desc": "Set description on selected entries",
    "rename_item": "Rename focused project folder",
    "review_meta": "Open metadata file for manual fix",
    "rename_meta_ext": "Rename .base.yml to .base.yaml",
    "refresh_cache": "Force full cache refresh now",
    "full_reconcile": "Run full reconcile scan now",
    "reconcile_all_cache": "Reconcile every cached row now",
    "edit_global_config": "Open global config in editor and reload",
    "reload_global_config": "Reload global config without opening editor",
}

CUSTOM_ACTION_RESERVED_HOTKEYS: set[str] = {
    "ctrl+n",
    "ctrl+p",
    "ctrl+s",
    "ctrl+f",
    "ctrl+c",
    "ctrl+l",
    "ctrl+k",
    "ctrl+d",
    "ctrl+w",
    "ctrl+a",
    "ctrl+o",
    "ctrl+g",
    "ctrl+q",
    "enter",
    "left",
    "right",
    "home",
    "end",
    "alt+left",
    "alt+right",
    "tab",
    "shift+tab",
    "backtab",
    "ctrl+e",
    "backspace",
    "delete",
    "space",
    "a",
    "c",
    "u",
}

ENV_BASE_DIR = "BASE_DIR"
WIDGET_PROJECTS = "#projects"
BUSY_LABEL_IDLE = "idle"
ACTION_ACCEPT = "accept"
ACTION_CANCEL = "cancel"

STATE_KEY_SIDE_MAIN = "side_main"
STATE_KEY_SIDE_SELECTED = "side_selected"
STATE_KEY_SIDE_INFO = "side_info"
STATE_KEY_SIDE_SETTINGS = "side_settings"

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
NOTES_CONFIG: dict[str, str] = {
    "path_template": "{{ PROJECT_PATH }}/NOTES.md",
    "open_command": "${EDITOR:-vi} {{ NOTE_PATH_Q }}",
    "create_command": "mkdir -p \"$(dirname {{ NOTE_PATH_Q }})\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}",
}
TABLE_BEHAVIOR_CONFIG: dict[str, object] = {
    "pin_wip_top": False,
    "side_width_pct": 33,
}
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
}
CACHE_SCHEMA_VERSION = 5
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
BENCHMARK_SUITE_VERSION = 1
BENCHMARK_SCORE_MODEL = "pow(day/elapsed, k)"
BENCHMARK_SCORE_REF_SECONDS = 30.0
BENCHMARK_SCORE_REF_DAY_VALUE = 1.0
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
        ("stats", "Stats"),
        ("cheat", "Cheat-sheet"),
        ("cache", "Cache and workers"),
    ],
    "settings": [
        ("table", "Table"),
        ("table_config", "Table config"),
        ("open", "Open"),
        ("global", "Global config"),
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
    {
        "id": "name",
        "label": "NAME",
        "default": True,
        "width": 34,
        "views": ["active", "archive"],
    },
    {"id": "git", "label": "GIT", "default": True, "width": 20, "views": ["active"]},
    {
        "id": "last_modified",
        "label": "LAST",
        "default": True,
        "width": 12,
        "views": ["active", "archive"],
    },
    {
        "id": "created",
        "label": "CREATED",
        "default": False,
        "width": 12,
        "views": ["active", "archive"],
    },
    {
        "id": "last_opened",
        "label": "OPENED",
        "default": False,
        "width": 12,
        "views": ["active", "archive"],
    },
    {
        "id": "properties",
        "label": "PROPERTIES",
        "default": True,
        "width": 16,
        "views": ["active", "archive"],
    },
    {
        "id": "tags",
        "label": "TAGS",
        "default": True,
        "width": 24,
        "views": ["active", "archive"],
    },
    {
        "id": "description",
        "label": "DESCRIPTION",
        "default": False,
        "width": 28,
        "views": ["active", "archive"],
    },
    {
        "id": "size",
        "label": "SIZE",
        "default": False,
        "width": 10,
        "views": ["active", "archive"],
    },
    {
        "id": "archived_at",
        "label": "ARCHIVED_AT",
        "default": True,
        "width": 12,
        "views": ["archive"],
    },
    {
        "id": "restore_to",
        "label": "RESTORE_TO",
        "default": True,
        "width": 30,
        "views": ["archive"],
    },
]
TABLE_COLUMN_VIEWS = ("active", "archive")
SORT_MODE_SPECS: list[dict[str, object]] = [
    {"id": "last", "label": "last changed", "views": ["active", "archive"]},
    {"id": "opened", "label": "last opened", "views": ["active", "archive"]},
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
    {"id": "restore_to", "label": "restore target", "views": ["archive"]},
]
PROFILE_RECONCILE_ACTIVE = "reconcile-active"
PROFILE_RECONCILE_ARCHIVE = "reconcile-archive"
PROFILE_GIT_REFRESH_ACTIVE = "git-refresh-active"
PROFILE_GIT_REFRESH_ARCHIVE = "git-refresh-archive"
PROFILE_METADATA_HEALTH_ACTIVE = "metadata-health-active"
PROFILE_METADATA_HEALTH_ARCHIVE = "metadata-health-archive"
PROFILE_PANE_PROBE_ACTIVE = "pane-probe-active"
PROFILE_PANE_PROBE_ARCHIVE = "pane-probe-archive"
