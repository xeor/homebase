from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

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
from ..core.utils import find_marker_root_upward as _find_marker_root_upward
from . import commands as tmux_commands
from . import core as tmux_core
from .registry import load_active_tmux_context


def find_marker_root_upward(path: Path) -> Path | None:
    return _find_marker_root_upward(path, BASE_MARKER_FILE)


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


def _tmux_command_prefix_for_socket(socket_path: str) -> list[str]:
    cmd = [_resolve_tmux_bin()]
    if socket_path:
        cmd += ["-S", socket_path]
    return cmd


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


def _tmux_for_prefix(tmux_command_prefix: Callable[[], list[str]]) -> Callable[..., str]:
    return lambda *args: core_utils.run_out(*tmux_command_prefix(), *args)


def _list_window_ids_for_tmux(tmux_fn: Callable[..., str]) -> set[str]:
    return tmux_commands.list_window_ids(tmux=tmux_fn)


def _load_profile_window_for_tmux(
    profile: Path,
    tmux_fn: Callable[..., str],
) -> tuple[str, str | None]:
    return tmux_commands.load_profile_window(
        profile,
        list_window_ids=lambda: _list_window_ids_for_tmux(tmux_fn),
    )


def _tmux_run_for_prefix(tmux_command_prefix: Callable[[], list[str]]) -> Callable[..., None]:
    def run(*args: str) -> None:
        subprocess.run([*tmux_command_prefix(), *args], check=True)

    return run


def _tmux_find_pane_for_cwd_for_tmux(
    target: Path,
    tmux_fn: Callable[..., str],
) -> tuple[str, str] | None:
    return tmux_commands.find_pane_for_cwd(
        target,
        tmux_find_panes_for_cwd=lambda path: tmux_commands.find_panes_for_cwd(
            path,
            tmux=tmux_fn,
            is_under=core_utils.is_under,
            pane_ref_factory=PaneRef,
        ),
    )


def _tmux_open_new_tab_for_prefix(
    path: Path,
    tmux_command_prefix: Callable[[], list[str]],
) -> int:
    return tmux_commands.tmux_open_new_tab(
        path,
        tmux_command_prefix=tmux_command_prefix,
    )


def _tmux_open_new_tab_with_load_for_prefix(
    path: Path,
    tmux_command_prefix: Callable[[], list[str]],
    tmux_fn: Callable[..., str],
) -> int:
    return tmux_commands.open_new_tab_with_load(
        path,
        open_new_tab_with_load_status=lambda profile_path: (
            tmux_commands.open_new_tab_with_load_status(
                profile_path,
                load_profile_window=lambda profile: _load_profile_window_for_tmux(
                    profile,
                    tmux_fn,
                ),
                tmux_run=_tmux_run_for_prefix(tmux_command_prefix),
                tmux_open_new_tab=lambda new_path: _tmux_open_new_tab_for_prefix(
                    new_path,
                    tmux_command_prefix,
                ),
            )
        ),
    )


def _focus_tmux_client_app(tmux_fn: Callable[..., str]) -> None:
    if sys.platform != "darwin":
        return
    try:
        raw_pid = tmux_fn("display-message", "-p", "#{client_pid}").strip()
        pid = int(raw_pid)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        return
    for candidate in _pid_ancestry(pid):
        if _focus_macos_app_process(candidate):
            return


def _pid_ancestry(pid: int) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        seen.add(current)
        out.append(current)
        try:
            proc = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(current)],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                break
            current = int(proc.stdout.strip())
        except (OSError, ValueError):
            break
    return out


def _focus_macos_app_process(pid: int) -> bool:
    script = (
        'tell application "System Events"\n'
        f"  set matches to application processes whose unix id is {pid}\n"
        "  if (count of matches) is 0 then return false\n"
        "  set frontmost of item 1 of matches to true\n"
        "  return true\n"
        "end tell"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _open_profile_spec(profile: str) -> dict[str, object]:
    spec = next(
        (p for p in OPEN_MODE_PROFILES if str(p.get("id")) == profile),
        None,
    )
    return spec or OPEN_MODE_PROFILES[0]


def _context_pane_for_project(
    context: dict[str, object],
    path: Path,
) -> dict[str, object] | None:
    raw = context.get("project_panes", {})
    if not isinstance(raw, dict):
        return None
    try:
        panes = raw.get(str(path.resolve()), [])
    except (OSError, RuntimeError, ValueError):
        panes = raw.get(str(path), [])
    if not isinstance(panes, list):
        return None
    candidates = [pane for pane in panes if isinstance(pane, dict)]
    if not candidates:
        return None
    candidates.sort(
        key=lambda pane: (
            0 if bool(pane.get("active", False)) else 1,
            str(pane.get("target", "")),
            str(pane.get("pane_id", "")),
        )
    )
    return candidates[0]


def _select_context_pane(
    pane: dict[str, object],
    tmux_command_prefix: Callable[[], list[str]],
) -> int:
    pane_id = str(pane.get("pane_id", "")).strip()
    target = str(pane.get("target", "")).strip()
    window_id = target.rsplit(".", 1)[0]
    if not pane_id or not window_id:
        return 1
    p1 = subprocess.run(
        [*tmux_command_prefix(), "select-window", "-t", window_id],
        check=False,
    )
    p2 = subprocess.run(
        [*tmux_command_prefix(), "select-pane", "-t", pane_id],
        check=False,
    )
    return 0 if p1.returncode == 0 and p2.returncode == 0 else 1


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
        is_under=core_utils.is_under,
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
    pause: bool = False,
) -> int:
    return tmux_commands.cmd_tmux_save(
        base_dir,
        dir_path,
        output,
        to_stdout,
        debug,
        pane_id_hint,
        session_id_hint,
        pause=pause,
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
    """Either tell the parent shell to ``cd`` here (preferred), or
    exec a sub-shell at this directory (fallback).

    Protocol — when the user has installed the shell-integration
    wrapper (see ``b shell-init <shell>``) it exports
    ``HOMEBASE_CD_FILE=<temp>`` before invoking the binary. We write
    the target path into that file and return cleanly; the wrapper
    then `cd`s the parent shell into it. This keeps the user's
    original shell alive — no phantom-cwd errors after deletion or
    archive moves.

    When the wrapper isn't installed:
      * TTY → exec a fresh shell at ``path`` (existing behavior),
        prefixed with a one-line stderr hint pointing at
        ``b shell-init`` so the user knows the better path exists.
        Suppress the hint when ``HOMEBASE_QUIET_FALLBACK`` is truthy.
      * Non-TTY (pipes, pytest captures) → no-op.
    """
    cd_file = os.environ.get("HOMEBASE_CD_FILE", "")
    if cd_file:
        # The wrapper expects either an empty file (no cd requested)
        # or a single path. ``fsync`` defends against a SIGKILL race:
        # a partial write fails the wrapper's ``[ -d "$d" ]`` check.
        try:
            payload = str(path.resolve()).encode("utf-8")
            fd = os.open(cd_file, os.O_WRONLY | os.O_TRUNC)
            try:
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            return 0
        except OSError:
            # Wrapper file unwritable for some reason — fall through
            # to the sub-shell fallback rather than crashing.
            pass

    if not sys.stdout.isatty():
        # pytest / piped output / non-interactive — never exec.
        return 0

    if not os.environ.get("HOMEBASE_QUIET_FALLBACK"):
        shell_name = Path(os.environ.get("SHELL", "/bin/sh")).name
        print(
            f"[homebase] tip: install the shell wrapper so the parent\n"
            f"           shell can cd instead of opening a sub-shell.\n"
            f"           Run `b setup` (or `b shell-init {shell_name}`).\n"
            f"           Falling back to sub-shell.",
            file=sys.stderr,
        )
    shell = os.environ.get("SHELL", "/bin/sh")
    os.chdir(path)
    os.execvp(shell, [shell])  # nosec B606  # intentional shell launch into user's $SHELL


def tmux_find_pane_for_cwd(target: Path) -> tuple[str, str] | None:
    return tmux_commands.find_pane_for_cwd(
        target,
        tmux_find_panes_for_cwd=tmux_find_panes_for_cwd,
    )


def tmux_find_panes_for_cwd(target: Path) -> list[PaneRef]:
    return tmux_commands.find_panes_for_cwd(
        target,
        tmux=tmux,
        is_under=core_utils.is_under,
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
    context = None if os.getenv("TMUX") else load_active_tmux_context(base_dir)
    socket_path = str(context.get("socket_path", "")).strip() if context else ""
    if socket_path:
        assert context is not None
        open_profile = str(context.get("open_profile", "")).strip()

        def tmux_command_prefix() -> list[str]:
            return _tmux_command_prefix_for_socket(socket_path)

        tmux_fn = _tmux_for_prefix(tmux_command_prefix)
        def load_context_open_mode(_base_dir: Path) -> dict[str, str]:
            if open_profile:
                return {"profile": open_profile}
            return load_open_mode_config(_base_dir)

        profile = load_context_open_mode(base_dir).get(
            "profile",
            str(OPEN_MODE_CONFIG["profile"]),
        )
        spec = _open_profile_spec(profile)
        if bool(spec.get("use_tmux", False)) and bool(spec.get("goto_loaded", False)):
            pane = _context_pane_for_project(context, path)
            if pane is not None:
                rc = _select_context_pane(pane, tmux_command_prefix)
                if rc == 0:
                    _focus_tmux_client_app(tmux_fn)
                return rc

        rc = tmux_commands.open_with_mode(
            base_dir,
            path,
            load_open_mode_config=load_context_open_mode,
            open_mode_default_profile=str(OPEN_MODE_CONFIG["profile"]),
            open_mode_profiles=OPEN_MODE_PROFILES,
            open_shell_in_dir=open_shell_in_dir,
            tmux_find_pane_for_cwd=lambda target: _tmux_find_pane_for_cwd_for_tmux(
                target,
                tmux_fn,
            ),
            tmux_command_prefix=tmux_command_prefix,
            tmux_open_new_tab_with_load=lambda target: (
                _tmux_open_new_tab_with_load_for_prefix(
                    target,
                    tmux_command_prefix,
                    tmux_fn,
                )
            ),
            tmux_open_new_tab=lambda target: _tmux_open_new_tab_for_prefix(
                target,
                tmux_command_prefix,
            ),
            tmux_available=lambda: True,
        )
        if rc == 0:
            _focus_tmux_client_app(tmux_fn)
        return rc

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
