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
        ("b archive reorganize [--dry-run]", "move flat archive entries under year subdirs"),
        ("b fix [path]", "interactive repairs for a directory"),
        ("b a [path]", "alias for b archive mv [path]"),
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
) -> int:
    return setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=TMUX_BIN_CANDIDATES,
        prompt_yes_no=_prompt_yes_no,
        completion_script_fn=completion_script_fn,
        shell_init_script_fn=shell_init_script_fn,
        dry_run=dry_run,
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
