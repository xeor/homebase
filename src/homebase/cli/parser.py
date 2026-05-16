from __future__ import annotations

import argparse


def _add_new_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("inputs", nargs="*", default=[])
    mode = p.add_mutually_exclusive_group()
    for key in ("empty", "local", "git", "download", "downloaded"):
        mode.add_argument(f"--{key}", dest="mode", action="store_const", const=key)
    p.add_argument("--as", dest="child_key", default=None)
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--template", default="")
    p.add_argument("--tmp", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--timestamp", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--open", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--cd", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--confirm", action=argparse.BooleanOptionalAction, default=None)
    # store_true flags default to None so the option resolver can tell
    # "not set on the CLI" from "explicitly disabled". Config-side
    # truthy values won't be wiped by an absent CLI flag.
    p.add_argument(
        "--ts-name", dest="ts_name", action="store_const", const=True, default=None,
    )
    p.add_argument(
        "--alpha-name",
        dest="alpha_name",
        action="store_const",
        const=True,
        default=None,
    )
    p.add_argument(
        "--ask-name",
        dest="ask_name",
        action="store_const",
        const=True,
        default=None,
    )
    p.add_argument(
        "--ask-source",
        dest="ask_source",
        action="store_const",
        const=True,
        default=None,
    )
    p.add_argument("--post", action="append", default=[])
    p.add_argument("--yes", action="store_const", const=True, default=None)
    p.add_argument(
        "--dry-run", dest="dry_run", action="store_const", const=True, default=None,
    )
    p.add_argument("--archive", action="store_const", const=True, default=None)
    p.add_argument("--multi", action="store_const", const=True, default=None)


def _build_new_parser(sub) -> None:
    p_new = sub.add_parser("new", help="create a new project")
    _add_new_arguments(p_new)
    p_n = sub.add_parser("n", help="alias for `new`")
    _add_new_arguments(p_n)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="b")
    parser.add_argument("--base-folder", dest="base_folder", default=None)
    parser.add_argument("--filter", dest="initial_filter", default="")

    sub = parser.add_subparsers(dest="command")
    p_help = sub.add_parser("help")
    p_help.add_argument("topic", nargs="?", default="")
    p_help.add_argument("--source", choices=["builtin", "config", "overridden"], default="")
    p_help.add_argument("--bound", choices=["bound", "unbound"], default="")
    p_help.add_argument("--view", choices=["active", "archive"], default="")
    p_help.add_argument("--show-defaults", action="store_true")
    # `b ls` — fast cache-backed listing. Replaces `b status`.
    p_ls = sub.add_parser(
        "ls",
        help="list projects (cache-backed; takes the same filter syntax as the TUI)",
    )
    p_ls.add_argument(
        "filter",
        nargs="*",
        default=[],
        help="filter expression (e.g. `tag:work foo`)",
    )
    p_ls.add_argument(
        "-l", "--long",
        action="store_true",
        help="long format with extra columns",
    )
    p_ls.add_argument(
        "--git",
        action="store_true",
        help="re-probe git and include the BRANCH column (slower)",
    )
    p_ls.add_argument(
        "--archived",
        action="store_true",
        help="list archived projects instead of active",
    )
    _build_new_parser(sub)
    p_completion = sub.add_parser("completion")
    p_completion.add_argument("shell", choices=["fish", "zsh", "bash"])
    # `b shell-init <shell>` prints a wrapper function that lets the
    # parent shell `cd` into the new project / removed project's
    # parent / etc. See src/homebase/cli/shell_init.py.
    p_shell_init = sub.add_parser(
        "shell-init",
        help="print shell-integration wrapper (cd handoff via HOMEBASE_CD_FILE)",
    )
    p_shell_init.add_argument("shell", nargs="?", choices=["fish", "zsh", "bash"], default="")
    p_internal_complete = sub.add_parser("__complete")
    p_internal_complete.add_argument("shell", choices=["fish", "zsh", "bash"])
    p_internal_complete.add_argument("cword", type=int)
    # REMAINDER so user words that look like options (e.g. ``--as``,
    # ``--no-tmp``) don't get re-parsed at the parent level. Newer
    # shell wrappers pass an explicit ``--`` separator (harmless and
    # filtered in dispatch); older installs that don't have ``--``
    # still work thanks to REMAINDER swallowing everything.
    p_internal_complete.add_argument("words", nargs=argparse.REMAINDER)
    sub.add_parser("recent")
    p_setup = sub.add_parser("setup")
    p_setup.add_argument("--dry-run", action="store_true")

    p_cache = sub.add_parser("cache")
    cache_sub = p_cache.add_subparsers(dest="cache_subcommand", required=True)
    cache_sub.add_parser("warm")

    p_tags = sub.add_parser("tags")
    tags_sub = p_tags.add_subparsers(dest="tags_subcommand", required=True)
    p_tags_sync = tags_sub.add_parser("sync-_tags")
    p_tags_sync.add_argument("--debug", action="store_true")

    p_hooks = sub.add_parser("hooks", help="hook administration commands")
    hooks_sub = p_hooks.add_subparsers(dest="hooks_subcommand", required=True)
    p_hooks_refresh = hooks_sub.add_parser(
        "refresh",
        help="re-run post-hook refresh logic without firing the underlying event",
    )
    p_hooks_refresh.add_argument("--all", dest="all_projects", action="store_true")
    p_hooks_refresh.add_argument("--project", dest="projects", action="append", default=[])
    p_hooks_refresh.add_argument("--tag", dest="tags", action="append", default=[])
    p_hooks_refresh.add_argument("--filter", dest="filter_expr", default="")
    p_hooks_refresh.add_argument("--hook", dest="hook_filter", action="append", default=[])
    p_hooks_refresh.add_argument("--event", dest="event_filter", action="append", default=[])
    p_hooks_refresh.add_argument("--archived", action="store_true")
    p_hooks_refresh.add_argument("--dry-run", dest="dry_run", action="store_true")

    p_utils = sub.add_parser("utils")
    utils_sub = p_utils.add_subparsers(dest="utils_subcommand", required=True)
    utils_sub.add_parser("opt-in-nested-discovery")

    p_a = sub.add_parser("a")
    p_a.add_argument("path", nargs="?", default=".")

    p_cd = sub.add_parser(
        "cd",
        help="open a shell in a project under base (tab-completes names)",
    )
    p_cd.add_argument("name", nargs="?", default="")

    p_rm = sub.add_parser("rm")
    p_rm.add_argument("path", nargs="?", default=".")
    p_rm.add_argument("--force-outside-base", action="store_true")
    # ``--force`` / ``-f`` skips the y/N confirmation prompt. It does
    # NOT bypass the outside-base safety net — that's still
    # ``--force-outside-base``.
    p_rm.add_argument("--force", "-f", action="store_true")

    p_fix = sub.add_parser("fix")
    p_fix.add_argument("path", nargs="?", default=".")

    # ``b archive`` with no subcommand → archive cwd (same as `b a`).
    # That's why ``archive_subcommand`` is not required.
    p_archive = sub.add_parser("archive")
    archive_sub = p_archive.add_subparsers(dest="archive_subcommand")
    p_archive_mv = archive_sub.add_parser("mv")
    p_archive_mv.add_argument("path", nargs="?", default=".")
    p_archive_ls = archive_sub.add_parser("ls")
    p_archive_ls.add_argument("path", nargs="?", default=".")
    p_archive_undo = archive_sub.add_parser("undo")
    p_archive_undo.add_argument("path", nargs="?", default=".")
    p_archive_restore = archive_sub.add_parser("restore")
    p_archive_restore.add_argument("archived_path")
    p_archive_reorg = archive_sub.add_parser("reorganize")
    p_archive_reorg.add_argument("--dry-run", action="store_true")

    p_tmux = sub.add_parser("tmux")
    tmux_sub = p_tmux.add_subparsers(dest="tmux_subcommand", required=True)
    p_tmux_load = tmux_sub.add_parser("load")
    p_tmux_load.add_argument("dir", nargs="?", default=".")
    p_tmux_save = tmux_sub.add_parser("save")
    p_tmux_save.add_argument("dir", nargs="?", default=".")
    p_tmux_save.add_argument("--output", default="")
    p_tmux_save.add_argument("--stdout", action="store_true")
    p_tmux_save.add_argument("--debug", action="store_true")
    p_tmux_save.add_argument("--pane-id", default="")
    p_tmux_save.add_argument("--session-id", default="")

    p_bench = sub.add_parser("benchmark")
    bench_sub = p_bench.add_subparsers(dest="benchmark_subcommand", required=True)
    p_bench_run = bench_sub.add_parser("run")
    p_bench_run.add_argument("--comment", default="")
    p_bench_run.add_argument("--keep-basefolder", action="store_true")
    p_bench_results = bench_sub.add_parser("results")
    p_bench_results.add_argument("--ignore-featureset", action="append", default=[])

    p_test = sub.add_parser("test")
    p_test.add_argument("--comment", default="")
    p_test.add_argument("--keep-basefolder", action="store_true")
    test_sub = p_test.add_subparsers(dest="test_subcommand")
    p_test_reg = test_sub.add_parser("regression")
    p_test_reg.add_argument("--list", action="store_true")
    p_test_reg.add_argument("--case", action="append", default=[])

    return parser


def parse_ignore_featureset_values(values: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            val = part.strip()
            if val:
                out.add(val)
    return out
