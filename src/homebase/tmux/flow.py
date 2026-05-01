from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..commands import workspace as commands_workspace
from ..config.prefs import load_open_mode_config
from ..core import utils as core_utils
from ..core.constants import (
    ACTION_CANCEL,
    BASE_MARKER_FILE,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    TMUX_BIN_CANDIDATES,
    TMUX_SHELL_COMMANDS,
)
from ..core.models import PaneRef
from ..workspace.rows import is_under
from . import commands as tmux_commands
from . import core as tmux_core


def find_marker_root_upward(path: Path) -> Path | None:
    return commands_workspace.find_marker_root_upward(path, BASE_MARKER_FILE)


def _prompt_readline(
    prompt: str,
    default: str | None = None,
    non_interactive_default: str | None = None,
) -> str | None:
    from ..core import prompting

    return prompting.prompt_readline(
        prompt,
        default=default,
        non_interactive_default=non_interactive_default,
    )


def tmux(*args: str) -> str:
    return core_utils.run_out(*_tmux_command_prefix(), *args)


def tmux_run(*args: str) -> None:
    subprocess.run([*_tmux_command_prefix(), *args], check=True)


def _tmux_socket_path_from_env() -> str:
    return tmux_core.tmux_socket_path_from_env()


def _resolve_tmux_bin() -> str:
    return tmux_core.resolve_tmux_bin(TMUX_BIN_CANDIDATES)


def _tmux_command_prefix() -> list[str]:
    return tmux_core.tmux_command_prefix(resolve_tmux_bin=_resolve_tmux_bin)


def list_window_ids() -> set[str]:
    return tmux_commands.list_window_ids(tmux=tmux)


def load_profile_window(profile: Path) -> tuple[str, str | None]:
    return tmux_commands.load_profile_window(profile, list_window_ids=list_window_ids)


def tmux_open_new_tab_with_load_status(path: Path) -> tuple[int, str | None]:
    return tmux_commands.open_new_tab_with_load_status(
        path,
        load_profile_window=load_profile_window,
        tmux_run=tmux_run,
        tmux_open_new_tab=tmux_open_new_tab,
    )


def choose_load_mode(pane_count: int) -> str:
    return tmux_commands.choose_load_mode(
        pane_count,
        action_cancel=ACTION_CANCEL,
        prompt_readline=_prompt_readline,
        is_interactive=(sys.stdin.isatty() and sys.stdout.isatty()),
    )


def cmd_tmux_load(dir_path: str = ".") -> int:
    return tmux_commands.cmd_tmux_load(
        dir_path,
        action_cancel=ACTION_CANCEL,
        tmux=tmux,
        tmux_run=tmux_run,
        choose_load_mode=choose_load_mode,
        load_profile_window=load_profile_window,
    )


def _tmux_display(value: str, target: str = "") -> str:
    return tmux_core.tmux_display(value, tmux=tmux, target=target)


def _tmux_notify(message: str, pane_id: str = "", delay_ms: int = 4000) -> None:
    tmux_core.tmux_notify(
        message,
        tmux_command_prefix=_tmux_command_prefix,
        pane_id=pane_id,
        delay_ms=delay_ms,
    )


def _tmux_parse_rows(raw: str, fields: int) -> list[list[str]]:
    return tmux_core.tmux_parse_rows(raw, fields)


def _tmux_list_sessions() -> list[dict[str, str]]:
    return tmux_core.tmux_list_sessions(tmux=tmux)


def _tmux_list_windows(session_id: str) -> list[dict[str, str]]:
    return tmux_core.tmux_list_windows(session_id, tmux=tmux)


def _tmux_list_panes(window_id: str) -> list[dict[str, str]]:
    return tmux_core.tmux_list_panes(window_id, tmux=tmux)


def _tmux_find_window_by_pane_id(pane_id: str) -> tuple[str, str] | None:
    return tmux_core.tmux_find_window_by_pane_id(pane_id, tmux=tmux)


def _tmux_session_activity(session: dict[str, str]) -> int:
    return tmux_core.tmux_session_activity(session)


def _tmux_active_window_in_session(session_id: str) -> dict[str, str]:
    return tmux_core.tmux_active_window_in_session(
        session_id,
        tmux_list_windows=_tmux_list_windows,
        tmux_display=lambda value, target: _tmux_display(value, target=target),
    )


def _tmux_resolve_session_window(
    pane_id_hint: str = "", session_id_hint: str = ""
) -> tuple[dict[str, str], dict[str, str]]:
    return tmux_core.tmux_resolve_session_window(
        pane_id_hint=pane_id_hint,
        session_id_hint=session_id_hint,
        tmux_list_sessions=_tmux_list_sessions,
        tmux_find_window_by_pane_id=_tmux_find_window_by_pane_id,
        tmux_list_windows=_tmux_list_windows,
        tmux_active_window_in_session=_tmux_active_window_in_session,
        tmux_display=lambda value, target: _tmux_display(value, target=target),
    )


def _first_token_basename(cmdline: str) -> str:
    return tmux_core.first_token_basename(cmdline)


def _tty_process_rows(tty: str) -> list[tuple[int, int, int, int, str]]:
    return tmux_core.tty_process_rows(tty)


def _is_descendant_pid(pid: int, ancestor: int, parent_by_pid: dict[int, int]) -> bool:
    return tmux_core.is_descendant_pid(pid, ancestor, parent_by_pid)


def _pid_command_line(pid: int) -> str:
    return tmux_core.pid_command_line(pid)


def _pane_best_run_command_debug(pane: dict[str, str]) -> dict[str, object]:
    return tmux_core.pane_best_run_command_debug(
        pane,
        shell_commands=TMUX_SHELL_COMMANDS,
    )


def _resolve_project_root_from_panes(
    pane_start_dirs: list[str], base_root: Path
) -> tuple[Path, dict[str, object]]:
    return tmux_core.resolve_project_root_from_panes(
        pane_start_dirs,
        base_root,
        is_under=is_under,
        find_marker_root_upward=find_marker_root_upward,
    )


def _resolve_tmux_save_output(raw_output: str, project_root: Path) -> Path:
    return tmux_core.resolve_tmux_save_output(raw_output, project_root)


def _tmux_save_debug_snapshot(
    sessions: list[dict[str, str]],
) -> list[dict[str, object]]:
    return tmux_commands.tmux_save_debug_snapshot(
        sessions,
        tmux_list_windows=_tmux_list_windows,
        tmux_list_panes=_tmux_list_panes,
    )


def _format_error(exc: Exception) -> str:
    return tmux_core.format_error(exc)


def cmd_tmux_save(
    base_dir: Path,
    dir_path: str = ".",
    output: str = "",
    to_stdout: bool = False,
    debug: bool = False,
    pane_id_hint: str = "",
    session_id_hint: str = "",
) -> int:
    return tmux_commands.cmd_tmux_save(
        base_dir,
        dir_path,
        output,
        to_stdout,
        debug,
        pane_id_hint,
        session_id_hint,
        tmux_list_sessions=_tmux_list_sessions,
        tmux_resolve_session_window=_tmux_resolve_session_window,
        tmux_list_panes=_tmux_list_panes,
        resolve_project_root_from_panes=_resolve_project_root_from_panes,
        pane_best_run_command_debug=_pane_best_run_command_debug,
        tmux_display=_tmux_display,
        tmux_save_debug_snapshot=_tmux_save_debug_snapshot,
        resolve_tmux_save_output=_resolve_tmux_save_output,
        tmux_notify=lambda message, pane_id, delay_ms: _tmux_notify(
            message,
            pane_id=pane_id,
            delay_ms=delay_ms,
        ),
        format_error=_format_error,
    )


def open_shell_in_dir(path: Path) -> int:
    shell = os.environ.get("SHELL", "/bin/sh")
    os.chdir(path)
    os.execvp(shell, [shell])
    return 0


def tmux_find_pane_for_cwd(target: Path) -> tuple[str, str] | None:
    return tmux_commands.find_pane_for_cwd(
        target,
        tmux_find_panes_for_cwd=tmux_find_panes_for_cwd,
    )


def tmux_find_panes_for_cwd(target: Path) -> list[PaneRef]:
    return tmux_commands.find_panes_for_cwd(
        target,
        tmux=tmux,
        is_under=is_under,
        pane_ref_factory=PaneRef,
    )


def tmux_open_new_tab(path: Path) -> int:
    return tmux_commands.tmux_open_new_tab(
        path,
        tmux_command_prefix=_tmux_command_prefix,
    )


def tmux_open_new_tab_with_load(path: Path) -> int:
    return tmux_commands.open_new_tab_with_load(
        path,
        open_new_tab_with_load_status=tmux_open_new_tab_with_load_status,
    )


def open_with_mode(base_dir: Path, path: Path) -> int:
    return tmux_commands.open_with_mode(
        base_dir,
        path,
        load_open_mode_config=load_open_mode_config,
        open_mode_default_profile=str(OPEN_MODE_CONFIG["profile"]),
        open_mode_profiles=OPEN_MODE_PROFILES,
        open_shell_in_dir=open_shell_in_dir,
        tmux_find_pane_for_cwd=tmux_find_pane_for_cwd,
        tmux_command_prefix=_tmux_command_prefix,
        tmux_open_new_tab_with_load=tmux_open_new_tab_with_load,
        tmux_open_new_tab=tmux_open_new_tab,
    )


