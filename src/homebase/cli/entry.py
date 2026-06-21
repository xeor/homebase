from __future__ import annotations

import os
import sys
from pathlib import Path

from ..cache.api import cache_load_rows
from ..commands import interactive_flow
from ..commands import raycast as raycast_cmd
from ..commands.archive import (
    archive_pack_internal,
    archive_restore_internal,
    archive_unpack_internal,
    cmd_archive_ls,
    cmd_archive_mv,
    cmd_archive_restore_entry,
    cmd_archive_undo,
    cmd_fix,
    cmd_rm,
)
from ..commands.deworktree import cmd_deworktree
from ..commands.example import cmd_example_generate
from ..commands.fix_worktrees import cmd_fix_worktrees
from ..commands.help import (
    cmd_help as cmd_help_dispatch,
)
from ..commands.help import (
    cmd_help_actions as cmd_help_actions_render,
)
from ..commands.help import (
    cmd_help_hotkeys as cmd_help_hotkeys_render,
)
from ..commands.hooks_cmd import cmd_hooks_refresh
from ..commands.setup import (
    cmd_cache_warm,
    cmd_cd,
    cmd_json,
    cmd_ls,
    cmd_open,
    cmd_recent,
    cmd_setup,
    cmd_tags_ls,
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
from ..core.logging import configure_logging, logger
from ..ui import run_textual_ui as _run_textual_ui
from ..ui.context import UIContext
from ..workspace.projects import run_post_commands
from ..workspace.startup_validation import run_startup_validations
from .completion import completion_candidates, completion_script
from .dispatch import dispatch_command
from .parser import build_cli_parser
from .shell_init import shell_init_help_text, shell_init_script


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


def _parse_args(argv: list[str], parser):
    try:
        return parser.parse_args(argv), 0
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return None, 0
        if isinstance(code, int):
            return None, code
        return None, 1


def _handle_fast_path_commands(ns, base_dir: Path, parser) -> int | None:
    """Return an exit code if the command should bypass config loading; else None."""
    if ns.command == "completion":
        return _cmd_completion(str(ns.shell))
    if ns.command == "shell-init":
        shell_name = str(getattr(ns, "shell", "") or "").strip()
        if not shell_name:
            print(shell_init_help_text())
            return 0
        print(shell_init_script(shell_name), end="")
        return 0
    if ns.command == "__complete":
        words = [str(x) for x in ns.words]
        if words and words[0] == "--":
            words = words[1:]
        return _cmd_internal_complete(
            str(ns.shell), int(ns.cword), words, base_dir=base_dir
        )
    if ns.command == "help":
        from ..commands.help import TOPICS, list_topics

        topic = str(getattr(ns, "topic", "")).strip().lower()
        if not topic:
            parser.print_help()
            return 0
        if topic == "topics":
            return list_topics()
        if topic not in TOPICS:
            parser.print_help()
            print()
            print(f"unknown help topic: {topic!r}", file=sys.stderr)
            list_topics()
            return 2
    return None


def _print_validation_issues(issues, header: str) -> None:
    print(header, file=sys.stderr)
    for issue in issues:
        if issue.path is not None:
            print(f"- {issue.message}: {issue.path}", file=sys.stderr)
        else:
            print(f"- {issue.message}", file=sys.stderr)


def _handle_startup_validation(ns, base_dir: Path) -> int | None:
    """Return an exit code if startup validation requires aborting; else None."""
    skip_validation = ns.command == "fix"
    issues = run_startup_validations(base_dir)
    if not issues:
        return None
    if skip_validation:
        _print_validation_issues(issues, "startup validation warnings:")
        return None
    _print_validation_issues(issues, "startup validation failed:")
    print("Run `b fix --all` to attempt repairs.", file=sys.stderr)
    return 1


def _config_error_help_response(ns, parser, prefix: str, exc: BaseException) -> int:
    print(f"warning: {prefix}: {exc}", file=sys.stderr)
    return cmd_help_dispatch(
        str(getattr(ns, "topic", "")).strip().lower(),
        print_default_help=parser.print_help,
        handlers={
            "actions": lambda: cmd_help_actions_render(
                actions={}, favorites=[],
            ),
            "hotkeys": lambda: cmd_help_hotkeys_render(favorites=[]),
        },
    )


def _cmd_raycast(
    base_dir: Path,
    subcommand: str,
    project: str,
    action_id: str,
    *,
    runtime_cfg,
    compile_filter_expr,
) -> int:
    if subcommand == "actions":
        return raycast_cmd.cmd_actions(
            base_dir,
            project,
            actions=runtime_cfg.actions,
            load_rows=cache_load_rows,
            notes_config=runtime_cfg.notes_config,
        )
    if subcommand == "projects":
        return raycast_cmd.cmd_projects(
            base_dir,
            project,
            actions=runtime_cfg.actions,
            load_rows=cache_load_rows,
            notes_config=runtime_cfg.notes_config,
            raycast_config=runtime_cfg.raycast_config,
            compile_filter_expr=compile_filter_expr,
        )
    return raycast_cmd.cmd_run(
        base_dir,
        project,
        action_id,
        actions=runtime_cfg.actions,
        load_rows=cache_load_rows,
        notes_config=runtime_cfg.notes_config,
        open_project=cmd_open,
    )


def main(argv: list[str]) -> int:
    from ..config import prefs as app_prefs  # noqa: F401  (alias for clarity)
    from ..config.hooks import HookConfigError, load_hook_refresh_config, load_hook_specs
    from ..config.prefs import (
        load_actions,
        load_archive_timezone_name,
        load_cache_profile_table,
        load_favorites,
        load_file_view_exclude_patterns,
        load_notes_config,
        load_open_mode_config,
        load_raycast_config,
        load_reconcile_config,
        load_saved_filter_queries,
        load_suffixes,
        load_wip_symbol_map,
    )
    from ..config.property_defs import load_property_defs
    from ..hooks.loader import verify_all_specs
    from ..hooks.runtime import dispatch_post_cli, dispatch_pre_cli
    from ..hooks.snapshot import snapshot_target_from_path
    from ..tmux.flow import cmd_tmux_load, cmd_tmux_save
    from ..workspace.benchmark import cmd_benchmark, cmd_test
    from ..workspace.filter_compile import compile_filter_expr
    from ..workspace.new import cmd_new
    from ..workspace.regression import cmd_test_regression

    parser = build_cli_parser()
    ns, rc = _parse_args(argv, parser)
    if ns is None:
        return rc

    verbosity = configure_logging(int(getattr(ns, "verbose", 0) or 0))
    logger.debug(
        "cli start command={} verbosity={} argv={}",
        getattr(ns, "command", None),
        verbosity,
        argv,
    )

    # The launcher symlink should point at the executable `b` script
    # that the venv installed (next to the running Python), not at the
    # package source directory. Using ``__file__`` here breaks for
    # editable installs because it resolves to the git checkout.
    # ``sys.executable`` is left unresolved so the parent stays inside
    # the venv bin dir (where the ``b`` script is); resolving follows
    # the symlink out to the system Python where no ``b`` exists.
    bin_dir = Path(sys.executable).parent

    base_dir = resolve_base_dir(ns.base_folder)
    os.environ[ENV_BASE_DIR] = str(base_dir)

    fast_rc = _handle_fast_path_commands(ns, base_dir, parser)
    if fast_rc is not None:
        return fast_rc

    validation_rc = _handle_startup_validation(ns, base_dir)
    if validation_rc is not None:
        return validation_rc

    runtime_builtins = dict(BUILTIN_ACTIONS)
    runtime_builtins.update(discover_tab_actions())
    try:
        runtime_cfg = runtime_init.load_runtime_config(
            base_dir,
            default_archive_tz_name=DEFAULT_ARCHIVE_TZ_NAME,
            load_property_defs=load_property_defs,
            load_wip_symbol_map=load_wip_symbol_map,
            load_saved_filter_queries=load_saved_filter_queries,
            load_suffixes=load_suffixes,
            load_file_view_exclude_patterns=load_file_view_exclude_patterns,
            load_actions=lambda bd: load_actions(bd, builtins=runtime_builtins),
            load_favorites=lambda bd, actions: load_favorites(bd, actions=actions),
            load_open_mode_config=load_open_mode_config,
            load_notes_config=load_notes_config,
            load_raycast_config=load_raycast_config,
            load_reconcile_config=load_reconcile_config,
            load_cache_profile_table=load_cache_profile_table,
            load_hook_specs=load_hook_specs,
            load_hook_refresh_config=load_hook_refresh_config,
            load_archive_timezone_name=load_archive_timezone_name,
        )
        verify_all_specs(runtime_cfg.hook_specs, base_dir)
    except HookConfigError as exc:
        # `b help` is read-only diagnostic and must remain usable even
        # when the config is broken — that's often exactly why the user
        # is asking for help.
        if ns.command == "help":
            return _config_error_help_response(ns, parser, "hook config error", exc)
        print(f"hook config error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        if ns.command == "help":
            return _config_error_help_response(ns, parser, "config error", exc)
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
        favorites=[dict(row) for row in runtime_cfg.favorites],
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
        hook_refresh_config=runtime_cfg.hook_refresh_config,
    )

    initial_filter_expr = runtime_init.resolve_initial_filter_expression(
        str(ns.initial_filter or ""),
        resolve_filter_expression=lambda expr: _resolve_filter_expression(base_dir, expr),
    )

    def _post_create_hook(result, plan, raw_input, explicit_name) -> None:
        try:
            target = snapshot_target_from_path(result.target, archived=bool(getattr(plan, "is_archive", False)))
        except OSError:
            return
        dispatch_post_cli(
            base_dir=base_dir,
            hook_specs=runtime_cfg.hook_specs,
            event="new_project",
            targets=[target],
            change={
                "created_path": result.target,
                "source": str(getattr(plan, "source_key", "auto")),
                "template": (str(getattr(plan, "template", "") or "").strip() or None),
                "initial_tags": [str(tag) for tag in getattr(plan, "tags", [])],
                "post_commands": [str(cmd) for cmd in getattr(plan, "post_commands", [])],
                "after_create": "open" if bool(result.open_shell) else "stay",
                "inputs": {
                    "raw_input": raw_input,
                    "explicit_name": explicit_name,
                    "mode": getattr(ns, "mode", None),
                    "child_key": getattr(ns, "child_key", None),
                    "tmp": getattr(ns, "tmp", None),
                    "timestamp": getattr(ns, "timestamp", None),
                    "ts_name": getattr(ns, "ts_name", None),
                    "alpha_name": getattr(ns, "alpha_name", None),
                    "ask_name": getattr(ns, "ask_name", None),
                    "ask_source": getattr(ns, "ask_source", None),
                    "archive": getattr(ns, "archive", None),
                    "multi": getattr(ns, "multi", None),
                },
                "plan": {},
            },
            view="archive" if target.archived else "active",
        )

    def _pre_create_hook(ns_obj, raw_input, explicit_name):
        pre = dispatch_pre_cli(
            base_dir=base_dir,
            hook_specs=runtime_cfg.hook_specs,
            event="new_project",
            targets=[],
            change={
                "source": str(getattr(ns_obj, "mode", None) or getattr(ns_obj, "child_key", None) or "auto"),
                "template": (str(getattr(ns_obj, "template", "") or "").strip() or None),
                "initial_tags": [str(tag) for tag in getattr(ns_obj, "tag", [])],
                "post_commands": [str(cmd) for cmd in getattr(ns_obj, "post", [])],
                "after_create": "open" if bool(getattr(ns_obj, "open", False)) else "stay",
                "inputs": {
                    "raw_input": raw_input,
                    "explicit_name": explicit_name,
                    "mode": getattr(ns_obj, "mode", None),
                    "child_key": getattr(ns_obj, "child_key", None),
                    "tmp": getattr(ns_obj, "tmp", None),
                    "timestamp": getattr(ns_obj, "timestamp", None),
                    "ts_name": getattr(ns_obj, "ts_name", None),
                    "alpha_name": getattr(ns_obj, "alpha_name", None),
                    "ask_name": getattr(ns_obj, "ask_name", None),
                    "ask_source": getattr(ns_obj, "ask_source", None),
                    "archive": getattr(ns_obj, "archive", None),
                    "multi": getattr(ns_obj, "multi", None),
                },
            },
            view="active",
        )
        if pre.cancelled:
            return False, pre.reason, ns_obj, raw_input, explicit_name
        changed = dict(pre.change)
        source = changed.get("source")
        if source is not None:
            source_text = str(source).strip()
            builtin = {"empty", "local", "git", "download", "downloaded"}
            if source_text == "auto":
                ns_obj.mode = None
                ns_obj.child_key = None
            elif source_text in builtin:
                ns_obj.mode = source_text
                ns_obj.child_key = None
            elif source_text:
                ns_obj.mode = None
                ns_obj.child_key = source_text
        template = changed.get("template")
        if template is not None:
            ns_obj.template = str(template).strip()
        tags = changed.get("initial_tags")
        if isinstance(tags, list):
            ns_obj.tag = [str(tag) for tag in tags if str(tag).strip()]
        post_commands = changed.get("post_commands")
        if isinstance(post_commands, list):
            ns_obj.post = [str(cmd) for cmd in post_commands if str(cmd).strip()]
        return True, "", ns_obj, raw_input, explicit_name

    try:
        rc = dispatch_command(
            ns,
            base_dir=base_dir,
            bin_dir=bin_dir,
            cwd=Path.cwd().resolve(),
            no_arg_flow=lambda bd, cwd_path, initial: no_arg_flow(
                bd,
                cwd_path,
                initial_filter_expr=initial,
                ctx=ui_ctx,
            ),
            cmd_ls=lambda bd, **kw: cmd_ls(bd, **kw),
            cmd_json=lambda bd, **kw: cmd_json(bd, **kw),
            cmd_new=lambda ns_obj, bd, cwd_path: cmd_new(
                ns_obj,
                bd,
                cwd_path,
                pre_create_hook=_pre_create_hook,
                post_create_hook=_post_create_hook,
                run_textual_ui=_run_textual_ui,
            ),
            cmd_completion=lambda shell: _cmd_completion(shell),
            cmd_internal_complete=lambda shell, cword, words: _cmd_internal_complete(
                shell,
                cword,
                words,
                base_dir=base_dir,
            ),
            cmd_recent=cmd_recent,
            cmd_help=lambda namespace: cmd_help_dispatch(
                str(getattr(namespace, "topic", "")).strip().lower(),
                print_default_help=parser.print_help,
                handlers={
                    "actions": lambda: cmd_help_actions_render(
                        actions=runtime_cfg.actions,
                        favorites=list(runtime_cfg.favorites),
                        source_filter=str(getattr(namespace, "source", "")).strip(),
                        bound_filter=str(getattr(namespace, "bound", "")).strip(),
                        view_filter=str(getattr(namespace, "view", "")).strip(),
                        show_defaults=bool(getattr(namespace, "show_defaults", False)),
                    ),
                    "hotkeys": lambda: cmd_help_hotkeys_render(
                        favorites=list(runtime_cfg.favorites),
                    ),
                },
            ),
            cmd_setup=lambda base_path, bin_path, dry_run, *, json_output=False: cmd_setup(
                base_path,
                bin_path,
                completion_script_fn=completion_script,
                shell_init_script_fn=shell_init_script,
                dry_run=dry_run,
                json_output=json_output,
            ),
            cmd_cache_warm=cmd_cache_warm,
            cmd_tags_sync=lambda bd, verbose, debug: cmd_tags_sync(
                bd,
                verbose=verbose,
                debug=debug,
            ),
            cmd_tags_ls=cmd_tags_ls,
            cmd_hooks_refresh=lambda bd, **kw: cmd_hooks_refresh(
                bd,
                hook_specs=runtime_cfg.hook_specs,
                **kw,
            ),
            cmd_utils=cmd_utils,
            cmd_archive_mv=cmd_archive_mv,
            cmd_cd=cmd_cd,
            cmd_open=cmd_open,
            cmd_raycast=lambda bd, subcommand, project, action_id: _cmd_raycast(
                bd,
                subcommand,
                project,
                action_id,
                runtime_cfg=runtime_cfg,
                compile_filter_expr=compile_filter_expr,
            ),
            cmd_rm=lambda path, force_outside_base, force=False: cmd_rm(
                path,
                force_outside_base=force_outside_base,
                force=force,
                hook_specs=runtime_cfg.hook_specs,
            ),
            cmd_fix=cmd_fix,
            cmd_deworktree=cmd_deworktree,
            cmd_fix_worktrees=cmd_fix_worktrees,
            cmd_archive_ls=cmd_archive_ls,
            cmd_archive_undo=cmd_archive_undo,
            cmd_archive_restore_entry=cmd_archive_restore_entry,
            cmd_tmux_load=cmd_tmux_load,
            cmd_tmux_save=lambda bd, dir_path, output, to_stdout, debug, pane_id, session_id, *, pause=False: cmd_tmux_save(
                bd,
                dir_path,
                output=output,
                to_stdout=to_stdout,
                debug=debug,
                pane_id_hint=pane_id,
                session_id_hint=session_id,
                pause=pause,
            ),
            cmd_benchmark=lambda bd, cwd_path, action, comment, keep_basefolder, ignore: cmd_benchmark(
                bd,
                cwd_path,
                action,
                comment=comment,
                keep_basefolder=keep_basefolder,
                ignore_featuresets=(ignore or set()),
                archive_pack_internal=archive_pack_internal,
                archive_unpack_internal=archive_unpack_internal,
            ),
            cmd_test_regression=lambda bd, cwd_path, list_only, selected: cmd_test_regression(
                bd,
                cwd_path,
                list_only=list_only,
                selected=selected,
                archive_pack_internal=archive_pack_internal,
                archive_unpack_internal=archive_unpack_internal,
                archive_restore_internal=archive_restore_internal,
                cmd_rm=cmd_rm,
            ),
            cmd_test=lambda bd, cwd_path, comment, keep_basefolder: cmd_test(
                bd,
                cwd_path,
                comment=comment,
                keep_basefolder=keep_basefolder,
                archive_pack_internal=archive_pack_internal,
                archive_unpack_internal=archive_unpack_internal,
            ),
            cmd_example_generate=cmd_example_generate,
            initial_filter_expr=initial_filter_expr,
        )
    except KeyboardInterrupt:
        print()
        return 130

    logger.debug("cli done command={} rc={}", getattr(ns, "command", None), rc)

    if rc == 1 and ns.command not in {
        None,
        "cache",
        "tags",
        "archive",
        "tmux",
        "benchmark",
        "test",
        "example",
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
