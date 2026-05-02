from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..archive import ops as archive_ops
from ..cache import queue as queue_utils
from ..commands import basic as commands_basic
from ..config.prefs import nested_discovery_enabled, set_nested_discovery_enabled
from ..core import nested as nested_utils
from ..core import prompting, setup_tools
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    BASE_MARKER_FILE,
    MODE_ACTIVE,
    MODE_ARCHIVE,
    NAMED_FILTERS,
    PACKED_ARCHIVE_SUFFIX,
    SORT_MODE_SPECS,
    TMUX_BIN_CANDIDATES,
)
from ..core.models import ProjectRow
from ..filter import engine as filter_engine
from ..metadata import property as property_utils
from ..metadata.api import (
    all_property_defs,
    property_tokens,
    sync_tag_symlinks_detailed,
)
from . import discovery as discovery_utils
from .projects import classify_name, project_row

DISCOVERY_PRUNE_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".direnv",
    "__pycache__",
}


def _resolve_include_nested(base_dir: Path, include_nested: bool | None) -> bool:
    return discovery_utils.resolve_include_nested(
        base_dir,
        include_nested,
        nested_discovery_enabled=nested_discovery_enabled,
    )


def _discovery_zone_depth(base_dir: Path, path: Path) -> tuple[str, int]:
    return discovery_utils.discovery_zone_depth(
        base_dir,
        path,
        archive_dir_name=ARCHIVE_DIR_NAME,
        mode_archive=MODE_ARCHIVE,
        mode_active=MODE_ACTIVE,
    )


def _discovery_marker_allowed(
    base_dir: Path,
    marker_dir: Path,
    include_nested: bool | None,
) -> bool:
    return discovery_utils.discovery_marker_allowed(
        base_dir,
        marker_dir,
        include_nested,
        zone_depth=_discovery_zone_depth,
        resolve_include_nested_fn=_resolve_include_nested,
    )


def _discovery_has_marker_ancestor(base_dir: Path, marker_dir: Path) -> bool:
    return discovery_utils.discovery_has_marker_ancestor(
        base_dir,
        marker_dir,
        base_marker_file=BASE_MARKER_FILE,
    )


def reconcile_queue_push(
    queue: list[tuple[int, str, str, list[Path]]],
    mode: str,
    reason: str,
    paths: list[Path],
    priority: int,
    limit: int = 40,
) -> list[tuple[int, str, str, list[Path]]]:
    return queue_utils.reconcile_queue_push(
        queue,
        mode,
        reason,
        paths,
        priority,
        limit=limit,
    )


def reconcile_queue_pop_next(
    queue: list[tuple[int, str, str, list[Path]]],
    worker_running: bool,
) -> tuple[
    list[tuple[int, str, str, list[Path]]], tuple[int, str, str, list[Path]] | None
]:
    return queue_utils.reconcile_queue_pop_next(
        queue,
        worker_running=worker_running,
    )


def _discovery_prune_walk_dirnames(dirnames: list[str]) -> None:
    discovery_utils.discovery_prune_walk_dirnames(
        dirnames,
        prune_names=DISCOVERY_PRUNE_DIR_NAMES,
    )


def _discovery_should_skip_active_walk_path(
    base_dir: Path,
    archive_root: Path,
    cur: Path,
) -> bool:
    return discovery_utils.discovery_should_skip_active_walk_path(
        base_dir,
        archive_root,
        cur,
        is_under=core_utils.is_under,
    )


def collect_workspace_rows(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
) -> tuple[list[ProjectRow], list[ProjectRow]]:
    nested = _resolve_include_nested(base_dir, include_nested)
    active = collect_projects(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=nested,
        size_cache=size_cache,
    )
    archived = collect_archived(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=nested,
        size_cache=size_cache,
    )
    return active, archived


def collect_projects(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
) -> list[ProjectRow]:
    rows = discovery_utils.collect_projects(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=include_nested,
        size_cache=size_cache,
        archive_dir_name=ARCHIVE_DIR_NAME,
        base_marker_file=BASE_MARKER_FILE,
        resolve_include_nested_fn=_resolve_include_nested,
        skip_active_walk_path=_discovery_should_skip_active_walk_path,
        prune_walk_dirnames=_discovery_prune_walk_dirnames,
        project_row=project_row,
    )
    return [row for row in rows if isinstance(row, ProjectRow)]


def archived_restore_target(base_dir: Path, archived_path: Path) -> Path:
    rel = archived_path.relative_to(base_dir / ARCHIVE_DIR_NAME)
    name = (
        core_utils.packed_archive_dir_name(rel, PACKED_ARCHIVE_SUFFIX)
        if str(rel).endswith(PACKED_ARCHIVE_SUFFIX)
        else rel.name
    )
    stem, ts = core_utils.split_archive_name(
        name,
        parse_timestamp=lambda value: core_utils.parse_archive_timestamp(value, ARCHIVE_TZ),
    )
    if ts > 0:
        rel = rel.with_name(stem)
    elif str(rel).endswith(PACKED_ARCHIVE_SUFFIX):
        rel = rel.with_name(name)
    return base_dir / rel


def collect_archived(
    base_dir: Path,
    include_git_dirty: bool = True,
    include_nested: bool | None = None,
    size_cache: dict[Path, tuple[int, int]] | None = None,
) -> list[ProjectRow]:
    rows = discovery_utils.collect_archived(
        base_dir,
        include_git_dirty=include_git_dirty,
        include_nested=include_nested,
        size_cache=size_cache,
        archive_dir_name=ARCHIVE_DIR_NAME,
        base_marker_file=BASE_MARKER_FILE,
        packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
        resolve_include_nested_fn=_resolve_include_nested,
        marker_allowed=_discovery_marker_allowed,
        has_marker_ancestor=_discovery_has_marker_ancestor,
        split_archive_entry_name=lambda path: core_utils.split_archive_entry_name(
            path,
            packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        ),
        archived_restore_target=archived_restore_target,
        project_row=project_row,
        classify_name=classify_name,
    )
    return [row for row in rows if isinstance(row, ProjectRow)]


def sort_rows(rows: list[ProjectRow], mode: str) -> list[ProjectRow]:
    if mode == "archived":
        return sorted(rows, key=lambda r: (r.archived_ts, r.last_ts), reverse=True)
    if mode == "created":
        return sorted(rows, key=lambda r: (r.created_ts, r.last_ts), reverse=True)
    if mode == "opened":
        return sorted(rows, key=lambda r: (r.opened_ts, r.last_ts), reverse=True)
    if mode == "restore_to":
        return sorted(
            rows,
            key=lambda r: ((str(r.restore_target or "").lower()), r.name.lower()),
        )
    if mode == "tags":
        return sorted(
            rows,
            key=lambda r: (
                ",".join(sorted(str(t).lower() for t in r.tags)),
                r.name.lower(),
            ),
        )
    if mode == "properties":
        return sorted(
            rows,
            key=lambda r: (
                ",".join(sorted(str(p).lower() for p in r.properties)),
                r.name.lower(),
            ),
        )
    if mode == "description":
        return sorted(rows, key=lambda r: (str(r.description).lower(), r.name.lower()))
    if mode == "size":
        return sorted(rows, key=lambda r: (int(r.size_bytes), r.name.lower()), reverse=True)
    if mode == "name":
        return sorted(rows, key=lambda r: r.name.lower())
    if mode == "git":
        return sorted(rows, key=lambda r: (r.git_ts, r.last_ts), reverse=True)
    return sorted(rows, key=lambda r: r.last_ts, reverse=True)


def _sort_modes_for_view(view_mode: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    vm = str(view_mode).strip()
    for spec in SORT_MODE_SPECS:
        sid = str(spec.get("id", "")).strip()
        label = str(spec.get("label", sid)).strip() or sid
        views = [str(v) for v in spec.get("views", [])]
        if sid and vm in views:
            out.append((sid, label))
    return out


def _normalize_sort_mode_for_view(view_mode: str, sort_mode: str) -> str:
    vm = str(view_mode).strip()
    sm = str(sort_mode).strip()
    allowed = {sid for sid, _label in _sort_modes_for_view(vm)}
    if sm in allowed:
        return sm
    return "last"


def match_query(row: ProjectRow, query: str) -> bool:
    q = query.strip().lower()
    if not q:
        return True
    hay = " ".join(
        [
            row.name,
            row.description,
            " ".join(row.tags),
            " ".join(row.properties),
            property_tokens(row.properties),
            row.branch,
            row.path.as_posix(),
        ]
    ).lower()
    return q in hay


_FILTER_TOKEN_RE = re.compile(r"\(|\)|\bOR\b|\||[^\s()|]+", re.IGNORECASE)


def _property_alias_set(key: str) -> set[str]:
    return property_utils.property_alias_set(key, all_defs=all_property_defs())


def compile_filter_expr(expr: str) -> tuple[Callable[[ProjectRow], bool], str | None]:
    return filter_engine.compile_filter_expr(
        expr,
        token_re=_FILTER_TOKEN_RE,
        match_query_fn=match_query,
        property_alias_set_fn=_property_alias_set,
        get_named_filter=lambda name: NAMED_FILTERS.get(name, ""),
    )


def query_uses_filter_syntax(text: str) -> bool:
    return filter_engine.query_uses_filter_syntax(text)


def normalize_filter_expression(expr: str) -> str:
    return filter_engine.normalize_filter_expression(expr, token_re=_FILTER_TOKEN_RE)


def pretty_filter_expression(expr: str) -> str:
    return filter_engine.pretty_filter_expression(expr, token_re=_FILTER_TOKEN_RE)


def print_help() -> None:
    print("b subcommands:")
    print("  global options: [--base-folder <path>] [--filter <name|expr>]")
    items = [
        ("b [--filter=<name|expr>]", "open Textual project overview"),
        ("b new", "interactive new project wizard"),
        ("b help", "show help"),
        ("b status", "workspace status table"),
        ("b recent", "projects sorted by last git commit"),
        (
            "b benchmark run [--comment TEXT] [--keep-basefolder]",
            "run synthetic performance benchmark",
        ),
        (
            "b benchmark results [--ignore-featureset set1,set2,...]",
            "show benchmark history table + trend",
        ),
        (
            "b test [--comment TEXT] [--keep-basefolder] | b test regression",
            "run performance or regression test suite",
        ),
        (
            "b setup [--yes|--no-tmux-binding]",
            "install symlink + verify runtime/tools/tmux binding",
        ),
        ("b cache warm", "pre-warm uv cache for textual/yaml"),
        ("b tags sync-_tags [--debug]", "rebuild _tags symlink index (verbose)"),
        (
            "b utils opt-in-nested-discovery",
            "inspect nested .base.yml in subfolders and enable nested discovery",
        ),
        ("b tmux load [dir]", "load .tmuxp.yaml into tmux"),
        ("b tmux save [dir]", "save current tmux window to .tmuxp.yaml"),
        ("b archive mv [path]", "archive directory"),
        ("b archive ls [path]", "list matching archives"),
        ("b archive undo [path]", "restore most recent archive by target path"),
        ("b archive restore <archived-path>", "restore exact archived entry"),
        ("b rm [--force-outside-base] [path]", "delete directory recursively"),
        (
            "b migrate [--archive] [--flat] <path> [path ...]",
            "move directories into ~/base or _archive",
        ),
        ("b fix [path]", "interactive repairs for a directory"),
        ("b a [path]", "alias for b archive mv [path]"),
    ]
    for cmd, desc in items:
        print(f"  {cmd:34} {desc}")


def _find_executable(name: str, extra_candidates: tuple[str, ...] = ()) -> str | None:
    return setup_tools.find_executable(name, extra_candidates)


def _recommended_tmux_save_binding(
    script_path: Path, uv_bin: str, tmux_bin: str
) -> str:
    return setup_tools.recommended_tmux_save_binding(script_path, uv_bin, tmux_bin)


def _compact_path_for_display(path_text: str) -> str:
    return setup_tools.compact_path_for_display(path_text)


def _binding_display_lines(binding: str, width: int = 88) -> list[str]:
    return setup_tools.binding_display_lines(binding, width=width)


def _has_recommended_tmux_binding(tmux_conf_text: str, expected_line: str) -> bool:
    return setup_tools.has_recommended_tmux_binding(tmux_conf_text, expected_line)


def _has_any_tmux_save_binding(tmux_conf_text: str) -> bool:
    return setup_tools.has_any_tmux_save_binding(tmux_conf_text)


def _write_tmux_binding(tmux_conf_path: Path, expected_line: str) -> None:
    setup_tools.write_tmux_binding(tmux_conf_path, expected_line)


def cmd_setup(bin_dir: Path, apply_tmux_binding: bool | None = None) -> int:
    return setup_tools.cmd_setup(
        bin_dir,
        tmux_bin_candidates=TMUX_BIN_CANDIDATES,
        apply_tmux_binding=apply_tmux_binding,
        cache_warm=cmd_cache_warm,
        prompt_yes_no=_prompt_yes_no,
    )


def cmd_cache_warm() -> int:
    return setup_tools.cmd_cache_warm()


def cmd_tags_sync(base_dir: Path, verbose: bool = True, debug: bool = False) -> int:
    return commands_basic.cmd_tags_sync(
        base_dir,
        sync_tag_symlinks_detailed=lambda bd, v, d: sync_tag_symlinks_detailed(
            bd,
            verbose=v,
            debug=d,
        ),
        verbose=verbose,
        debug=debug,
    )


def cmd_status(base_dir: Path) -> int:
    return commands_basic.cmd_status(base_dir, collect_projects=collect_projects)


def cmd_recent(base_dir: Path) -> int:
    return commands_basic.cmd_recent(
        base_dir,
        collect_projects=collect_projects,
        sort_rows=sort_rows,
        fmt_ymd=core_utils.fmt_ymd,
    )


def _scan_nested_project_paths(base_dir: Path) -> list[Path]:
    return nested_utils.scan_nested_project_paths(
        base_dir,
        archive_dir_name=ARCHIVE_DIR_NAME,
        base_marker_file=BASE_MARKER_FILE,
        discovery_should_skip_active_walk_path=_discovery_should_skip_active_walk_path,
        discovery_prune_walk_dirnames=_discovery_prune_walk_dirnames,
    )


def _suggest_flat_name(base_dir: Path, nested_path: Path) -> str:
    return nested_utils.suggest_flat_name(base_dir, nested_path)


def _prompt_readline(
    prompt: str,
    default: str | None = None,
    non_interactive_default: str | None = None,
) -> str | None:
    return prompting.prompt_readline(
        prompt,
        default=default,
        non_interactive_default=non_interactive_default,
    )


def _prompt_yes_no(question: str, default: bool) -> bool:
    return prompting.prompt_yes_no(question, default=default, read=_prompt_readline)


def _scan_nested_markers_all(
    base_dir: Path,
) -> tuple[dict[str, int], list[dict[str, object]]]:
    return nested_utils.scan_nested_markers_all(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        discovery_zone_depth=_discovery_zone_depth,
        discovery_marker_allowed=_discovery_marker_allowed,
    )


def cmd_utils_opt_in_nested_discovery(base_dir: Path) -> int:
    return nested_utils.cmd_utils_opt_in_nested_discovery(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        archive_dir_name=ARCHIVE_DIR_NAME,
        nested_discovery_enabled=nested_discovery_enabled,
        set_nested_discovery_enabled=set_nested_discovery_enabled,
        prompt_yes_no=_prompt_yes_no,
        scan_nested_markers_all_fn=_scan_nested_markers_all,
    )


def cmd_utils(base_dir: Path, subcommand: str) -> int:
    return nested_utils.cmd_utils(
        base_dir,
        subcommand,
        cmd_utils_opt_in_nested_discovery=cmd_utils_opt_in_nested_discovery,
    )



def resolve_archive_prefix(src: Path, base_dir: Path) -> str:
    return archive_ops.resolve_archive_prefix(src, base_dir)


def archive_destination(src: Path, base_dir: Path) -> Path:
    return archive_ops.archive_destination(
        src,
        base_dir,
        archive_dir_name=ARCHIVE_DIR_NAME,
        split_archive_name=lambda name: core_utils.split_archive_name(
            name,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        ),
        archive_iso_from_ts=lambda ts: core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ),
        archive_now_iso=lambda: core_utils.archive_now_iso(ARCHIVE_TZ),
    )
