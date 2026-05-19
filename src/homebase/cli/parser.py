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
    p_new = sub.add_parser(
        "new",
        help="create a project from name/path/url",
        description=(
            "Create a new project under base. Input can be a bare name, local path,\n"
            "or remote URL. Source is auto-detected unless you force one with flags."
        ),
    )
    _add_new_arguments(p_new)
    p_n = sub.add_parser("n", help="alias for `new`")
    _add_new_arguments(p_n)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="b")
    parser.add_argument("--base-folder", dest="base_folder", default=None)
    parser.add_argument("--filter", dest="initial_filter", default="")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity (-v, -vv, -vvv)",
    )

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
    p_completion = sub.add_parser(
        "completion",
        help="print completion script for shell",
    )
    p_completion.add_argument("shell", choices=["fish", "zsh", "bash"], help="target shell")
    # `b shell-init <shell>` prints a wrapper function that lets the
    # parent shell `cd` into the new project / removed project's
    # parent / etc. See src/homebase/cli/shell_init.py.
    p_shell_init = sub.add_parser(
        "shell-init",
        help="print shell-integration wrapper (cd handoff via HOMEBASE_CD_FILE)",
    )
    p_shell_init.add_argument("shell", nargs="?", choices=["fish", "zsh", "bash"], default="", help="shell name (omit for usage help)")
    p_internal_complete = sub.add_parser("__complete", help=argparse.SUPPRESS)
    p_internal_complete.add_argument("shell", choices=["fish", "zsh", "bash"], help=argparse.SUPPRESS)
    p_internal_complete.add_argument("cword", type=int, help=argparse.SUPPRESS)
    # REMAINDER so user words that look like options (e.g. ``--as``,
    # ``--no-tmp``) don't get re-parsed at the parent level. Newer
    # shell wrappers pass an explicit ``--`` separator (harmless and
    # filtered in dispatch); older installs that don't have ``--``
    # still work thanks to REMAINDER swallowing everything.
    p_internal_complete.add_argument("words", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    sub.add_parser("recent", help="list projects sorted by latest commit")
    p_setup = sub.add_parser("setup", help="check and install recommended shell/tool setup")
    p_setup.add_argument("--dry-run", action="store_true", help="print proposed changes without writing")
    p_setup.add_argument("--json", dest="json_output", action="store_true", help="emit machine-readable report")

    p_cache = sub.add_parser("cache", help="cache maintenance commands")
    cache_sub = p_cache.add_subparsers(dest="cache_subcommand", required=True)
    cache_sub.add_parser("warm", help="pre-warm runtime/import cache")

    p_tags = sub.add_parser("tags", help="tag index and listing commands")
    tags_sub = p_tags.add_subparsers(dest="tags_subcommand", required=True)
    p_tags_sync = tags_sub.add_parser("sync-_tags", help="rebuild _tags symlink index")
    p_tags_sync.add_argument("--debug", action="store_true", help="print per-project debug output")
    tags_sub.add_parser(
        "ls",
        help="list every known tag in its configured hierarchy",
    )

    p_hooks = sub.add_parser("hooks", help="hook administration commands")
    hooks_sub = p_hooks.add_subparsers(dest="hooks_subcommand", required=True)
    p_hooks_refresh = hooks_sub.add_parser(
        "refresh",
        help="re-run post-hook refresh logic without firing the underlying event",
    )
    p_hooks_refresh.add_argument("--all", dest="all_projects", action="store_true", help="refresh all projects")
    p_hooks_refresh.add_argument("--project", dest="projects", action="append", default=[], help="project path/name filter (repeatable)")
    p_hooks_refresh.add_argument("--tag", dest="tags", action="append", default=[], help="only projects containing tag (repeatable)")
    p_hooks_refresh.add_argument("--filter", dest="filter_expr", default="", help="filter expression")
    p_hooks_refresh.add_argument("--hook", dest="hook_filter", action="append", default=[], help="hook name filter (repeatable)")
    p_hooks_refresh.add_argument("--event", dest="event_filter", action="append", default=[], help="event filter (repeatable)")
    p_hooks_refresh.add_argument("--archived", action="store_true", help="include archived view")
    p_hooks_refresh.add_argument("--dry-run", dest="dry_run", action="store_true", help="show what would run")

    p_utils = sub.add_parser("utils", help="utility and migration helpers")
    utils_sub = p_utils.add_subparsers(dest="utils_subcommand", required=True)
    utils_sub.add_parser("opt-in-nested-discovery", help="enable nested project discovery if safe")

    p_a = sub.add_parser("a", help="archive path (alias for `b archive mv`)")
    p_a.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="target directories (default: cwd)",
    )
    p_a.add_argument(
        "--yes", "-y",
        dest="yes",
        action="store_true",
        help="skip confirmation prompts",
    )

    p_cd = sub.add_parser(
        "cd",
        help="open a shell in a project under base (tab-completes names)",
    )
    p_cd.add_argument("name", nargs="?", default="", help="project name under base")

    p_rm = sub.add_parser("rm", help="delete a directory recursively")
    p_rm.add_argument("path", nargs="?", default=".", help="target path (default: cwd)")
    p_rm.add_argument("--force-outside-base", action="store_true", help="allow deleting outside base root")
    # ``--force`` / ``-f`` skips the y/N confirmation prompt. It does
    # NOT bypass the outside-base safety net — that's still
    # ``--force-outside-base``.
    p_rm.add_argument("--force", "-f", action="store_true", help="skip y/N confirmation")

    p_fix = sub.add_parser(
        "fix",
        help="repair marker/archive entries under base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Inspect one or more directories under base and apply safe repairs.\n"
            "Valid targets: direct base projects (base/<name>) and archive\n"
            "entries (base/_archive/<year>/<entry> or legacy entries directly\n"
            "under _archive). Anything else is ignored.\n"
            "\n"
            "Available fixers (all run by default; each is contextual):\n"
            "  marker         create missing .base.yaml in active projects\n"
            "  archive-entry  for items under _archive, ensure canonical\n"
            "                 YYYY-MM-DD_<name> form and move into the right\n"
            "                 year subdir. Date is detected from the name\n"
            "                 (also accepting space/hyphen/dot separators and\n"
            "                 normalising 00→01 segments), from an embedded\n"
            "                 YYYY-MM-DD, or from the newest file mtime;\n"
            "                 falls back to a prompt (default: today,\n"
            "                 YYYY-MM-DD). Handles dirs and .tgz files.\n"
            "\n"
            "Targeting `_archive` itself fans out to every malformed entry\n"
            "(legacy direct children + non-canonical entries inside year\n"
            "subdirs). Pass `--all` to also sweep direct base projects in\n"
            "the same pass.\n"
            "\n"
            "Selection: pass --<fixer> to run only those, or --no-<fixer>\n"
            "to skip a fixer. The two forms cannot be mixed for the same name."
        ),
    )
    p_fix.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="target directories (default: current directory)",
    )
    p_fix.add_argument(
        "--all",
        dest="all_targets",
        action="store_true",
        help=(
            "sweep the whole workspace: every direct base project plus the "
            "_archive root. Overrides any explicit paths."
        ),
    )
    p_fix.add_argument(
        "--yes", "-y",
        dest="yes",
        action="store_true",
        help="skip all prompts and apply every selected fix",
    )
    p_fix.add_argument(
        "--marker",
        dest="enable_marker",
        action="store_true",
        help="include the marker fixer (only this when no other --<fixer> set)",
    )
    p_fix.add_argument(
        "--no-marker",
        dest="disable_marker",
        action="store_true",
        help="skip the marker fixer",
    )
    p_fix.add_argument(
        "--archive-entry",
        dest="enable_archive_entry",
        action="store_true",
        help="include the archive-entry fixer",
    )
    p_fix.add_argument(
        "--no-archive-entry",
        dest="disable_archive_entry",
        action="store_true",
        help="skip the archive-entry fixer",
    )

    # ``b archive`` with no subcommand → archive cwd (same as `b a`).
    # That's why ``archive_subcommand`` is not required.
    p_archive = sub.add_parser(
        "archive",
        help="archive and restore operations",
        description=(
            "Archive directories under base into _archive/<year>/. The "
            "archive date is auto-detected: .git HEAD commit date if "
            "present, otherwise a date found in the folder name (full "
            "date or year), otherwise the newest regular-file mtime. "
            "If nothing is detected, falls back to today (prompts for "
            "confirmation in interactive mode)."
        ),
    )
    p_archive.add_argument(
        "--yes", "-y",
        dest="yes",
        action="store_true",
        help="skip confirmation prompts",
    )
    archive_sub = p_archive.add_subparsers(dest="archive_subcommand")
    p_archive_mv = archive_sub.add_parser(
        "mv", help="archive one or more directories (same as bare `b archive`)",
    )
    p_archive_mv.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="target directories (default: cwd)",
    )
    p_archive_mv.add_argument(
        "--yes", "-y",
        dest="yes",
        action="store_true",
        help="skip confirmation prompts",
    )
    p_archive_ls = archive_sub.add_parser("ls", help="list archive matches for path")
    p_archive_ls.add_argument("path", nargs="?", default=".", help="path/name to match")
    p_archive_undo = archive_sub.add_parser("undo", help="restore most recent archive entry for path")
    p_archive_undo.add_argument("path", nargs="?", default=".", help="path/name to restore")
    p_archive_restore = archive_sub.add_parser("restore", help="restore exact archived path")
    p_archive_restore.add_argument("archived_path", help="full archived entry path")

    p_tmux = sub.add_parser("tmux", help="tmux integration commands")
    tmux_sub = p_tmux.add_subparsers(dest="tmux_subcommand", required=True)
    p_tmux_load = tmux_sub.add_parser("load", help="load .tmuxp.yaml for a project")
    p_tmux_load.add_argument("dir", nargs="?", default=".", help="project directory (default: cwd)")
    p_tmux_save = tmux_sub.add_parser("save", help="save current tmux window as .tmuxp.yaml")
    p_tmux_save.add_argument("dir", nargs="?", default=".", help="project directory (default: cwd)")
    p_tmux_save.add_argument("--output", default="", help="write profile to explicit file path")
    p_tmux_save.add_argument("--stdout", action="store_true", help="print profile to stdout")
    p_tmux_save.add_argument("--debug", action="store_true", help="include debug diagnostics")
    p_tmux_save.add_argument("--pane-id", default="", help="tmux pane id hint")
    p_tmux_save.add_argument("--session-id", default="", help="tmux session id hint")
    p_tmux_save.add_argument(
        "--pause",
        action="store_true",
        help="print progress and wait for Enter at the end (useful from tmux display-popup)",
    )

    p_bench = sub.add_parser("benchmark", help="performance benchmark commands")
    bench_sub = p_bench.add_subparsers(dest="benchmark_subcommand", required=True)
    p_bench_run = bench_sub.add_parser("run", help="run benchmark suite and store result")
    p_bench_run.add_argument("--comment", default="", help="optional run annotation")
    p_bench_run.add_argument("--keep-basefolder", action="store_true", help="reuse existing base fixture")
    p_bench_results = bench_sub.add_parser("results", help="show benchmark history")
    p_bench_results.add_argument("--ignore-featureset", action="append", default=[], help="ignore feature set id(s); repeat or comma-separate")

    p_test = sub.add_parser("test", help="run test/regression harness")
    p_test.add_argument("--comment", default="", help="optional run annotation")
    p_test.add_argument("--keep-basefolder", action="store_true", help="reuse existing base fixture")
    test_sub = p_test.add_subparsers(dest="test_subcommand")
    p_test_reg = test_sub.add_parser("regression", help="run regression cases")
    p_test_reg.add_argument("--list", action="store_true", help="list available regression cases")
    p_test_reg.add_argument("--case", action="append", default=[], help="run only named case (repeatable)")

    return parser


def parse_ignore_featureset_values(values: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            val = part.strip()
            if val:
                out.add(val)
    return out
