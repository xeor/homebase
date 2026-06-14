from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import yaml


def list_window_ids(*, tmux: Callable[..., str]) -> set[str]:
    out = tmux("list-windows", "-F", "#{window_id}")
    return {line.strip() for line in out.splitlines() if line.strip()}


def load_profile_window(
    profile: Path,
    *,
    list_window_ids: Callable[[], set[str]],
) -> tuple[str, str | None]:
    before = list_window_ids()
    proc = subprocess.run(
        ["tmuxp", "load", "-a", str(profile)],
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    created = sorted(list_window_ids() - before)
    if len(created) != 1:
        raise RuntimeError(f"expected one new window from tmuxp load, got {len(created)}")
    status_line: str | None = None
    combined = "\n".join(x for x in [(proc.stdout or "").strip(), (proc.stderr or "").strip()] if x)
    for raw in combined.splitlines():
        line = raw.strip()
        if line.lower().startswith("loaded workspace:"):
            status_line = line
            break
    return created[0], status_line


def choose_load_mode(
    pane_count: int,
    *,
    action_cancel: str,
    prompt_readline: Callable[..., str | None],
    is_interactive: bool,
) -> str:
    if pane_count <= 1:
        return "overwrite"
    print("Current window has splits/panes.")
    print("Choose load mode:")
    print("  1) overwrite current window")
    print("  2) open as new tab")
    print("  3) merge into current tab")
    print("  4) cancel")
    while True:
        choice = prompt_readline(
            "Select [1-4]: ",
            default="4",
            non_interactive_default="4",
        )
        if choice is None:
            return action_cancel
        if choice == "1":
            return "overwrite"
        if choice == "2":
            return "new"
        if choice == "3":
            return "merge"
        if choice == "4":
            return action_cancel
        if not is_interactive:
            print("invalid non-interactive choice, using cancel")
            return action_cancel
        print("invalid choice")


def open_new_tab_with_load_status(
    path: Path,
    *,
    load_profile_window: Callable[[Path], tuple[str, str | None]],
    tmux_run: Callable[..., None],
    tmux_open_new_tab: Callable[[Path], int],
) -> tuple[int, str | None]:
    profile = path / ".tmuxp.yaml"
    if profile.is_file() and shutil.which("tmuxp") is not None:
        try:
            window_id, status_line = load_profile_window(profile)
            tmux_run("select-window", "-t", window_id)
            return 0, status_line
        except (subprocess.SubprocessError, OSError, ValueError):
            return tmux_open_new_tab(path), None
    return tmux_open_new_tab(path), None


def open_new_tab_with_load(
    path: Path,
    *,
    open_new_tab_with_load_status: Callable[[Path], tuple[int, str | None]],
) -> int:
    rc, _status_line = open_new_tab_with_load_status(path)
    return rc


def find_panes_for_cwd(
    target: Path,
    *,
    tmux: Callable[..., str],
    is_under: Callable[[Path, Path], bool],
    pane_ref_factory: Callable[..., Any],
) -> list[Any]:
    try:
        out = tmux(
            "list-panes",
            "-a",
            "-F",
            "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t#{window_name}\t#{pane_current_command}\t#{pane_current_path}\t#{?pane_active,1,0}",
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        return []
    cwd_rows: list[Any] = []
    window_rows: list[Any] = []
    target_res = target.resolve()
    target_name = target_res.name
    for line in out.splitlines():
        parts = line.split("\t", 5)
        if len(parts) != 6:
            continue
        pane_id, target_text, window_name, command, cwd_text, active_raw = parts
        try:
            cwd = Path(cwd_text).resolve()
        except (OSError, ValueError):
            continue
        pane = pane_ref_factory(
            pane_id=pane_id.strip(),
            target=target_text.strip(),
            window_name=window_name.strip(),
            command=command.strip(),
            cwd=cwd,
            active=(active_raw.strip() == "1"),
        )
        if cwd == target_res or is_under(cwd, target_res):
            cwd_rows.append(pane)
        elif window_name.strip() == target_name:
            window_rows.append(pane)
    rows = cwd_rows or window_rows
    rows.sort(
        key=lambda pane: (
            0 if pane.active else 1,
            pane.target.rsplit(".", 1)[0],
            pane.target,
            pane.pane_id,
        )
    )
    return rows


def find_pane_for_cwd(
    target: Path,
    *,
    tmux_find_panes_for_cwd: Callable[[Path], list[Any]],
) -> tuple[str, str] | None:
    matches = tmux_find_panes_for_cwd(target)
    if not matches:
        return None
    pane = matches[0]
    target_window = pane.target.rsplit(".", 1)[0]
    return pane.pane_id, target_window


def tmux_open_new_tab(
    path: Path,
    *,
    tmux_command_prefix: Callable[[], list[str]],
) -> int:
    proc = subprocess.run(
        [
            *tmux_command_prefix(),
            "new-window",
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


def open_with_mode(
    base_dir: Path,
    path: Path,
    *,
    load_open_mode_config: Callable[[Path], dict[str, str]],
    open_mode_default_profile: str,
    open_mode_profiles: list[dict[str, object]],
    open_shell_in_dir: Callable[[Path], int],
    tmux_find_pane_for_cwd: Callable[[Path], tuple[str, str] | None],
    tmux_command_prefix: Callable[[], list[str]],
    tmux_open_new_tab_with_load: Callable[[Path], int],
    tmux_open_new_tab: Callable[[Path], int],
    tmux_available: Callable[[], bool] | None = None,
) -> int:
    conf = load_open_mode_config(base_dir)
    profile = str(conf.get("profile", open_mode_default_profile))
    spec = next((p for p in open_mode_profiles if str(p.get("id")) == profile), None)
    if spec is None:
        spec = open_mode_profiles[0]

    use_tmux = bool(spec.get("use_tmux", False))
    run_load = bool(spec.get("run_load", False))
    goto_loaded = bool(spec.get("goto_loaded", False))
    fallback_cd = bool(spec.get("fallback_cd", True))

    if not use_tmux:
        return open_shell_in_dir(path)

    is_tmux_available = tmux_available or (lambda: bool(os.getenv("TMUX")))
    if not is_tmux_available():
        if fallback_cd:
            return open_shell_in_dir(path)
        print("open mode requires tmux session", file=sys.stderr)
        return 1

    if goto_loaded:
        found = tmux_find_pane_for_cwd(path)
        if found is not None:
            pane_id, window_id = found
            subprocess.run([*tmux_command_prefix(), "select-window", "-t", window_id], check=False)
            subprocess.run([*tmux_command_prefix(), "select-pane", "-t", pane_id], check=False)
            return 0

    if run_load:
        return tmux_open_new_tab_with_load(path)
    return tmux_open_new_tab(path)


def cmd_tmux_load(
    dir_path: str = ".",
    *,
    action_cancel: str,
    tmux: Callable[..., str],
    tmux_run: Callable[..., None],
    choose_load_mode: Callable[[int], str],
    load_profile_window: Callable[[Path], tuple[str, str | None]],
) -> int:
    profile = Path(dir_path).resolve() / ".tmuxp.yaml"
    if not profile.is_file():
        print(f"no .tmuxp.yaml in {Path(dir_path).resolve()}", file=sys.stderr)
        return 1
    if not os.getenv("TMUX"):
        print("not inside a tmux session", file=sys.stderr)
        return 1
    data = yaml.safe_load(profile.read_text())
    windows = data.get("windows", []) if isinstance(data, dict) else []
    if len(windows) != 1:
        print(".tmuxp.yaml must contain exactly one window", file=sys.stderr)
        return 1
    session_name = tmux("display-message", "-p", "#{session_name}")
    current_window_id = tmux("display-message", "-p", "#{window_id}")
    current_index = tmux("display-message", "-p", "#{window_index}")
    pane_count = int(tmux("display-message", "-p", "#{window_panes}"))
    mode = choose_load_mode(pane_count)
    if mode == action_cancel:
        print("cancelled")
        return 0
    new_window_id, status_line = load_profile_window(profile)
    if status_line:
        print(status_line)
    if mode == "new":
        tmux_run("select-window", "-t", new_window_id)
        return 0
    if mode == "overwrite":
        tmux_run(
            "move-window",
            "-k",
            "-s",
            new_window_id,
            "-t",
            f"{session_name}:{current_index}",
        )
        tmux_run("select-window", "-t", f"{session_name}:{current_index}")
        return 0
    try:
        pane_ids = [
            pane.strip()
            for pane in tmux("list-panes", "-t", new_window_id, "-F", "#{pane_id}").splitlines()
            if pane.strip()
        ]
        if not pane_ids:
            raise RuntimeError("newly loaded window has no panes")
        for pane_id in pane_ids:
            tmux_run("join-pane", "-s", pane_id, "-t", current_window_id)
        tmux_run("select-layout", "-t", current_window_id, "tiled")
        return 0
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        print(f"merge failed: {exc}", file=sys.stderr)
        print("loaded window is kept as new tab", file=sys.stderr)
        return 1


def tmux_save_debug_snapshot(
    sessions: list[dict[str, str]],
    *,
    tmux_list_windows: Callable[[str], list[dict[str, str]]],
    tmux_list_panes: Callable[[str], list[dict[str, str]]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for session in sessions:
        sid = session.get("session_id", "")
        windows_snapshot: list[dict[str, object]] = []
        for window in tmux_list_windows(sid):
            wid = window.get("window_id", "")
            windows_snapshot.append(
                {
                    "window_id": wid,
                    "window_name": window.get("window_name", ""),
                    "window_active": window.get("window_active", ""),
                    "panes": tmux_list_panes(wid),
                }
            )
        out.append(
            {
                "session_id": sid,
                "session_name": session.get("session_name", ""),
                "session_activity": session.get("session_activity", ""),
                "session_attached": session.get("session_attached", ""),
                "windows": windows_snapshot,
            }
        )
    return out


def _wait_for_enter() -> None:
    print("")
    print("Press ESC to close…", flush=True)
    # ESC is intercepted by tmux at the popup level and closes the
    # popup (killing this process). No other key works — they echo
    # into the popup buffer but never reach this process's stdin in
    # a way that releases the read. The os.read call below just
    # parks the process so the popup stays open until ESC.
    try:
        os.read(sys.stdin.fileno(), 1)
    except (OSError, KeyboardInterrupt):
        return


# Common install locations to probe when $PATH is stripped — tmux
# servers started before the shell rc loaded /opt/homebrew/bin etc.
# would otherwise wrongly report tmux/tmuxp as MISSING.
_BIN_SEARCH_PREFIXES: tuple[str, ...] = (
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/opt/local/bin",
    "/usr/bin",
    "/bin",
)


def _find_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for prefix in _BIN_SEARCH_PREFIXES:
        candidate = Path(prefix) / name
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        except OSError:
            continue
    extra_home = Path(os.environ.get("HOME", "")) / ".local" / "bin" / name
    try:
        if extra_home.is_file() and os.access(extra_home, os.X_OK):
            return str(extra_home)
    except OSError:
        pass
    return None


def _tool_version(binary: str) -> str:
    found = _find_bin(binary)
    if not found:
        return "MISSING"
    # Augment PATH so child processes (e.g. tmuxp's internal `tmux`
    # lookup during `tmuxp --version`) can find their own deps even
    # when the tmux server was started with a stripped PATH.
    env = os.environ.copy()
    extra_prefixes = ":".join(_BIN_SEARCH_PREFIXES)
    env["PATH"] = (
        f"{env.get('PATH', '')}:{extra_prefixes}"
        if env.get("PATH")
        else extra_prefixes
    )
    try:
        proc = subprocess.run(
            [found, "-V"] if binary == "tmux" else [found, "--version"],
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return found
    line = (proc.stdout or proc.stderr or "").strip().splitlines()
    version = line[0] if line else ""
    return f"{found}  ({version})" if version else found


# ANSI color codes — tmux display-popup renders these.
_C_BANNER = "\033[1;41;37m"  # bold white on red bg
_C_HINT = "\033[1;33m"  # bold yellow
_C_DIM = "\033[2m"
_C_RESET = "\033[0m"


def print_error_banner(headline: str, hint: str = "") -> None:
    """Print a prominent colored banner naming the actual failure."""
    print("", flush=True)
    print(f"{_C_BANNER}  ✗ {headline}  {_C_RESET}", flush=True)
    if hint:
        for line in hint.splitlines():
            print(f"{_C_HINT}  → {line}{_C_RESET}", flush=True)
    print("", flush=True)


def classify_save_error(detail: str, base_root: Path | None = None) -> tuple[str, str]:
    """Map an exception detail string to (headline, hint).

    The headline is the user-facing problem name; the hint is a
    concrete next step. Anything not matched falls back to the raw
    detail so we never hide information.
    """
    low = detail.lower()
    base_text = str(base_root) if base_root else "your base folder"
    if "not inside a tmux session" in low:
        return (
            "not running inside a tmux session",
            "$TMUX is unset. The keybinding should set this automatically when "
            "run from a tmux pane — did you launch b tmux save manually?",
        )
    if "no pane start directories under base root" in low:
        return (
            "this pane is outside your base folder",
            f"in the pane that triggered this popup (not this popup itself), "
            f"cd into a project under {base_text}, then press the keybinding "
            f"again.",
        )
    if "no project root found" in low or "no_project_root" in low:
        return (
            "this pane is under base but not in a project (no .base.yaml found)",
            f"in the originating pane, cd into a folder under {base_text} "
            f"that contains a .base.yaml marker, then press the keybinding "
            f"again.",
        )
    if "multiple project roots" in low:
        return (
            "this window's panes span multiple projects",
            "all panes in the window must share one project — close the "
            "extra panes or move them to another window, then retry.",
        )
    if "resolved active window has no panes" in low:
        return (
            "the active tmux window reports no panes",
            "this is unusual — try detaching/reattaching tmux, then retry.",
        )
    if "no pane start directories found" in low:
        return (
            "tmux returned no pane working directories",
            "tmux may be wedged — check `tmux list-panes -a` manually.",
        )
    if "command not found" in low or "no such file or directory" in low:
        return (
            "a required binary is missing",
            "check the diagnostics block below for tmux/tmuxp paths.",
        )
    return ("b tmux save failed", detail)


def print_save_diagnostics_header(
    pane_id_hint: str,
    session_id_hint: str,
) -> None:
    """Print environment info at the start of every popup run.

    Cheap (~3s budget for version subprocess calls). Looks in common
    install prefixes so a stripped $PATH does not falsely report
    tmux/tmuxp as MISSING.
    """
    print(f"{_C_DIM}── b tmux save diagnostics ──{_C_RESET}", flush=True)
    print(f"tmux:        {_tool_version('tmux')}", flush=True)
    print(f"tmuxp:       {_tool_version('tmuxp')}", flush=True)
    print(f"TMUX={os.environ.get('TMUX', 'unset')}", flush=True)
    print(f"TMUX_PANE={os.environ.get('TMUX_PANE', 'unset')}", flush=True)
    print(f"pane-id hint:    {pane_id_hint or '(none)'}", flush=True)
    print(f"session-id hint: {session_id_hint or '(none)'}", flush=True)
    print(f"PWD={os.getcwd()}", flush=True)
    print(f"{_C_DIM}─────────────────────────────{_C_RESET}", flush=True)


def cmd_tmux_save(
    base_dir: Path,
    dir_path: str = ".",
    output: str = "",
    to_stdout: bool = False,
    debug: bool = False,
    pane_id_hint: str = "",
    session_id_hint: str = "",
    *,
    pause: bool = False,
    tmux_list_sessions: Callable[[], list[dict[str, str]]],
    tmux_resolve_session_window: Callable[[str, str], tuple[dict[str, str], dict[str, str]]],
    tmux_list_panes: Callable[[str], list[dict[str, str]]],
    resolve_project_root_from_panes: Callable[[list[str], Path], tuple[Path, dict[str, object]]],
    pane_best_run_command_debug: Callable[[dict[str, str]], dict[str, object]],
    tmux_display: Callable[[str], str],
    tmux_save_debug_snapshot: Callable[[list[dict[str, str]]], list[dict[str, object]]],
    resolve_tmux_save_output: Callable[[str, Path], Path],
    tmux_notify: Callable[[str, str, int], None],
    format_error: Callable[[Exception], str],
) -> int:
    def _step(msg: str) -> None:
        if pause:
            print(f"… {msg}", flush=True)

    if not os.getenv("TMUX"):
        print("not inside a tmux session", file=sys.stderr)
        if pause:
            headline, hint = classify_save_error("not inside a tmux session")
            print_error_banner(headline, hint)
            print_save_diagnostics_header(str(pane_id_hint), str(session_id_hint))
            _wait_for_enter()
            # Exit 0 so the outer shell wrapper does NOT show its own
            # diagnostic block — we already presented everything.
            return 0
        return 1

    try:
        _step("listing tmux sessions")
        sessions = tmux_list_sessions()
        _step("resolving active session + window")
        session, window = tmux_resolve_session_window(str(pane_id_hint), str(session_id_hint))
        wid = window.get("window_id", "")
        _step("listing panes")
        panes = tmux_list_panes(wid)
        if not panes:
            raise RuntimeError("resolved active window has no panes")
        _step(f"found {len(panes)} pane(s); resolving project root")

        pane_start_dirs = [pane.get("pane_current_path", "") for pane in panes]
        project_root, project_debug = resolve_project_root_from_panes(pane_start_dirs, base_dir.resolve())

        pane_objs: list[dict[str, object]] = []
        for pane in panes:
            pane_obj: dict[str, object] = {
                "start_directory": str(pane.get("pane_current_path", "")).strip(),
            }
            cmd_debug = pane_best_run_command_debug(pane)
            cmd = str(cmd_debug.get("selected", "") or "")
            if cmd:
                pane_obj["shell_command"] = [{"cmd": cmd, "enter": True}]
            if debug:
                pane_obj["debug"] = cmd_debug
            pane_objs.append(pane_obj)

        workspace: dict[str, object] = {
            "session_name": session.get("session_name", ""),
            "windows": [
                {
                    "window_name": window.get("window_name", ""),
                    "layout": window.get("window_layout", ""),
                    "panes": pane_objs,
                }
            ],
        }
        if debug:
            workspace["debug"] = {
                "context": {
                    "cwd": str(Path.cwd()),
                    "tmux_env": os.environ.get("TMUX", ""),
                    "tmux_pane_env": os.environ.get("TMUX_PANE", ""),
                    "pane_id_hint": str(pane_id_hint),
                    "session_id_hint": str(session_id_hint),
                    "server_current_session_id": tmux_display("#{session_id}"),
                    "server_current_window_id": tmux_display("#{window_id}"),
                    "resolved_session_id": session.get("session_id", ""),
                    "resolved_session_name": session.get("session_name", ""),
                    "resolved_window_id": window.get("window_id", ""),
                    "resolved_window_name": window.get("window_name", ""),
                    "resolved_project_root": str(project_root),
                },
                "sessions": tmux_save_debug_snapshot(sessions),
                "project_resolution": project_debug,
            }

        text = yaml.safe_dump(workspace, sort_keys=False, allow_unicode=False)
        legacy_output = str(dir_path).strip()
        output_path = resolve_tmux_save_output(
            output or (legacy_output if legacy_output and legacy_output != "." else ""),
            project_root,
        )
        _step(f"writing profile to {output_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(output_path.parent),
            delete=False,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        ) as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(output_path)

        if to_stdout:
            print(text)
        tmux_notify(f"b tmux save: saved {output_path}", str(pane_id_hint), 4000)
        if pause:
            print("")
            print(f"✓ saved profile: {output_path}")
            print(f"  session: {session.get('session_name', '')}, "
                  f"window: {window.get('window_name', '')}, "
                  f"panes: {len(panes)}")
            print("")
            print("Take a look at the file before committing — pane")
            print("commands are best-effort and may need a tweak.")
            _wait_for_enter()
        return 0
    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        RuntimeError,
        yaml.YAMLError,
    ) as exc:
        detail = format_error(exc)
        if pause:
            # Skip tmux_notify in popup mode — the popup is showing the
            # error in detail and the status-bar notify call can block
            # for 1-2s before the banner becomes visible.
            headline, hint = classify_save_error(detail, base_root=base_dir.resolve())
            print_error_banner(headline, hint)
            print_save_diagnostics_header(str(pane_id_hint), str(session_id_hint))
            _wait_for_enter()
            # Exit 0 so the shell wrapper does NOT show its own banner.
            return 0
        print(f"b tmux save failed: {detail}", file=sys.stderr)
        tmux_notify(f"b tmux save failed: {detail}", str(pane_id_hint), 6000)
        return 1
    except Exception as exc:  # noqa: BLE001 - top-level error boundary for the tmux key binding
        # The binding runs detached from any visible terminal; a bare
        # traceback to stderr is invisible.
        import traceback

        traceback.print_exc(file=sys.stderr)
        if pause:
            # Skip the status-bar notify — popup is showing it all.
            print_error_banner(
                f"unhandled crash: {type(exc).__name__}",
                f"{exc}\nfull traceback printed above; please report this.",
            )
            print_save_diagnostics_header(str(pane_id_hint), str(session_id_hint))
            _wait_for_enter()
            return 0
        tmux_notify(
            f"b tmux save crashed: {type(exc).__name__}: {exc}",
            str(pane_id_hint),
            8000,
        )
        return 1
