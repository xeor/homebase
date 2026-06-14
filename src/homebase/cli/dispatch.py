from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..core.logging import logger
from .parser import parse_ignore_featureset_values


def _dispatch_ls(ns: Any, base_dir: Path, cmd_ls: Callable[..., int]) -> int:
    filter_parts = list(getattr(ns, "filter", []) or [])
    return cmd_ls(
        base_dir,
        filter_expr=" ".join(filter_parts),
        long_format=bool(getattr(ns, "long", False)),
        with_git=bool(getattr(ns, "git", False)),
        show_archived=bool(getattr(ns, "archived", False)),
        with_created=bool(getattr(ns, "created", False)),
        with_active=bool(getattr(ns, "active", False)),
        with_wip=bool(getattr(ns, "wip", False)),
        with_worktree_of=bool(getattr(ns, "worktree_of", False)),
        with_src=bool(getattr(ns, "src", False)),
        with_path=bool(getattr(ns, "path", False)),
        with_description=bool(getattr(ns, "description", False)),
        with_props=bool(getattr(ns, "props", False)),
    )


def _dispatch_json(ns: Any, base_dir: Path, cmd_json: Callable[..., int]) -> int:
    filter_parts = list(getattr(ns, "filter", []) or [])
    return cmd_json(
        base_dir,
        filter_expr=" ".join(filter_parts),
        include_archived=bool(getattr(ns, "archived", False)),
        archived_only=bool(getattr(ns, "archived_only", False)),
    )


def _dispatch_internal_complete(
    ns: Any, cmd_internal_complete: Callable[[str, int, list[str]], int]
) -> int:
    return cmd_internal_complete(
        str(ns.shell),
        int(ns.cword),
        [str(x) for x in ns.words],
    )


def _dispatch_setup(ns: Any, base_dir: Path, bin_dir: Path, cmd_setup: Callable[..., int]) -> int:
    return cmd_setup(
        base_dir,
        bin_dir,
        bool(getattr(ns, "dry_run", False)),
        json_output=bool(getattr(ns, "json_output", False)),
    )


def _dispatch_cache(ns: Any, cmd_cache_warm: Callable[[], int]) -> int:
    if ns.cache_subcommand == "warm":
        return cmd_cache_warm()
    return 1


def _dispatch_tags(
    ns: Any,
    base_dir: Path,
    cmd_tags_sync: Callable[[Path, bool, bool], int],
    cmd_tags_ls: Callable[[Path], int],
) -> int:
    if ns.tags_subcommand == "sync-_tags":
        return cmd_tags_sync(base_dir, True, bool(ns.debug))
    if ns.tags_subcommand == "ls":
        return cmd_tags_ls(base_dir)
    return 1


def _dispatch_hooks(
    ns: Any, base_dir: Path, cmd_hooks_refresh: Callable[..., int]
) -> int:
    if ns.hooks_subcommand != "refresh":
        return 1
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


def _dispatch_archive_mv(
    ns: Any, base_dir: Path, cmd_archive_mv: Callable[..., int]
) -> int:
    paths = list(getattr(ns, "paths", []) or [])
    if not paths:
        paths = ["."]
    return cmd_archive_mv(
        base_dir,
        paths,
        yes=bool(getattr(ns, "yes", False)),
    )


def _dispatch_cd(ns: Any, base_dir: Path, cmd_cd: Callable[[Path, str], int]) -> int:
    raw = getattr(ns, "name", []) or []
    args = [raw] if isinstance(raw, str) else list(raw)
    name = str(args[-1]) if args else ""
    return cmd_cd(base_dir, name)


def _dispatch_open(ns: Any, base_dir: Path, cmd_open: Callable[[Path, str], int]) -> int:
    raw = getattr(ns, "name", []) or []
    args = [raw] if isinstance(raw, str) else list(raw)
    name = str(args[-1]) if args else ""
    return cmd_open(base_dir, name)


def _dispatch_rm(ns: Any, cmd_rm: Callable[..., int]) -> int:
    return cmd_rm(
        str(ns.path),
        bool(ns.force_outside_base),
        force=bool(getattr(ns, "force", False)),
    )


def _resolve_fix_selection(ns: Any) -> tuple[set[str], int]:
    """Return (selected_kinds, exit_code). exit_code != 0 means error."""
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
        print(f"fix: cannot combine --{names} with --no-{names}", file=sys.stderr)
        return (set(), 2)
    selected = include_flags if include_flags else (set(FIX_KINDS) - exclude_flags)
    return (selected, 0)


def _dispatch_fix(ns: Any, cmd_fix: Callable[..., int]) -> int:
    selected, err = _resolve_fix_selection(ns)
    if err:
        return err
    paths = list(getattr(ns, "paths", []) or [])
    return cmd_fix(
        paths,
        include=selected,
        yes=bool(getattr(ns, "yes", False)),
        all_targets=bool(getattr(ns, "all_targets", False)),
    )


def _dispatch_archive(
    ns: Any,
    base_dir: Path,
    cmd_archive_mv: Callable[..., int],
    cmd_archive_ls: Callable[[Path, str], int],
    cmd_archive_undo: Callable[[Path, str], int],
    cmd_archive_restore_entry: Callable[[Path, str], int],
) -> int:
    sub = getattr(ns, "archive_subcommand", None)
    # Bare ``b archive`` archives cwd, matching ``b a``.
    if sub is None or sub == "mv":
        return _dispatch_archive_mv(ns, base_dir, cmd_archive_mv)
    if sub == "ls":
        return cmd_archive_ls(base_dir, str(ns.path))
    if sub == "undo":
        return cmd_archive_undo(base_dir, str(ns.path))
    if sub == "restore":
        return cmd_archive_restore_entry(base_dir, str(ns.archived_path))
    return 1


def _dispatch_tmux(
    ns: Any,
    base_dir: Path,
    cmd_tmux_load: Callable[[str], int],
    cmd_tmux_save: Callable[..., int],
) -> int:
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


def _dispatch_benchmark(
    ns: Any,
    base_dir: Path,
    cwd: Path,
    cmd_benchmark: Callable[[Path, Path, str, str, bool, set[str] | None], int],
) -> int:
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


def _dispatch_test(
    ns: Any,
    base_dir: Path,
    cwd: Path,
    cmd_test_regression: Callable[[Path, Path, bool, list[str]], int],
    cmd_test: Callable[[Path, Path, str, bool], int],
) -> int:
    if ns.test_subcommand == "regression":
        return cmd_test_regression(
            base_dir,
            cwd,
            bool(ns.list),
            [str(x) for x in ns.case],
        )
    return cmd_test(base_dir, cwd, str(ns.comment), bool(ns.keep_basefolder))


def _dispatch_example(
    ns: Any, cmd_example_generate: Callable[[str, int, int | None], int]
) -> int:
    if ns.example_subcommand == "generate":
        seed = getattr(ns, "seed", None)
        return cmd_example_generate(
            str(ns.path),
            int(getattr(ns, "count", 30) or 30),
            int(seed) if seed is not None else None,
        )
    return 1


def _build_dispatch_table(
    ns: Any,
    base_dir: Path,
    bin_dir: Path,
    cwd: Path,
    handlers: dict[str, Callable[..., int]],
) -> dict[str, Callable[[], int]]:
    table: dict[str, Callable[[], int]] = {
        "help": lambda: handlers["cmd_help"](ns),
        "ls": lambda: _dispatch_ls(ns, base_dir, handlers["cmd_ls"]),
        "json": lambda: _dispatch_json(ns, base_dir, handlers["cmd_json"]),
        "new": lambda: handlers["cmd_new"](ns, base_dir, cwd),
        "n": lambda: handlers["cmd_new"](ns, base_dir, cwd),
        "completion": lambda: handlers["cmd_completion"](str(ns.shell)),
        "__complete": lambda: _dispatch_internal_complete(ns, handlers["cmd_internal_complete"]),
        "recent": lambda: handlers["cmd_recent"](base_dir),
        "setup": lambda: _dispatch_setup(ns, base_dir, bin_dir, handlers["cmd_setup"]),
        "cache": lambda: _dispatch_cache(ns, handlers["cmd_cache_warm"]),
        "tags": lambda: _dispatch_tags(
            ns, base_dir, handlers["cmd_tags_sync"], handlers["cmd_tags_ls"]
        ),
        "hooks": lambda: _dispatch_hooks(ns, base_dir, handlers["cmd_hooks_refresh"]),
        "utils": lambda: handlers["cmd_utils"](base_dir, str(ns.utils_subcommand)),
        "a": lambda: _dispatch_archive_mv(ns, base_dir, handlers["cmd_archive_mv"]),
        "cd": lambda: _dispatch_cd(ns, base_dir, handlers["cmd_cd"]),
        "open": lambda: _dispatch_open(ns, base_dir, handlers["cmd_open"]),
        "rm": lambda: _dispatch_rm(ns, handlers["cmd_rm"]),
        "deworktree": lambda: handlers["cmd_deworktree"](
            base_dir, str(getattr(ns, "path", ".") or ".")
        ),
        "fix-worktrees": lambda: handlers["cmd_fix_worktrees"](
            base_dir, apply=bool(getattr(ns, "apply", False))
        ),
        "fix": lambda: _dispatch_fix(ns, handlers["cmd_fix"]),
        "archive": lambda: _dispatch_archive(
            ns,
            base_dir,
            handlers["cmd_archive_mv"],
            handlers["cmd_archive_ls"],
            handlers["cmd_archive_undo"],
            handlers["cmd_archive_restore_entry"],
        ),
        "tmux": lambda: _dispatch_tmux(
            ns, base_dir, handlers["cmd_tmux_load"], handlers["cmd_tmux_save"]
        ),
        "benchmark": lambda: _dispatch_benchmark(
            ns, base_dir, cwd, handlers["cmd_benchmark"]
        ),
        "test": lambda: _dispatch_test(
            ns, base_dir, cwd, handlers["cmd_test_regression"], handlers["cmd_test"]
        ),
        "example": lambda: _dispatch_example(ns, handlers["cmd_example_generate"]),
    }
    return table


def dispatch_command(
    ns: Any,
    *,
    base_dir: Path,
    bin_dir: Path,
    cwd: Path,
    no_arg_flow: Callable[[Path, Path, str], int],
    cmd_ls: Callable[..., int],
    cmd_json: Callable[..., int],
    cmd_new: Callable[[Any, Path, Path], int],
    cmd_completion: Callable[[str], int],
    cmd_internal_complete: Callable[[str, int, list[str]], int],
    cmd_recent: Callable[[Path], int],
    cmd_help: Callable[[Any], int],
    cmd_setup: Callable[..., int],
    cmd_cache_warm: Callable[[], int],
    cmd_tags_sync: Callable[[Path, bool, bool], int],
    cmd_tags_ls: Callable[[Path], int],
    cmd_hooks_refresh: Callable[..., int],
    cmd_utils: Callable[[Path, str], int],
    cmd_archive_mv: Callable[..., int],
    cmd_cd: Callable[[Path, str], int],
    cmd_open: Callable[[Path, str], int],
    cmd_rm: Callable[..., int],
    cmd_fix: Callable[..., int],
    cmd_deworktree: Callable[[Path, str], int],
    cmd_fix_worktrees: Callable[..., int],
    cmd_archive_ls: Callable[[Path, str], int],
    cmd_archive_undo: Callable[[Path, str], int],
    cmd_archive_restore_entry: Callable[[Path, str], int],
    cmd_tmux_load: Callable[[str], int],
    cmd_tmux_save: Callable[..., int],
    cmd_benchmark: Callable[[Path, Path, str, str, bool, set[str] | None], int],
    cmd_test_regression: Callable[[Path, Path, bool, list[str]], int],
    cmd_test: Callable[[Path, Path, str, bool], int],
    cmd_example_generate: Callable[[str, int, int | None], int],
    initial_filter_expr: str,
) -> int:
    logger.debug("dispatch command={} cwd={} base={}", ns.command, cwd, base_dir)
    if ns.command is None:
        return no_arg_flow(base_dir, cwd, initial_filter_expr)
    handlers: dict[str, Callable[..., int]] = {
        "cmd_ls": cmd_ls,
        "cmd_json": cmd_json,
        "cmd_new": cmd_new,
        "cmd_completion": cmd_completion,
        "cmd_internal_complete": cmd_internal_complete,
        "cmd_recent": cmd_recent,
        "cmd_help": cmd_help,
        "cmd_setup": cmd_setup,
        "cmd_cache_warm": cmd_cache_warm,
        "cmd_tags_sync": cmd_tags_sync,
        "cmd_tags_ls": cmd_tags_ls,
        "cmd_hooks_refresh": cmd_hooks_refresh,
        "cmd_utils": cmd_utils,
        "cmd_archive_mv": cmd_archive_mv,
        "cmd_cd": cmd_cd,
        "cmd_open": cmd_open,
        "cmd_rm": cmd_rm,
        "cmd_fix": cmd_fix,
        "cmd_deworktree": cmd_deworktree,
        "cmd_fix_worktrees": cmd_fix_worktrees,
        "cmd_archive_ls": cmd_archive_ls,
        "cmd_archive_undo": cmd_archive_undo,
        "cmd_archive_restore_entry": cmd_archive_restore_entry,
        "cmd_tmux_load": cmd_tmux_load,
        "cmd_tmux_save": cmd_tmux_save,
        "cmd_benchmark": cmd_benchmark,
        "cmd_test_regression": cmd_test_regression,
        "cmd_test": cmd_test,
        "cmd_example_generate": cmd_example_generate,
    }
    table = _build_dispatch_table(ns, base_dir, bin_dir, cwd, handlers)
    handler = table.get(ns.command)
    if handler is None:
        return 1
    return handler()
