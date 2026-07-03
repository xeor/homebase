from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    ARCHIVE_TZ_PRESETS,
    DEFAULT_ARCHIVE_TZ_NAME,
    OPEN_MODE_PROFILES,
)

# Field kinds the editor widget knows how to render.
FIELD_KINDS = ("text", "choice", "bool", "int", "list_csv")

# Per-preset apply intents (the apply-plan summary).
INTENT_ADD = "add"
INTENT_UPDATE = "update"
INTENT_REMOVE = "remove"
INTENT_KEEP = "keep"
INTENT_SKIP = "skip"

# Detection states for a preset against the current config.
STATE_SET = "set"
STATE_PARTIAL = "partial"
STATE_UNSET = "unset"

_MISSING = object()


@dataclass(frozen=True)
class ConfigField:
    """One editable parameter of a preset, bound to a nested config path."""

    key: str
    path: tuple[str, ...]
    label: str
    kind: str
    default: Any
    choices: tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class ConfigEnv:
    """Environment facts used to recommend presets."""

    platform: str = ""
    has_git: bool = False
    has_tmux: bool = False
    shell: str = ""


@dataclass(frozen=True)
class ConfigPreset:
    """A coherent config bundle: a static ``fragment`` plus editable ``fields``."""

    id: str
    title: str
    description: str
    category: str
    tags: tuple[str, ...] = ()
    fragment: dict[str, Any] = field(default_factory=dict)
    fields: tuple[ConfigField, ...] = ()
    recommend_when: Callable[[ConfigEnv], bool] | None = None


# --- nested dict primitives ------------------------------------------------


def _get(data: object, path: tuple[str, ...]) -> object:
    cur: object = data
    for part in path:
        if not isinstance(cur, Mapping) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _set(data: dict[str, Any], path: tuple[str, ...], value: object) -> None:
    cur = data
    for part in path[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[path[-1]] = copy.deepcopy(value)


def _del(data: dict[str, Any], path: tuple[str, ...]) -> None:
    """Delete a leaf and prune any parent dicts left empty."""
    stack: list[tuple[dict[str, Any], str]] = []
    cur: Any = data
    for part in path[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        stack.append((cur, part))
        cur = cur[part]
    if not isinstance(cur, dict) or path[-1] not in cur:
        return
    del cur[path[-1]]
    for parent, key in reversed(stack):
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            del parent[key]


def _flatten(data: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> Iterator[
    tuple[tuple[str, ...], object]
]:
    """Yield ``(path, value)`` for every non-mapping leaf (lists are leaves)."""
    for key, value in data.items():
        path = (*prefix, key)
        if isinstance(value, Mapping):
            yield from _flatten(value, path)
        else:
            yield path, value


def _deep_merge(dst: dict[str, Any], src: Mapping[str, Any]) -> None:
    for key, value in src.items():
        if isinstance(value, Mapping) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = copy.deepcopy(value)


# --- preset queries --------------------------------------------------------


def field_current_value(field_def: ConfigField, current: Mapping[str, Any]) -> object:
    value = _get(current, field_def.path)
    return None if value is _MISSING else value


def _enabled_field_value(
    field_def: ConfigField,
    current: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> object:
    if field_def.key in overrides:
        return overrides[field_def.key]
    existing = _get(current, field_def.path)
    if existing is not _MISSING:
        return existing
    return field_def.default


def detect_state(preset: ConfigPreset, current: Mapping[str, Any]) -> str:
    present = 0
    total = 0
    for path, value in _flatten(preset.fragment):
        total += 1
        if _get(current, path) == value:
            present += 1
    for f in preset.fields:
        total += 1
        if _get(current, f.path) is not _MISSING:
            present += 1
    if total == 0 or present == 0:
        return STATE_UNSET
    if present == total:
        return STATE_SET
    return STATE_PARTIAL


def preset_is_fully_present(preset: ConfigPreset, current: Mapping[str, Any]) -> bool:
    """True when every path the preset manages already exists in ``current``.

    Value-independent: a hand-edited value at one of these paths still counts
    as present, because enabling is non-destructive (it never overwrites an
    existing leaf). So a fully-present preset is a no-op to enable and reads
    as ``keep``."""
    if not preset.fragment and not preset.fields:
        return False
    for path, _ in _flatten(preset.fragment):
        if _get(current, path) is _MISSING:
            return False
    for f in preset.fields:
        if _get(current, f.path) is _MISSING:
            return False
    return True


def preset_is_selected_default(
    preset: ConfigPreset,
    current: Mapping[str, Any],
    env: ConfigEnv,
) -> bool:
    # Pre-check only presets that are a no-op to keep (already fully present)
    # or that are recommended for this environment while unset. Presets the
    # user has partially/differently configured stay unchecked so their
    # default plan is ``skip`` -- never a forced overwrite or removal of
    # hand-edited config.
    if preset_is_fully_present(preset, current):
        return True
    return bool(preset.recommend_when and preset.recommend_when(env))


def _desired_leaves(
    preset: ConfigPreset,
    current: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[tuple[str, ...], object]:
    """Leaves an enabled preset wants, honouring non-destructive fill-gaps.

    A ``fragment`` leaf that already exists keeps its current value (enabling
    never clobbers hand edits); only absent leaves take the preset value.
    ``field`` leaves resolve to override > existing > default, so a user's
    value is likewise preserved unless they explicitly edit the field."""
    leaves: dict[tuple[str, ...], object] = {}
    for path, value in _flatten(preset.fragment):
        existing = _get(current, path)
        leaves[path] = value if existing is _MISSING else existing
    for f in preset.fields:
        leaves[f.path] = _enabled_field_value(f, current, overrides)
    return leaves


def _preset_removal_paths(
    preset: ConfigPreset, current: Mapping[str, Any]
) -> list[tuple[str, ...]]:
    """Paths to delete on disable.

    A ``field`` path is dedicated to its preset, so it is removed whenever
    present (disabling means "I no longer want this setting"). ``fragment``
    leaves can overlap with unrelated hand-edited config, so they are only
    removed when they still equal what the preset would have written."""
    paths: list[tuple[str, ...]] = []
    for path, value in _flatten(preset.fragment):
        if _get(current, path) == value:
            paths.append(path)
    for f in preset.fields:
        if _get(current, f.path) is not _MISSING:
            paths.append(f.path)
    return paths


def apply_presets(
    current: Mapping[str, Any],
    enabled_ids: set[str],
    overrides: Mapping[str, Mapping[str, Any]],
    catalog: list[ConfigPreset],
    *,
    removable_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Build the desired config.

    Enabling is non-destructive: each preset's leaves are filled via
    ``_desired_leaves`` (existing values win over preset defaults). Disabling
    removes a preset's owned paths, but only for presets in ``removable_ids``
    (the set that was active at load / last apply); ``None`` means every
    preset is removable (used by the pure-model tests)."""
    result = copy.deepcopy(dict(current))
    for preset in catalog:
        if preset.id in enabled_ids:
            leaves = _desired_leaves(preset, current, overrides.get(preset.id, {}))
            for path, value in leaves.items():
                _set(result, path, value)
        elif removable_ids is None or preset.id in removable_ids:
            for path in _preset_removal_paths(preset, current):
                _del(result, path)
    return result


def _preset_change(
    preset: ConfigPreset,
    current: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> tuple[bool, bool]:
    """Return ``(adds, modifies)`` for enabling ``preset``.

    ``adds`` -> the preset would create at least one absent leaf.
    ``modifies`` -> it would change an existing leaf's value (only possible
    via a field override, since fragments never overwrite)."""
    adds = False
    modifies = False
    for path, value in _desired_leaves(preset, current, overrides).items():
        existing = _get(current, path)
        if existing is _MISSING:
            adds = True
        elif existing != value:
            modifies = True
    return adds, modifies


def plan_intents(
    current: Mapping[str, Any],
    enabled_ids: set[str],
    overrides: Mapping[str, Mapping[str, Any]],
    catalog: list[ConfigPreset],
    *,
    removable_ids: set[str] | None = None,
) -> dict[str, str]:
    intents: dict[str, str] = {}
    for preset in catalog:
        if preset.id in enabled_ids:
            adds, modifies = _preset_change(
                preset, current, overrides.get(preset.id, {})
            )
            if modifies:
                intents[preset.id] = INTENT_UPDATE
            elif adds:
                intents[preset.id] = INTENT_ADD
            else:
                intents[preset.id] = INTENT_KEEP
        else:
            removable = removable_ids is None or preset.id in removable_ids
            if removable and _preset_removal_paths(preset, current):
                intents[preset.id] = INTENT_REMOVE
            else:
                intents[preset.id] = INTENT_SKIP
    return intents


# --- catalog ---------------------------------------------------------------


def _badge(label: str, color: str, **detector: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"label": label, "color": color}
    out.update(detector)
    return out


def build_presets(env: ConfigEnv) -> list[ConfigPreset]:
    return [
        ConfigPreset(
            id="archive_timezone",
            title="Archive timezone",
            description="IANA timezone used for archive date parsing and formatting.",
            category="Archive",
            tags=("archive", "time"),
            fields=(
                ConfigField(
                    key="timezone",
                    path=("archive", "timezone"),
                    label="Timezone",
                    kind="text",
                    default=DEFAULT_ARCHIVE_TZ_NAME,
                    choices=ARCHIVE_TZ_PRESETS,
                    help="Any IANA zone name; choices are common presets.",
                ),
            ),
        ),
        ConfigPreset(
            id="open_mode",
            title="Default open behavior",
            description="What UI open actions do (shell cd vs tmux tab/load).",
            category="Behavior",
            tags=("open", "tmux"),
            fields=(
                ConfigField(
                    key="profile",
                    path=("open_mode", "profile"),
                    label="Profile",
                    kind="choice",
                    default="shell_cd",
                    choices=tuple(str(p["id"]) for p in OPEN_MODE_PROFILES),
                    help="shell_cd / tmux_tab / tmux_tab_load / tmux_tab_load_or_goto.",
                ),
            ),
        ),
        ConfigPreset(
            id="tmux_focus",
            title="macOS tmux focus backend",
            description="Backend that brings the terminal frontmost on `b open`.",
            category="Behavior",
            tags=("tmux", "macos"),
            fields=(
                ConfigField(
                    key="method",
                    path=("tmux_focus", "method"),
                    label="Backend",
                    kind="choice",
                    default="auto",
                    choices=("auto", "appkit", "osascript", "system_events"),
                    help="macOS only; auto tries appkit -> osascript -> system_events.",
                ),
            ),
            recommend_when=lambda e: e.platform == "darwin",
        ),
        ConfigPreset(
            id="suffixes",
            title="Project name suffixes",
            description="Suffixes stripped/recognised on project folder names.",
            category="Workspace",
            tags=("project", "naming"),
            fields=(
                ConfigField(
                    key="suffixes",
                    path=("suffixes",),
                    label="Suffixes (comma separated)",
                    kind="list_csv",
                    default=["tmp", "fork", "old"],
                    help="Comma-separated list, e.g. tmp,fork,old.",
                ),
            ),
        ),
        ConfigPreset(
            id="reconcile_pacing",
            title="Reconcile pacing",
            description="How fast the active/archive reconcile workers scan rows.",
            category="Performance",
            tags=("performance", "sync"),
            fields=(
                ConfigField(
                    key="active_interval",
                    path=("reconcile", "active", "interval_s"),
                    label="Active interval (s)",
                    kind="int",
                    default=5,
                    help="Seconds between active-reconcile passes.",
                ),
                ConfigField(
                    key="active_batch",
                    path=("reconcile", "active", "batch_size"),
                    label="Active batch size",
                    kind="int",
                    default=1,
                    help="Rows updated per active-reconcile pass.",
                ),
                ConfigField(
                    key="archive_interval",
                    path=("reconcile", "archive", "interval_s"),
                    label="Archive interval (s)",
                    kind="int",
                    default=12,
                    help="Seconds between archive-reconcile passes.",
                ),
                ConfigField(
                    key="archive_batch",
                    path=("reconcile", "archive", "batch_size"),
                    label="Archive batch size",
                    kind="int",
                    default=1,
                    help="Rows updated per archive-reconcile pass.",
                ),
            ),
        ),
        ConfigPreset(
            id="table_behavior",
            title="Table behavior",
            description="Pin WIP rows on top and set the side-panel width.",
            category="Table",
            tags=("table", "layout"),
            fields=(
                ConfigField(
                    key="pin_wip_top",
                    path=("table", "behavior", "pin_wip_top"),
                    label="Pin WIP rows on top",
                    kind="bool",
                    default=False,
                ),
                ConfigField(
                    key="side_width_pct",
                    path=("table", "behavior", "side_width_pct"),
                    label="Side panel width (%)",
                    kind="int",
                    default=33,
                    help="Percentage of the screen used by the side panel.",
                ),
                ConfigField(
                    key="preview_entries_limit",
                    path=("table", "behavior", "preview_entries_limit"),
                    label="Preview entries limit",
                    kind="int",
                    default=8,
                    help="Max file entries shown in the side-panel preview.",
                ),
            ),
        ),
        ConfigPreset(
            id="raycast_sort",
            title="Raycast project sort",
            description="Ordering of the project list in the Raycast extension.",
            category="Integrations",
            tags=("raycast", "integration"),
            fields=(
                ConfigField(
                    key="sort",
                    path=("raycast", "sort"),
                    label="Sort order",
                    kind="choice",
                    default="name",
                    choices=("name", "opened"),
                    help="name = alphabetical; opened = newest last-opened first.",
                ),
            ),
        ),
        ConfigPreset(
            id="file_view_excludes",
            title="File-view excludes",
            description="Names/globs hidden from the project file view.",
            category="Workspace",
            tags=("files", "ignore"),
            fields=(
                ConfigField(
                    key="patterns",
                    path=("files_view", "exclude_patterns"),
                    label="Exclude patterns (comma separated)",
                    kind="list_csv",
                    default=[
                        ".DS_Store",
                        ".git",
                        "node_modules",
                        "__pycache__",
                        ".venv",
                        "dist",
                        "build",
                    ],
                    help="Comma-separated names/globs, e.g. node_modules,*.pyc.",
                ),
            ),
        ),
        ConfigPreset(
            id="notes_integration",
            title="Notes integration",
            description="Per-project NOTES.md path plus open/create commands.",
            category="Notes",
            tags=("notes", "markdown"),
            fragment={
                "notes": {
                    "path_template": "{{ PROJECT_PATH }}/NOTES.md",
                    "open_command": "${EDITOR:-vi} {{ NOTE_PATH_Q }}",
                    "create_command": (
                        'mkdir -p "$(dirname {{ NOTE_PATH_Q }})" '
                        "&& touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}"
                    ),
                    "rename": {
                        "enabled": True,
                        "command": "mv {{ OLD_NOTE_PATH_Q }} {{ NEW_NOTE_PATH_Q }}",
                    },
                }
            },
        ),
        ConfigPreset(
            id="property_badges_worktree",
            title="Worktree property badges",
            description="Row badges for git worktrees: worktree pointer and any-git.",
            category="Properties",
            tags=("badges", "worktree"),
            fragment={
                "properties": {
                    "WT": _badge(
                        "Git worktree", "#8d84c6", **{"file-exists": [".git"]}
                    ),
                    "ANYGIT": _badge(
                        "Git repo or worktree", "#7dd3a7", **{"path-exists": [".git"]}
                    ),
                }
            },
        ),
        ConfigPreset(
            id="property_badges_core",
            title="Core property badges",
            description="Common project-row badges: git, python, node, container, envrc.",
            category="Properties",
            tags=("badges", "git"),
            fragment={
                "properties": {
                    "GIT": _badge("Git repo", "#87afff", **{"dir-exists": [".git"]}),
                    "PY": _badge(
                        "Python project",
                        "#7dcfff",
                        **{"file-exists": ["pyproject.toml", "requirements.txt"]},
                    ),
                    "JS": _badge(
                        "Node package", "#7dcfff", **{"file-exists": ["package.json"]}
                    ),
                    "CNT": _badge(
                        "Container file",
                        "#8be9fd",
                        **{"file-exists": ["Containerfile", "Dockerfile", "docker-compose.yml"]},
                    ),
                    "ENV": _badge("envrc", "#8be9fd", **{"file-exists": [".envrc"]}),
                }
            },
        ),
        ConfigPreset(
            id="saved_filters_starter",
            title="Starter saved filters",
            description="A couple of saved + named query-bar filters to get going.",
            category="Filters",
            tags=("filters", "search"),
            fragment={
                "filters": {
                    "saved": ["#wip", ":tags=0", ":modified=@-7d"],
                    "named": {"hot": "#cli OR #api", "stale": ":modified<=@-60d"},
                }
            },
        ),
        ConfigPreset(
            id="color_variables",
            title="Color palette variables",
            description="Reusable `{{ _COLOR_* }}` hex variables for badges/styles.",
            category="Properties",
            tags=("colors", "variables"),
            fragment={
                "variables": {
                    "_COLOR_CORE": "#7dcfff",
                    "_COLOR_INFRA": "#8be9fd",
                    "_COLOR_DYN": "#ffb86c",
                    "_COLOR_META": "#a6adc8",
                    "_COLOR_FILE": "#87afff",
                    "_COLOR_PKG": "#bd93f9",
                    "_COLOR_WARN": "#f1fa8c",
                    "_COLOR_ERR": "#ff5555",
                }
            },
        ),
        ConfigPreset(
            id="property_badges_languages",
            title="Language property badges",
            description="Row badges for Go and Rust projects.",
            category="Properties",
            tags=("badges", "language"),
            fragment={
                "properties": {
                    "GO": _badge("Go module", "#7dcfff", **{"file-exists": ["go.mod"]}),
                    "RS": _badge(
                        "Rust project", "#7dcfff", **{"file-exists": ["Cargo.toml"]}
                    ),
                }
            },
        ),
        ConfigPreset(
            id="property_badges_activity",
            title="Activity property badges",
            description="Live badges: active tmux pane and editor running.",
            category="Properties",
            tags=("badges", "tmux"),
            fragment={
                "properties": {
                    "TMX": _badge(
                        "Active tmux",
                        "#ffb86c",
                        cache_ttl_s=3,
                        queries=[{"type": "tmux_open_panes"}],
                    ),
                    "EDT": _badge(
                        "Editor active",
                        "#ffb86c",
                        cache_ttl_s=8,
                        queries=[
                            {
                                "type": "tmux_editor_commands",
                                "commands": [
                                    "code",
                                    "code-insiders",
                                    "codium",
                                    "cursor",
                                    "zed",
                                    "nvim",
                                    "vim",
                                    "hx",
                                    "emacs",
                                    "subl",
                                ],
                            }
                        ],
                    ),
                }
            },
        ),
        ConfigPreset(
            id="property_badges_docs",
            title="Docs property badges",
            description="Row badges for a docs/ directory and README.md.",
            category="Properties",
            tags=("badges", "docs"),
            fragment={
                "properties": {
                    "DOC": _badge(
                        "Docs dir", "#a6adc8", **{"dir-exists": ["docs"]}
                    ),
                    "RM": _badge(
                        "README", "#87afff", **{"file-exists": ["README.md"]}
                    ),
                }
            },
        ),
        ConfigPreset(
            id="property_badges_health",
            title="Health property badges",
            description="Metadata warning/error markers and packed-archive badge.",
            category="Properties",
            tags=("badges", "health"),
            fragment={
                "properties": {
                    "W": _badge(
                        "Metadata warning",
                        "#f1fa8c",
                        queries=[{"type": "metadata_health", "level": "warning"}],
                    ),
                    "E": _badge(
                        "Metadata error",
                        "#ff5555",
                        queries=[{"type": "metadata_health", "level": "error"}],
                    ),
                    "PKG": _badge(
                        "Packed archive",
                        "#bd93f9",
                        queries=[{"type": "packed_archive"}],
                    ),
                }
            },
        ),
        ConfigPreset(
            id="wip_hotkeys",
            title="WIP marker hotkeys",
            description="Digit keys mapped to WIP marker glyphs.",
            category="Behavior",
            tags=("wip", "hotkeys"),
            fragment={
                "wip": {
                    "hotkeys": {
                        "1": "©",
                        "2": "™",
                        "3": "£",
                        "4": "€",
                        "5": "∞",
                        "6": "§",
                        "7": "|",
                        "8": "[",
                        "9": "]",
                    }
                }
            },
        ),
        ConfigPreset(
            id="raycast_subtitle",
            title="Raycast row subtitle",
            description="Extra info shown under each Raycast project result.",
            category="Integrations",
            tags=("raycast", "subtitle"),
            fragment={
                "raycast": {
                    "secondary_info": ["{{ opened_ago }}", "{{ tags_space }}"],
                    "secondary_separator": " • ",
                }
            },
        ),
        ConfigPreset(
            id="date_color_gradient",
            title="Date color gradient",
            description="Age heatmap for date columns (blue=new -> red=old).",
            category="Table",
            tags=("table", "colors"),
            fragment={
                "table": {
                    "columns_style": {
                        "date": {
                            "all": {
                                "modified": {
                                    0: "#38bdf8",
                                    10: "#22c55e",
                                    100: "#facc15",
                                    250: "#f97316",
                                    365: "#ef4444",
                                }
                            }
                        }
                    }
                }
            },
        ),
        ConfigPreset(
            id="new_project_after_create",
            title="New project after-create",
            description="Whether `b new` opens the new project or stays in the list.",
            category="Workspace",
            tags=("new", "workflow"),
            fields=(
                ConfigField(
                    key="after_create",
                    path=("new_project", "after_create"),
                    label="After create",
                    kind="choice",
                    default="open",
                    choices=("open", "stay"),
                    help="open = enter the new project; stay = keep the current view.",
                ),
            ),
        ),
        ConfigPreset(
            id="new_sources_starter",
            title="Starter `b new` sources",
            description="Throwaway source presets: timestamped tmp and sequential alpha.",
            category="Workspace",
            tags=("new", "sources"),
            fragment={
                "new": {
                    "sources": {
                        "tmp": {
                            "parent": "empty",
                            "timestamp": True,
                            "tmp": True,
                            "ts-name": True,
                            "tags": ["scratch"],
                        },
                        "alpha": {
                            "parent": "empty",
                            "alpha-name": True,
                            "tags": ["scratch"],
                        },
                    }
                }
            },
        ),
        ConfigPreset(
            id="editor_actions",
            title="Editor open actions",
            description="Custom actions to open an item or the base dir in $EDITOR.",
            category="Actions",
            tags=("actions", "editor"),
            fragment={
                "actions": {
                    "open_item_in_editor": {
                        "kind": "shell",
                        "scope": "target",
                        "multi": "joined",
                        "command": "$EDITOR {{ paths_q }}",
                    },
                    "open_base_in_editor": {
                        "kind": "shell",
                        "scope": "workspace",
                        "command": "$EDITOR {{ base_dir_q }}",
                    },
                }
            },
        ),
        ConfigPreset(
            id="tag_rules_starter",
            title="Starter tag rules",
            description="Example tag grouping/styling (programming roll-up, prio:, wip).",
            category="Filters",
            tags=("tags", "grouping"),
            fragment={
                "tag_rules": [
                    {"match": "^prio:", "parents": ["priority"], "color": "#ff5555", "bold": True, "prefix": "⚡ "},
                    {"match": "^wip$", "suffix": " \U0001f525"},
                    {"tags": ["python", "rust", "go"], "parents": ["programming"]},
                    {"tags": ["priority"], "parents": ["meta"], "group_only": True},
                    {"tags": ["meta"], "group_only": True},
                ]
            },
        ),
    ]


__all__ = [
    "ConfigEnv",
    "ConfigField",
    "ConfigPreset",
    "FIELD_KINDS",
    "INTENT_ADD",
    "INTENT_KEEP",
    "INTENT_REMOVE",
    "INTENT_SKIP",
    "INTENT_UPDATE",
    "STATE_PARTIAL",
    "STATE_SET",
    "STATE_UNSET",
    "apply_presets",
    "build_presets",
    "detect_state",
    "field_current_value",
    "plan_intents",
    "preset_is_selected_default",
]
