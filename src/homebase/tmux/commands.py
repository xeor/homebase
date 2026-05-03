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
    rows: list[Any] = []
    target_res = target.resolve()
    for line in out.splitlines():
        parts = line.split("\t", 5)
        if len(parts) != 6:
            continue
        pane_id, target_text, window_name, command, cwd_text, active_raw = parts
        try:
            cwd = Path(cwd_text).resolve()
        except (OSError, ValueError):
            continue
        if cwd == target_res or is_under(cwd, target_res):
            rows.append(
                pane_ref_factory(
                    pane_id=pane_id.strip(),
                    target=target_text.strip(),
                    window_name=window_name.strip(),
                    command=command.strip(),
                    cwd=cwd,
                    active=(active_raw.strip() == "1"),
                )
            )
    rows.sort(key=lambda pane: (0 if pane.active else 1, pane.target, pane.pane_id))
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

    if not os.getenv("TMUX"):
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


def cmd_tmux_save(
    base_dir: Path,
    dir_path: str = ".",
    output: str = "",
    to_stdout: bool = False,
    debug: bool = False,
    pane_id_hint: str = "",
    session_id_hint: str = "",
    *,
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
    if not os.getenv("TMUX"):
        print("not inside a tmux session", file=sys.stderr)
        return 1

    try:
        sessions = tmux_list_sessions()
        session, window = tmux_resolve_session_window(str(pane_id_hint), str(session_id_hint))
        wid = window.get("window_id", "")
        panes = tmux_list_panes(wid)
        if not panes:
            raise RuntimeError("resolved active window has no panes")

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
        return 0
    except (
        subprocess.SubprocessError,
        OSError,
        ValueError,
        RuntimeError,
        yaml.YAMLError,
    ) as exc:
        detail = format_error(exc)
        print(f"b tmux save failed: {detail}", file=sys.stderr)
        tmux_notify(f"b tmux save failed: {detail}", str(pane_id_hint), 6000)
        return 1
