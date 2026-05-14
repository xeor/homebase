from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .parser import parse_ignore_featureset_values


def dispatch_command(
    ns: Any,
    *,
    parser: argparse.ArgumentParser,
    base_dir: Path,
    bin_dir: Path,
    cwd: Path,
    no_arg_flow: Callable[[Path, Path, str], int],
    cmd_status: Callable[[Path], int],
    cmd_new: Callable[[Any, Path, Path], int],
    cmd_completion: Callable[[str], int],
    cmd_internal_complete: Callable[[str, int, list[str]], int],
    cmd_recent: Callable[[Path], int],
    cmd_help_actions: Callable[[str, str, str, bool], int],
    cmd_setup: Callable[[Path, Path, bool], int],
    cmd_cache_warm: Callable[[], int],
    cmd_tags_sync: Callable[[Path, bool, bool], int],
    cmd_utils: Callable[[Path, str], int],
    cmd_archive_mv: Callable[[Path, str], int],
    cmd_rm: Callable[[str, bool], int],
    cmd_fix: Callable[[str], int],
    cmd_archive_ls: Callable[[Path, str], int],
    cmd_archive_undo: Callable[[Path, str], int],
    cmd_archive_restore_entry: Callable[[Path, str], int],
    cmd_archive_reorganize: Callable[[Path, bool], int],
    cmd_tmux_load: Callable[[str], int],
    cmd_tmux_save: Callable[[Path, str, str, bool, bool, str, str], int],
    cmd_benchmark: Callable[[Path, Path, str, str, bool, set[str] | None], int],
    cmd_test_regression: Callable[[Path, Path, bool, list[str]], int],
    cmd_test: Callable[[Path, Path, str, bool], int],
    initial_filter_expr: str,
) -> int:
    if ns.command is None:
        return no_arg_flow(base_dir, cwd, initial_filter_expr)
    if ns.command == "help":
        if str(getattr(ns, "topic", "")).strip() == "actions":
            return cmd_help_actions(
                str(getattr(ns, "source", "")).strip(),
                str(getattr(ns, "bound", "")).strip(),
                str(getattr(ns, "view", "")).strip(),
                bool(getattr(ns, "show_defaults", False)),
            )
        parser.print_help()
        return 0
    if ns.command == "status":
        return cmd_status(base_dir)
    if ns.command in {"new", "n"}:
        return cmd_new(ns, base_dir, cwd)
    if ns.command == "completion":
        return cmd_completion(str(ns.shell))
    if ns.command == "__complete":
        return cmd_internal_complete(
            str(ns.shell),
            int(ns.cword),
            [str(x) for x in ns.words],
        )
    if ns.command == "recent":
        return cmd_recent(base_dir)
    if ns.command == "setup":
        return cmd_setup(base_dir, bin_dir, bool(getattr(ns, "dry_run", False)))
    if ns.command == "cache":
        return cmd_cache_warm() if ns.cache_subcommand == "warm" else 1
    if ns.command == "tags":
        if ns.tags_subcommand == "sync-_tags":
            return cmd_tags_sync(base_dir, True, bool(ns.debug))
        return 1
    if ns.command == "utils":
        return cmd_utils(base_dir, str(ns.utils_subcommand))
    if ns.command == "a":
        return cmd_archive_mv(base_dir, str(ns.path))
    if ns.command == "rm":
        return cmd_rm(str(ns.path), bool(ns.force_outside_base))
    if ns.command == "fix":
        return cmd_fix(str(ns.path))
    if ns.command == "archive":
        if ns.archive_subcommand == "mv":
            return cmd_archive_mv(base_dir, str(ns.path))
        if ns.archive_subcommand == "ls":
            return cmd_archive_ls(base_dir, str(ns.path))
        if ns.archive_subcommand == "undo":
            return cmd_archive_undo(base_dir, str(ns.path))
        if ns.archive_subcommand == "restore":
            return cmd_archive_restore_entry(base_dir, str(ns.archived_path))
        if ns.archive_subcommand == "reorganize":
            return cmd_archive_reorganize(base_dir, bool(ns.dry_run))
        return 1
    if ns.command == "tmux":
        if ns.tmux_subcommand == "load":
            return cmd_tmux_load(str(ns.dir))
        if ns.tmux_subcommand == "save":
            return cmd_tmux_save(
                base_dir,
                str(ns.dir),
                str(ns.output),
                bool(ns.stdout),
                bool(ns.debug),
                str(ns.pane_id),
                str(ns.session_id),
            )
        return 1
    if ns.command == "benchmark":
        if ns.benchmark_subcommand == "run":
            return cmd_benchmark(
                base_dir,
                cwd,
                "run",
                str(ns.comment),
                bool(ns.keep_basefolder),
                None,
            )
        if ns.benchmark_subcommand == "results":
            return cmd_benchmark(
                base_dir,
                cwd,
                "results",
                "",
                False,
                parse_ignore_featureset_values([str(x) for x in ns.ignore_featureset]),
            )
        return 1
    if ns.command == "test":
        if ns.test_subcommand == "regression":
            return cmd_test_regression(
                base_dir,
                cwd,
                bool(ns.list),
                [str(x) for x in ns.case],
            )
        return cmd_test(base_dir, cwd, str(ns.comment), bool(ns.keep_basefolder))
    return 1
