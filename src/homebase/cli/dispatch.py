from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from ..core.logging import logger
from .parser import parse_ignore_featureset_values


def dispatch_command(
    ns: Any,
    *,
    parser: argparse.ArgumentParser,
    base_dir: Path,
    bin_dir: Path,
    cwd: Path,
    no_arg_flow: Callable[[Path, Path, str], int],
    cmd_ls: Callable[..., int],
    cmd_new: Callable[[Any, Path, Path], int],
    cmd_completion: Callable[[str], int],
    cmd_internal_complete: Callable[[str, int, list[str]], int],
    cmd_recent: Callable[[Path], int],
    cmd_help_actions: Callable[[str, str, str, bool], int],
    cmd_setup: Callable[..., int],
    cmd_cache_warm: Callable[[], int],
    cmd_tags_sync: Callable[[Path, bool, bool], int],
    cmd_hooks_refresh: Callable[..., int],
    cmd_utils: Callable[[Path, str], int],
    cmd_archive_mv: Callable[..., int],
    cmd_cd: Callable[[Path, str], int],
    cmd_rm: Callable[..., int],
    cmd_fix: Callable[..., int],
    cmd_archive_ls: Callable[[Path, str], int],
    cmd_archive_undo: Callable[[Path, str], int],
    cmd_archive_restore_entry: Callable[[Path, str], int],
    cmd_tmux_load: Callable[[str], int],
    cmd_tmux_save: Callable[..., int],
    cmd_benchmark: Callable[[Path, Path, str, str, bool, set[str] | None], int],
    cmd_test_regression: Callable[[Path, Path, bool, list[str]], int],
    cmd_test: Callable[[Path, Path, str, bool], int],
    initial_filter_expr: str,
) -> int:
    logger.debug("dispatch command={} cwd={} base={}", ns.command, cwd, base_dir)
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
    if ns.command == "ls":
        filter_parts = list(getattr(ns, "filter", []) or [])
        return cmd_ls(
            base_dir,
            filter_expr=" ".join(filter_parts),
            long_format=bool(getattr(ns, "long", False)),
            with_git=bool(getattr(ns, "git", False)),
            show_archived=bool(getattr(ns, "archived", False)),
        )
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
        return cmd_setup(
            base_dir,
            bin_dir,
            bool(getattr(ns, "dry_run", False)),
            json_output=bool(getattr(ns, "json_output", False)),
        )
    if ns.command == "cache":
        return cmd_cache_warm() if ns.cache_subcommand == "warm" else 1
    if ns.command == "tags":
        if ns.tags_subcommand == "sync-_tags":
            return cmd_tags_sync(base_dir, True, bool(ns.debug))
        return 1
    if ns.command == "hooks":
        if ns.hooks_subcommand == "refresh":
            return cmd_hooks_refresh(
                base_dir,
                project_filters=list(getattr(ns, "projects", []) or []),
                tag_filters=list(getattr(ns, "tags", []) or []),
                filter_expr=str(getattr(ns, "filter_expr", "") or ""),
                hook_filter=list(getattr(ns, "hook_filter", []) or []),
                event_filter=list(getattr(ns, "event_filter", []) or []),
                select_all=bool(getattr(ns, "all_projects", False)),
                show_archived=bool(getattr(ns, "archived", False)),
                dry_run=bool(getattr(ns, "dry_run", False)),
            )
        return 1
    if ns.command == "utils":
        return cmd_utils(base_dir, str(ns.utils_subcommand))
    if ns.command == "a":
        paths = list(getattr(ns, "paths", []) or [])
        if not paths:
            paths = ["."]
        return cmd_archive_mv(
            base_dir,
            paths,
            yes=bool(getattr(ns, "yes", False)),
        )
    if ns.command == "cd":
        return cmd_cd(base_dir, str(getattr(ns, "name", "") or ""))
    if ns.command == "rm":
        return cmd_rm(
            str(ns.path),
            bool(ns.force_outside_base),
            force=bool(getattr(ns, "force", False)),
        )
    if ns.command == "fix":
        import sys

        from ..commands.workspace import FIX_KINDS

        slug_to_attr = {kind: kind.replace("-", "_") for kind in FIX_KINDS}
        include_flags = {
            kind for kind, attr in slug_to_attr.items()
            if bool(getattr(ns, f"enable_{attr}", False))
        }
        exclude_flags = {
            kind for kind, attr in slug_to_attr.items()
            if bool(getattr(ns, f"disable_{attr}", False))
        }
        conflict = include_flags & exclude_flags
        if conflict:
            names = ", ".join(sorted(conflict))
            print(
                f"fix: cannot combine --{names} with --no-{names}",
                file=sys.stderr,
            )
            return 2
        selected = include_flags if include_flags else (set(FIX_KINDS) - exclude_flags)
        paths = list(getattr(ns, "paths", []) or [])
        return cmd_fix(
            paths,
            include=selected,
            yes=bool(getattr(ns, "yes", False)),
            all_targets=bool(getattr(ns, "all_targets", False)),
        )
    if ns.command == "archive":
        sub = getattr(ns, "archive_subcommand", None)
        # Bare ``b archive`` archives cwd, matching ``b a``.
        if sub is None or sub == "mv":
            paths = list(getattr(ns, "paths", []) or [])
            if not paths:
                paths = ["."]
            return cmd_archive_mv(
                base_dir,
                paths,
                yes=bool(getattr(ns, "yes", False)),
            )
        if sub == "ls":
            return cmd_archive_ls(base_dir, str(ns.path))
        if sub == "undo":
            return cmd_archive_undo(base_dir, str(ns.path))
        if sub == "restore":
            return cmd_archive_restore_entry(base_dir, str(ns.archived_path))
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
                pause=bool(getattr(ns, "pause", False)),
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
