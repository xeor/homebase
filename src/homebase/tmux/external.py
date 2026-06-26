from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ..config.prefs import load_open_mode_config
from ..core import debug_timers
from ..core import utils as core_utils
from ..core.constants import (
    ENV_TMUX_SESSION,
    OPEN_MODE_CONFIG,
    OPEN_MODE_PROFILES,
    TMUX_BIN_CANDIDATES,
)
from ..core.models import PaneRef
from . import commands as tmux_commands
from . import core as tmux_core
from .client_focus import focus_tmux_client_app
from .registry import load_active_tmux_context, load_tmux_contexts

TmuxFn = Callable[..., str]
ExternalTmuxTarget = tuple[dict[str, object] | None, list[str], TmuxFn, str]
ExternalTmuxCandidate = tuple[
    dict[str, object] | None,
    list[str],
    TmuxFn,
    list[dict[str, str]],
]


def _resolve_tmux_bin() -> str:
    return tmux_core.resolve_tmux_bin(TMUX_BIN_CANDIDATES)


def _tmux_command_prefix_for_socket(socket_path: str) -> list[str]:
    command = [_resolve_tmux_bin()]
    if socket_path:
        command.extend(["-S", socket_path])
    return command


def _tmux_for_prefix(command_prefix: Callable[[], list[str]]) -> TmuxFn:
    return lambda *args: core_utils.run_out(*command_prefix(), *args)


def _tmux_socket_path_from_env() -> str:
    return tmux_core.tmux_socket_path_from_env()


def is_inside_current_tmux_pane() -> bool:
    if not os.getenv("TMUX"):
        return False
    pane_id = os.environ.get("TMUX_PANE", "").strip()
    if not pane_id:
        return False
    current_ttys: set[str] = set()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                current_ttys.add(os.ttyname(stream.fileno()))
        except (OSError, ValueError):
            continue
    if not current_ttys:
        return True
    tmux_fn = _tmux_for_prefix(
        lambda: _tmux_command_prefix_for_socket(_tmux_socket_path_from_env())
    )
    try:
        pane_tty = tmux_fn(
            "display-message",
            "-p",
            "-t",
            pane_id,
            "#{pane_tty}",
        ).strip()
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        return False
    return bool(pane_tty) and pane_tty in current_ttys


def _configured_tmux_session(base_dir: Path) -> str:
    env_session = os.environ.get(ENV_TMUX_SESSION, "").strip()
    if env_session:
        return env_session
    return str(load_open_mode_config(base_dir).get("tmux_session", "")).strip()


def external_tmux_command_prefix_and_session(
    base_dir: Path,
    *,
    quiet: bool = False,
) -> tuple[list[str], str] | None:
    resolved = _external_tmux_target(base_dir, quiet=quiet)
    if resolved is None:
        return None
    return resolved[1], resolved[3]


def resolve_external_tmux_target(
    base_dir: Path,
    *,
    quiet: bool = True,
) -> ExternalTmuxTarget | None:
    """Public accessor for the same ``(context, prefix, tmux_fn,
    session_target)`` resolution that ``b open`` uses outside tmux.

    Used by the setup Debug tab so the focus diagnostic targets the
    exact session/socket a real ``b open`` would act on."""
    return _external_tmux_target(base_dir, quiet=quiet)


def _external_tmux_target(
    base_dir: Path,
    *,
    context: dict[str, object] | None = None,
    quiet: bool = False,
) -> ExternalTmuxTarget | None:
    configured = _configured_tmux_session(base_dir)
    contexts: list[dict[str, object] | None] = (
        [context]
        if context is not None
        else [dict(candidate) for candidate in load_tmux_contexts(base_dir)]
    )
    candidates = _external_tmux_candidates(contexts)
    if not candidates:
        candidates = [_external_tmux_candidate(None, _tmux_socket_path_from_env())]

    matches = _matching_external_targets(candidates, configured)
    if len(matches) == 1:
        return matches[0]
    if not quiet:
        _report_external_tmux_resolution_failure(candidates, configured, matches)
    return None


def _matching_external_targets(
    candidates: list[ExternalTmuxCandidate],
    configured: str,
) -> list[ExternalTmuxTarget]:
    matches: list[ExternalTmuxTarget] = []
    for candidate_context, prefix, tmux_fn, sessions in candidates:
        for session in sessions:
            session_id = str(session.get("session_id", "")).strip()
            session_name = str(session.get("session_name", "")).strip()
            if configured and configured not in {session_id, session_name}:
                continue
            session_target = configured or session_id or session_name
            if session_target:
                matches.append(
                    (candidate_context, prefix, tmux_fn, session_target)
                )
    return matches


def _report_external_tmux_resolution_failure(
    candidates: list[ExternalTmuxCandidate],
    configured: str,
    matches: list[ExternalTmuxTarget],
) -> None:
    session_names = sorted(
        {
            str(session.get("session_name", "")).strip()
            for _context, _prefix, _tmux_fn, sessions in candidates
            for session in sessions
            if str(session.get("session_name", "")).strip()
        }
    )
    if configured:
        print(
            f"configured tmux session not found or ambiguous: {configured}; "
            f"sessions={', '.join(session_names)}",
            file=sys.stderr,
        )
    elif not matches:
        print("no tmux sessions found", file=sys.stderr)
    else:
        print(
            "multiple tmux sessions found; set open_mode.tmux_session "
            f"or pass --tmux-session; sessions={', '.join(session_names)}",
            file=sys.stderr,
        )


def _external_tmux_candidate(
    context: dict[str, object] | None,
    socket_path: str,
) -> ExternalTmuxCandidate:
    prefix = _tmux_command_prefix_for_socket(socket_path)
    tmux_fn = _tmux_for_prefix(lambda: prefix)
    try:
        sessions = tmux_core.tmux_list_sessions(tmux=tmux_fn)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        sessions = []
    return context, prefix, tmux_fn, sessions


def _external_tmux_candidates(
    contexts: list[dict[str, object] | None],
) -> list[ExternalTmuxCandidate]:
    candidates = []
    seen_sockets: set[str] = set()
    for context in contexts:
        socket_path = str(context.get("socket_path", "")).strip() if context else ""
        if not socket_path or socket_path in seen_sockets:
            continue
        seen_sockets.add(socket_path)
        candidates.append(_external_tmux_candidate(context, socket_path))
    return candidates


def _context_for_configured_session(
    contexts: list[dict[str, object]],
    configured: str,
) -> dict[str, object] | None:
    if not contexts:
        return None
    if not configured:
        return contexts[0]
    candidates = _external_tmux_candidates(
        [dict(candidate) for candidate in contexts]
    )
    for context, _prefix, _tmux_fn, sessions in candidates:
        if context is not None and any(
            configured
            in {
                str(session.get("session_id", "")).strip(),
                str(session.get("session_name", "")).strip(),
            }
            for session in sessions
        ):
            return context
    return None


def _load_profile_window(
    profile: Path,
    tmux_fn: TmuxFn,
    *,
    socket_path: str,
    session_target: str,
    session_pane_id: str,
) -> tuple[str, str | None]:
    tmuxp_args = ["tmuxp", "load", "-a"]
    if socket_path:
        tmuxp_args.extend(["-S", socket_path])
    env = os.environ.copy()
    if session_pane_id:
        env["TMUX_PANE"] = session_pane_id
    return tmux_commands.load_profile_window(
        profile,
        list_window_ids=lambda: {
            line.strip()
            for line in tmux_fn(
                "list-windows",
                "-t",
                session_target,
                "-F",
                "#{window_id}",
            ).splitlines()
            if line.strip()
        },
        tmuxp_args=tmuxp_args,
        env=env,
    )


def _tmux_run_for_prefix(
    tmux_command_prefix: Callable[[], list[str]],
) -> Callable[..., None]:
    def run(*args: str) -> None:
        subprocess.run([*tmux_command_prefix(), *args], check=True)

    return run


def _list_panes_args_for_session(
    args: tuple[str, ...],
    session_target: str,
) -> list[str]:
    if args[:2] != ("list-panes", "-a"):
        return list(args)
    return ["list-panes", "-s", "-t", session_target, *args[2:]]


def _tmux_find_pane_for_cwd_in_session(
    target: Path,
    tmux_fn: TmuxFn,
    session_target: str,
) -> tuple[str, str] | None:
    def find_panes(path: Path) -> list[PaneRef]:
        return tmux_commands.find_panes_for_cwd(
            path,
            tmux=lambda *args: tmux_fn(
                *_list_panes_args_for_session(args, session_target)
            ),
            is_under=core_utils.is_under,
            pane_ref_factory=PaneRef,
        )

    return tmux_commands.find_pane_for_cwd(
        target,
        tmux_find_panes_for_cwd=find_panes,
    )


def _tmux_open_new_tab_in_session(
    path: Path,
    tmux_command_prefix: Callable[[], list[str]],
    session_target: str,
) -> int:
    proc = subprocess.run(
        [
            *tmux_command_prefix(),
            "new-window",
            "-t",
            session_target,
            "-c",
            str(path),
            "-P",
            "-F",
            "#{window_id}",
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return 1
    window_id = (proc.stdout or "").strip()
    if window_id:
        subprocess.run(
            [*tmux_command_prefix(), "select-window", "-t", window_id],
            check=False,
        )
    return 0


def _tmux_open_new_tab_with_load(
    path: Path,
    tmux_command_prefix: Callable[[], list[str]],
    tmux_fn: TmuxFn,
    *,
    socket_path: str,
    session_target: str,
) -> int:
    session_pane_id = _first_pane_in_session(tmux_fn, session_target)
    return tmux_commands.open_new_tab_with_load(
        path,
        open_new_tab_with_load_status=lambda profile_path: (
            tmux_commands.open_new_tab_with_load_status(
                profile_path,
                load_profile_window=lambda profile: _load_profile_window(
                    profile,
                    tmux_fn,
                    socket_path=socket_path,
                    session_target=session_target,
                    session_pane_id=session_pane_id,
                ),
                tmux_run=_tmux_run_for_prefix(tmux_command_prefix),
                tmux_open_new_tab=lambda new_path: _tmux_open_new_tab_in_session(
                    new_path,
                    tmux_command_prefix,
                    session_target,
                ),
            )
        ),
    )


def _first_pane_in_session(tmux_fn: TmuxFn, session_target: str) -> str:
    try:
        raw = tmux_fn(
            "list-panes",
            "-s",
            "-t",
            session_target,
            "-F",
            "#{pane_id}",
        )
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        return ""
    return next((line.strip() for line in raw.splitlines() if line.strip()), "")


def _open_profile_spec(profile: str) -> dict[str, object]:
    spec = next(
        (p for p in OPEN_MODE_PROFILES if str(p.get("id")) == profile),
        None,
    )
    return spec or OPEN_MODE_PROFILES[0]


def _context_open_mode_loader(
    context: dict[str, object] | None,
) -> Callable[[Path], dict[str, str]]:
    open_profile = str(context.get("open_profile", "")).strip() if context else ""

    def load_context_open_mode(base_dir: Path) -> dict[str, str]:
        if open_profile:
            return {"profile": open_profile}
        return load_open_mode_config(base_dir)

    return load_context_open_mode


def _open_with_external_tmux_target(
    base_dir: Path,
    path: Path,
    *,
    context: dict[str, object] | None,
    load_context_open_mode: Callable[[Path], dict[str, str]],
    prefix: list[str],
    tmux_fn: TmuxFn,
    session_target: str,
    open_shell_in_dir: Callable[[Path], int],
) -> int:
    def tmux_command_prefix() -> list[str]:
        return list(prefix)

    socket_path = str(context.get("socket_path", "")).strip() if context else ""
    with debug_timers.timed_step(base_dir, "tmux_focus.open_with_mode") as info:
        rc = tmux_commands.open_with_mode(
            base_dir,
            path,
            load_open_mode_config=load_context_open_mode,
            open_mode_default_profile=str(OPEN_MODE_CONFIG["profile"]),
            open_mode_profiles=OPEN_MODE_PROFILES,
            open_shell_in_dir=open_shell_in_dir,
            tmux_find_pane_for_cwd=lambda target: _tmux_find_pane_for_cwd_in_session(
                target,
                tmux_fn,
                session_target,
            ),
            tmux_command_prefix=tmux_command_prefix,
            tmux_open_new_tab_with_load=lambda target: _tmux_open_new_tab_with_load(
                target,
                tmux_command_prefix,
                tmux_fn,
                socket_path=socket_path,
                session_target=session_target,
            ),
            tmux_open_new_tab=lambda target: _tmux_open_new_tab_in_session(
                target,
                tmux_command_prefix,
                session_target,
            ),
            tmux_available=lambda: True,
        )
        info["rc"] = rc
    if rc == 0:
        focus_tmux_client_app(tmux_fn, base_dir)
    return rc


def open_with_mode_outside_tmux(
    base_dir: Path,
    path: Path,
    *,
    open_shell_in_dir: Callable[[Path], int],
) -> int:
    configured = _configured_tmux_session(base_dir)
    profile_context = (
        _context_for_configured_session(load_tmux_contexts(base_dir), configured)
        if configured
        else load_active_tmux_context(base_dir)
    )
    load_context_open_mode = _context_open_mode_loader(profile_context)
    profile = load_context_open_mode(base_dir).get(
        "profile",
        str(OPEN_MODE_CONFIG["profile"]),
    )
    spec = _open_profile_spec(profile)
    if not bool(spec.get("use_tmux", False)):
        return open_shell_in_dir(path)
    with debug_timers.timed_step(base_dir, "tmux_focus.external_target_resolution") as info:
        resolved = _external_tmux_target(base_dir)
        info["resolved"] = resolved is not None
    if resolved is None:
        return 1
    context, prefix, tmux_fn, session_target = resolved
    return _open_with_external_tmux_target(
        base_dir,
        path,
        context=context,
        load_context_open_mode=load_context_open_mode,
        prefix=prefix,
        tmux_fn=tmux_fn,
        session_target=session_target,
        open_shell_in_dir=open_shell_in_dir,
    )
