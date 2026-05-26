from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..config.prefs import nested_discovery_enabled, set_nested_discovery_enabled
from ..core import nested as nested_utils
from ..core import prompting, setup_tools
from ..core import utils as core_utils
from ..core.constants import ARCHIVE_DIR_NAME, BASE_MARKER_FILE, TMUX_BIN_CANDIDATES
from ..metadata.api import sync_tag_symlinks_detailed
from ..workspace import discovery_helpers
from ..workspace.rows import collect_projects, sort_rows
from . import basic as commands_basic


def print_help() -> None:
    print("b subcommands:")
    print("  global options: [--base-folder <path>] [--filter <name|expr>]")
    items = [
        ("b [--filter=<name|expr>]", "open Textual project overview"),
        ("b new", "interactive new project wizard"),
        ("b help", "show help"),
        (
            "b ls [filter] [-l] [--git] [--archived]",
            "list projects (cache-backed; same filter syntax as the TUI)",
        ),
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
        ("b setup [--dry-run]", "validate environment + propose one-by-one fixes"),
        ("b cache warm", "pre-warm uv cache for textual/yaml"),
        ("b tags sync-_tags [--debug]", "rebuild _tags symlink index (verbose)"),
        (
            "b utils opt-in-nested-discovery",
            "inspect nested .base.yaml in subfolders and enable nested discovery",
        ),
        ("b tmux load [dir]", "load .tmuxp.yaml into tmux"),
        ("b tmux save [dir]", "save current tmux window to .tmuxp.yaml"),
        ("b archive mv [path]", "archive directory"),
        ("b archive ls [path]", "list matching archives"),
        ("b archive undo [path]", "restore most recent archive by target path"),
        ("b archive restore <archived-path>", "restore exact archived entry"),
        ("b rm [--force-outside-base] [path]", "delete directory recursively"),
        (
            "b migrate [--archive] <path> [path ...]",
            "move directories into ~/base or _archive",
        ),
        (
            "b fix [--all] [paths…]",
            "repair: add missing markers, normalize archive entries, "
            "relocate to <year>/ subdirs",
        ),
        ("b a [path]", "alias for b archive mv [path]"),
        (
            "b example generate --path <dir> [--count N] [--seed N]",
            "generate a demo base folder with random data (screenshots/testing)",
        ),
    ]
    for cmd, desc in items:
        print(f"  {cmd:34} {desc}")


def _prompt_readline(
    prompt: str,
    default: str | None = None,
    non_interactive_default: str | None = None,
) -> str | None:
    return prompting.prompt_readline(
        prompt,
        default=default,
        non_interactive_default=non_interactive_default,
        abort_on_interrupt=True,
    )


def _prompt_yes_no(question: str, default: bool) -> bool:
    return prompting.prompt_yes_no(question, default=default, read=_prompt_readline)


def cmd_setup(
    base_dir: Path,
    bin_dir: Path,
    *,
    completion_script_fn: Callable[[str], str] | None = None,
    shell_init_script_fn: Callable[[str], str] | None = None,
    dry_run: bool = False,
    json_output: bool = False,
) -> int:
    return setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=TMUX_BIN_CANDIDATES,
        prompt_yes_no=_prompt_yes_no,
        completion_script_fn=completion_script_fn,
        shell_init_script_fn=shell_init_script_fn,
        select_fix_ids_fn=None,
        dry_run=dry_run,
        json_output=json_output,
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


def cmd_tags_ls(base_dir: Path) -> int:
    from ..cache.api import cache_load_rows
    from ..workspace.rows import collect_workspace_rows

    def _load_rows(bd: Path):
        active, archived, _ts = cache_load_rows(bd)
        if not active and not archived:
            # Cold cache: fall back to a live scan so first-run output
            # isn't an empty tree.
            active, archived = collect_workspace_rows(bd, include_git_dirty=False)
        return active, archived

    return commands_basic.cmd_tags_ls(base_dir, load_rows=_load_rows)


def cmd_ls(
    base_dir: Path,
    *,
    filter_expr: str = "",
    long_format: bool = False,
    with_git: bool = False,
    show_archived: bool = False,
) -> int:
    from ..cache.api import cache_load_rows
    from ..workspace.filter_compile import compile_filter_expr
    from ..workspace.projects import git_info

    def _enrich_git(rows: list) -> None:
        # Live re-probe — the slow path the user explicitly asked for
        # via --git. Updates branch/dirty/git_ts in-place on the rows.
        for row in rows:
            try:
                branch, dirty, git_ts = git_info(row.path, include_dirty=True)
            except (OSError, ValueError):
                continue
            row.branch = branch
            row.dirty = dirty
            if git_ts:
                row.git_ts = git_ts

    return commands_basic.cmd_ls(
        base_dir,
        cache_load_rows=cache_load_rows,
        compile_filter_expr=compile_filter_expr,
        fmt_ymd=core_utils.fmt_ymd,
        fmt_size_human=core_utils.fmt_size_human,
        enrich_git=_enrich_git,
        filter_expr=filter_expr,
        long_format=long_format,
        with_git=with_git,
        show_archived=show_archived,
    )


def cmd_recent(base_dir: Path) -> int:
    return commands_basic.cmd_recent(
        base_dir,
        collect_projects=collect_projects,
        sort_rows=sort_rows,
        fmt_ymd=core_utils.fmt_ymd,
    )


def cmd_cd(base_dir: Path, name: str) -> int:
    from ..core.constants import ARCHIVE_DIR_NAME
    from ..tmux.flow import open_shell_in_dir

    return commands_basic.cmd_cd(
        base_dir,
        name,
        archive_dir_name=ARCHIVE_DIR_NAME,
        open_shell_in_dir=open_shell_in_dir,
    )


def _scan_nested_markers_all(
    base_dir: Path,
) -> tuple[dict[str, int], list[dict[str, object]]]:
    return nested_utils.scan_nested_markers_all(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        discovery_zone_depth=discovery_helpers.discovery_zone_depth,
        discovery_marker_allowed=discovery_helpers.discovery_marker_allowed,
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
