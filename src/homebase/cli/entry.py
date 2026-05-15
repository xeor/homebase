from __future__ import annotations

import os
import sys
from pathlib import Path

from ..commands import interactive_flow
from ..commands.actions import cmd_help_actions as cmd_help_actions_render
from ..commands.archive import (
    cmd_archive_ls,
    cmd_archive_mv,
    cmd_archive_reorganize,
    cmd_archive_restore_entry,
    cmd_archive_undo,
    cmd_fix,
    cmd_rm,
)
from ..commands.setup import (
    cmd_cache_warm,
    cmd_cd,
    cmd_ls,
    cmd_recent,
    cmd_setup,
    cmd_tags_sync,
    cmd_utils,
)
from ..core import runtime_init
from ..core import utils as core_utils
from ..core.constants import (
    BUILTIN_ACTIONS,
    DEFAULT_ARCHIVE_TZ_NAME,
    ENV_BASE_DIR,
    discover_tab_actions,
)
from ..ui import run_textual_ui as _run_textual_ui
from ..ui.context import UIContext
from ..workspace.projects import run_post_commands
from ..workspace.startup_validation import run_startup_validations
from .completion import completion_candidates, completion_script
from .dispatch import dispatch_command
from .parser import build_cli_parser
from .shell_init import shell_init_script


def resolve_base_dir(base_folder_arg: str | None) -> Path:
    return core_utils.resolve_base_dir(base_folder_arg, os.environ.get("BASE_FOLDER"))


def run_textual_ui(
    base_dir: Path,
    cwd: Path,
    ctx: UIContext | None = None,
    start_new: bool = False,
    initial_filter_expr: str = "",
) -> tuple[str, Path | None, list[str]]:
    return _run_textual_ui(base_dir, cwd, ctx, start_new, initial_filter_expr)


def no_arg_flow(
    base_dir: Path,
    cwd: Path,
    initial_filter_expr: str = "",
    *,
    ctx: UIContext | None = None,
) -> int:
    from ..tmux.flow import open_shell_in_dir, open_with_mode

    return interactive_flow.no_arg_flow(
        base_dir,
        cwd,
        initial_filter_expr=initial_filter_expr,
        cmd_list=cmd_ls,
        run_textual_ui=lambda bd, c, q: run_textual_ui(
            bd,
            c,
            ctx=ctx,
            initial_filter_expr=q,
        ),
        run_post_commands=run_post_commands,
        open_with_mode=open_with_mode,
        cmd_archive_mv=cmd_archive_mv,
        open_shell_in_dir=open_shell_in_dir,
        cmd_archive_restore_entry=cmd_archive_restore_entry,
        cmd_rm=lambda path: cmd_rm(path),
    )


def _resolve_filter_expression(base_dir: Path, expr: str):
    from ..config.prefs import resolve_filter_expression

    return resolve_filter_expression(base_dir, expr)


def main(argv: list[str]) -> int:
    from ..config import prefs as app_prefs  # noqa: F401  (alias for clarity)
    from ..config.hooks import HookConfigError, load_hook_specs
    from ..config.prefs import (
        load_actions,
        load_archive_timezone_name,
        load_cache_profile_table,
        load_file_view_exclude_patterns,
        load_hotbar,
        load_keys,
        load_notes_config,
        load_open_mode_config,
        load_reconcile_config,
        load_saved_filter_queries,
        load_suffixes,
        load_wip_symbol_map,
    )
    from ..config.property_defs import load_property_defs
    from ..hooks.loader import verify_all_specs
    from ..tmux.flow import cmd_tmux_load, cmd_tmux_save
    from ..workspace.benchmark import cmd_benchmark, cmd_test
    from ..workspace.new import cmd_new
    from ..workspace.regression import cmd_test_regression

    parser = build_cli_parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    script = Path(__file__).resolve()
    bin_dir = script.parent.parent

    base_dir = resolve_base_dir(ns.base_folder)
    os.environ[ENV_BASE_DIR] = str(base_dir)

    # Fast paths that must work even when the global config is broken
    # (otherwise shell completion keeps spamming "config error: ..." on
    # every keystroke that triggers the completion function).
    if ns.command == "completion":
        return _cmd_completion(str(ns.shell))
    if ns.command == "shell-init":
        print(shell_init_script(str(ns.shell)), end="")
        return 0
    if ns.command == "__complete":
        # Strip a leading ``--`` separator that newer shell wrappers
        # use to keep argparse from eating option-shaped user words.
        words = [str(x) for x in ns.words]
        if words and words[0] == "--":
            words = words[1:]
        return _cmd_internal_complete(
            str(ns.shell),
            int(ns.cword),
            words,
            base_dir=base_dir,
        )
    if ns.command == "help" and str(getattr(ns, "topic", "")).strip() != "actions":
        parser.print_help()
        return 0

    startup_issues = run_startup_validations(base_dir)
    if startup_issues:
        print("startup validation failed:", file=sys.stderr)
        for issue in startup_issues:
            if issue.path is not None:
                print(f"- {issue.message}: {issue.path}", file=sys.stderr)
            else:
                print(f"- {issue.message}", file=sys.stderr)
        return 1

    try:
        runtime_builtins = dict(BUILTIN_ACTIONS)
        runtime_builtins.update(discover_tab_actions())
        runtime_cfg = runtime_init.load_runtime_config(
            base_dir,
            default_archive_tz_name=DEFAULT_ARCHIVE_TZ_NAME,
            load_property_defs=load_property_defs,
            load_wip_symbol_map=load_wip_symbol_map,
            load_saved_filter_queries=load_saved_filter_queries,
            load_suffixes=load_suffixes,
            load_file_view_exclude_patterns=load_file_view_exclude_patterns,
            load_actions=lambda bd: load_actions(bd, builtins=runtime_builtins),
            load_hotbar=lambda bd, actions: load_hotbar(bd, actions=actions),
            load_keys=lambda bd, actions: load_keys(bd, actions=actions),
            load_open_mode_config=load_open_mode_config,
            load_notes_config=load_notes_config,
            load_reconcile_config=load_reconcile_config,
            load_cache_profile_table=load_cache_profile_table,
            load_hook_specs=load_hook_specs,
            load_archive_timezone_name=load_archive_timezone_name,
        )
        verify_all_specs(runtime_cfg.hook_specs, base_dir)
    except HookConfigError as exc:
        print(f"hook config error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    ui_ctx = UIContext(
        base_dir=base_dir,
        archive_tz=runtime_cfg.archive_tz,
        archive_tz_name=runtime_cfg.archive_tz_name,
        property_defs=list(runtime_cfg.property_defs),
        wip_open_symbol_map=dict(runtime_cfg.wip_open_symbol_map),
        named_filters=dict(runtime_cfg.named_filters),
        saved_filter_queries=list(runtime_cfg.saved_filter_queries),
        suffixes=list(runtime_cfg.suffixes),
        file_view_exclude_patterns=list(runtime_cfg.file_view_exclude_patterns),
        actions=dict(runtime_cfg.actions),
        hotbar=[
            {
                "action": str(item.action),
                "label": str(item.label),
                "style": [dict(rule) for rule in item.style],
            }
            for item in runtime_cfg.hotbar
        ],
        keys={
            str(key): {"action": str(entry.action), "label": str(entry.label)}
            for key, entry in runtime_cfg.keys.items()
        },
        open_mode_config=dict(runtime_cfg.open_mode_config),
        notes_config=dict(runtime_cfg.notes_config),
        reconcile_config={
            mode: dict(conf) for mode, conf in runtime_cfg.reconcile_config.items()
        },
        cache_profile_table={
            scope: {name: dict(profile) for name, profile in table.items()}
            for scope, table in runtime_cfg.cache_profile_table.items()
        },
        hook_specs=dict(runtime_cfg.hook_specs),
    )

    initial_filter_expr = runtime_init.resolve_initial_filter_expression(
        str(ns.initial_filter or ""),
        resolve_filter_expression=lambda expr: _resolve_filter_expression(base_dir, expr),
    )

    try:
        rc = dispatch_command(
            ns,
            parser=parser,
            base_dir=base_dir,
            bin_dir=bin_dir,
            cwd=Path.cwd().resolve(),
            no_arg_flow=lambda bd, cwd_path, initial: no_arg_flow(
                bd,
                cwd_path,
                initial_filter_expr=initial,
                ctx=ui_ctx,
            ),
            cmd_ls=lambda bd, filter_expr="", long_format=False, with_git=False, show_archived=False: cmd_ls(
                bd,
                filter_expr=filter_expr,
                long_format=long_format,
                with_git=with_git,
                show_archived=show_archived,
            ),
            cmd_new=cmd_new,
            cmd_completion=lambda shell: _cmd_completion(shell),
            cmd_internal_complete=lambda shell, cword, words: _cmd_internal_complete(
                shell,
                cword,
                words,
                base_dir=base_dir,
            ),
            cmd_recent=cmd_recent,
            cmd_help_actions=lambda source, bound, view, show_defaults: cmd_help_actions_render(
                actions=runtime_cfg.actions,
                hotbar=list(runtime_cfg.hotbar),
                keys=dict(runtime_cfg.keys),
                source_filter=source,
                bound_filter=bound,
                view_filter=view,
                show_defaults=show_defaults,
            ),
            cmd_setup=lambda base_path, bin_path, dry_run: cmd_setup(
                base_path,
                bin_path,
                completion_script_fn=completion_script,
                shell_init_script_fn=shell_init_script,
                dry_run=dry_run,
            ),
            cmd_cache_warm=cmd_cache_warm,
            cmd_tags_sync=lambda bd, verbose, debug: cmd_tags_sync(
                bd,
                verbose=verbose,
                debug=debug,
            ),
            cmd_utils=cmd_utils,
            cmd_archive_mv=cmd_archive_mv,
            cmd_cd=cmd_cd,
            cmd_rm=lambda path, force_outside_base, force=False: cmd_rm(
                path,
                force_outside_base=force_outside_base,
                force=force,
            ),
            cmd_fix=cmd_fix,
            cmd_archive_ls=cmd_archive_ls,
            cmd_archive_undo=cmd_archive_undo,
            cmd_archive_restore_entry=cmd_archive_restore_entry,
            cmd_archive_reorganize=cmd_archive_reorganize,
            cmd_tmux_load=cmd_tmux_load,
            cmd_tmux_save=lambda bd, dir_path, output, to_stdout, debug, pane_id, session_id: cmd_tmux_save(
                bd,
                dir_path,
                output=output,
                to_stdout=to_stdout,
                debug=debug,
                pane_id_hint=pane_id,
                session_id_hint=session_id,
            ),
            cmd_benchmark=lambda bd, cwd_path, action, comment, keep_basefolder, ignore: cmd_benchmark(
                bd,
                cwd_path,
                action,
                comment=comment,
                keep_basefolder=keep_basefolder,
                ignore_featuresets=(ignore or set()),
            ),
            cmd_test_regression=lambda bd, cwd_path, list_only, selected: cmd_test_regression(
                bd,
                cwd_path,
                list_only=list_only,
                selected=selected,
            ),
            cmd_test=lambda bd, cwd_path, comment, keep_basefolder: cmd_test(
                bd,
                cwd_path,
                comment=comment,
                keep_basefolder=keep_basefolder,
            ),
            initial_filter_expr=initial_filter_expr,
        )
    except KeyboardInterrupt:
        print()
        return 130

    if rc == 1 and ns.command not in {
        None,
        "cache",
        "tags",
        "archive",
        "tmux",
        "benchmark",
        "test",
        "help",
        "status",
        "new",
        "n",
        "recent",
        "setup",
        "utils",
        "a",
        "rm",
        "fix",
    }:
        print("unknown command", file=sys.stderr)
    return rc


def _cmd_completion(shell: str) -> int:
    print(completion_script(shell), end="")
    return 0


def _cmd_internal_complete(shell: str, cword: int, words: list[str], *, base_dir: Path) -> int:
    _ = shell
    for value in completion_candidates(words, cword, base_dir=base_dir):
        print(value)
    return 0
