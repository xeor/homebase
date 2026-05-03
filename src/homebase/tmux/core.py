from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Callable


def tmux_socket_path_from_env() -> str:
    raw = os.environ.get("TMUX", "").strip()
    if not raw:
        return ""
    return raw.split(",", 1)[0].strip()


def resolve_tmux_bin(tmux_bin_candidates: tuple[str, ...]) -> str:
    env_tmux = os.environ.get("TMUX_BIN", "").strip()
    if env_tmux:
        p = Path(env_tmux)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    found = shutil.which("tmux")
    if found:
        return found
    for candidate in tmux_bin_candidates:
        p = Path(candidate)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return "tmux"


def tmux_command_prefix(*, resolve_tmux_bin: Callable[[], str]) -> list[str]:
    cmd = [resolve_tmux_bin()]
    socket_path = tmux_socket_path_from_env()
    if socket_path:
        cmd += ["-S", socket_path]
    return cmd


def tmux_parse_rows(raw: str, fields: int) -> list[list[str]]:
    out: list[list[str]] = []
    for line in str(raw).splitlines():
        parts = line.split("\t")
        if len(parts) != fields:
            continue
        out.append([str(p).strip() for p in parts])
    return out


def tmux_display(
    value: str,
    *,
    tmux: Callable[..., str],
    target: str = "",
) -> str:
    args = ["display-message", "-p"]
    if target:
        args += ["-t", target]
    args.append(value)
    try:
        return tmux(*args)
    except (subprocess.SubprocessError, OSError, ValueError, RuntimeError):
        return ""


def tmux_notify(
    message: str,
    *,
    tmux_command_prefix: Callable[[], list[str]],
    pane_id: str = "",
    delay_ms: int = 4000,
) -> None:
    msg = str(message).strip()
    if not msg:
        return
    base = tmux_command_prefix() + ["display-message", "-d", str(delay_ms)]
    target = str(pane_id).strip()
    try:
        if target:
            proc = subprocess.run(base + ["-t", target, msg], check=False)
            if proc.returncode == 0:
                return
        _ = subprocess.run(base + [msg], check=False)
    except (subprocess.SubprocessError, OSError, ValueError, RuntimeError):
        return


def tmux_list_sessions(*, tmux: Callable[..., str]) -> list[dict[str, str]]:
    raw = tmux(
        "list-sessions",
        "-F",
        "#{session_id}\t#{session_name}\t#{session_activity}\t#{session_attached}",
    )
    out: list[dict[str, str]] = []
    for sid, name, activity, attached in tmux_parse_rows(raw, 4):
        out.append(
            {
                "session_id": sid,
                "session_name": name,
                "session_activity": activity,
                "session_attached": attached,
            }
        )
    return out


def tmux_list_windows(session_id: str, *, tmux: Callable[..., str]) -> list[dict[str, str]]:
    raw = tmux(
        "list-windows",
        "-t",
        session_id,
        "-F",
        "#{window_id}\t#{window_name}\t#{window_layout}\t#{window_active}",
    )
    out: list[dict[str, str]] = []
    for wid, name, layout, active in tmux_parse_rows(raw, 4):
        out.append(
            {
                "window_id": wid,
                "window_name": name,
                "window_layout": layout,
                "window_active": active,
            }
        )
    return out


def tmux_list_panes(window_id: str, *, tmux: Callable[..., str]) -> list[dict[str, str]]:
    raw = tmux(
        "list-panes",
        "-t",
        window_id,
        "-F",
        "#{pane_id}\t#{pane_pid}\t#{pane_tty}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_active}",
    )
    out: list[dict[str, str]] = []
    for pid, pane_pid, tty, cmd, cwd, active in tmux_parse_rows(raw, 6):
        out.append(
            {
                "pane_id": pid,
                "pane_pid": pane_pid,
                "pane_tty": tty,
                "pane_current_command": cmd,
                "pane_current_path": cwd,
                "pane_active": active,
            }
        )
    return out


def tmux_find_window_by_pane_id(
    pane_id: str,
    *,
    tmux: Callable[..., str],
) -> tuple[str, str] | None:
    raw = tmux("list-panes", "-a", "-F", "#{pane_id}\t#{session_id}\t#{window_id}")
    for pid, sid, wid in tmux_parse_rows(raw, 3):
        if pid == pane_id:
            return sid, wid
    return None


def tmux_session_activity(session: dict[str, str]) -> int:
    try:
        return int(session.get("session_activity", "0") or "0")
    except (TypeError, ValueError):
        return 0


def tmux_active_window_in_session(
    session_id: str,
    *,
    tmux_list_windows: Callable[[str], list[dict[str, str]]],
    tmux_display: Callable[[str, str], str],
) -> dict[str, str]:
    windows = tmux_list_windows(session_id)
    if not windows:
        raise RuntimeError(f"session has no windows: {session_id}")
    active_window_id = tmux_display("#{window_id}", session_id)
    if active_window_id:
        for w in windows:
            if w.get("window_id", "") == active_window_id:
                return w
    for w in windows:
        if w.get("window_active", "") == "1":
            return w
    return windows[0]


def tmux_resolve_session_window(
    *,
    pane_id_hint: str,
    session_id_hint: str,
    tmux_list_sessions: Callable[[], list[dict[str, str]]],
    tmux_find_window_by_pane_id: Callable[[str], tuple[str, str] | None],
    tmux_list_windows: Callable[[str], list[dict[str, str]]],
    tmux_active_window_in_session: Callable[[str], dict[str, str]],
    tmux_display: Callable[[str, str], str],
) -> tuple[dict[str, str], dict[str, str]]:
    sessions = tmux_list_sessions()
    if not sessions:
        raise RuntimeError("no tmux sessions found")

    pane_id = str(pane_id_hint).strip() or os.environ.get("TMUX_PANE", "").strip()
    if pane_id:
        located = tmux_find_window_by_pane_id(pane_id)
        if located is not None:
            sid, wid = located
            session = next((s for s in sessions if s.get("session_id", "") == sid), None)
            if session is not None:
                window = next((w for w in tmux_list_windows(sid) if w.get("window_id", "") == wid), None)
                if window is not None:
                    return session, window

    hinted_sid = str(session_id_hint).strip()
    if hinted_sid:
        session = next((s for s in sessions if s.get("session_id", "") == hinted_sid), None)
        if session is not None:
            return session, tmux_active_window_in_session(hinted_sid)

    current_sid = tmux_display("#{session_id}", "")
    current_wid = tmux_display("#{window_id}", "")
    if current_sid and current_wid:
        session = next((s for s in sessions if s.get("session_id", "") == current_sid), None)
        if session is not None:
            window = next((w for w in tmux_list_windows(current_sid) if w.get("window_id", "") == current_wid), None)
            if window is not None:
                return session, window

    if len(sessions) == 1:
        session = sessions[0]
        return session, tmux_active_window_in_session(session.get("session_id", ""))

    ranked = sorted(
        sessions,
        key=lambda s: (tmux_session_activity(s), str(s.get("session_name", ""))),
        reverse=True,
    )
    if ranked and tmux_session_activity(ranked[0]) > 0:
        session = ranked[0]
        return session, tmux_active_window_in_session(session.get("session_id", ""))

    main_session = next((s for s in sessions if s.get("session_name", "") == "main"), None)
    if main_session is not None:
        return main_session, tmux_active_window_in_session(main_session.get("session_id", ""))

    names = ", ".join(str(s.get("session_name", "")) for s in sessions)
    raise RuntimeError(
        f"unable to resolve tmux session/window; no active session signal and no 'main' session; sessions={names}"
    )


def first_token_basename(cmdline: str) -> str:
    text = str(cmdline).strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text)
    except ValueError:
        parts = text.split()
    if not parts:
        return ""
    return Path(parts[0]).name.lower()


def tty_process_rows(tty: str) -> list[tuple[int, int, int, int, str]]:
    t = str(tty).strip()
    if not t:
        return []
    if t.startswith("/dev/"):
        t = t[5:]
    proc = subprocess.run(
        ["ps", "-t", t, "-o", "pid=,ppid=,pgid=,tpgid=,command="],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    rows: list[tuple[int, int, int, int, str]] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(.+)$", line)
        if m is None:
            continue
        try:
            pid = int(m.group(1))
            ppid = int(m.group(2))
            pgid = int(m.group(3))
            tpgid = int(m.group(4))
        except ValueError:
            continue
        cmdline = m.group(5).strip()
        if not cmdline:
            continue
        rows.append((pid, ppid, pgid, tpgid, cmdline))
    return rows


def is_descendant_pid(pid: int, ancestor: int, parent_by_pid: dict[int, int]) -> bool:
    if pid <= 0 or ancestor <= 0:
        return False
    seen: set[int] = set()
    cur = pid
    while cur > 1 and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        cur = int(parent_by_pid.get(cur, 0))
    return False


def pid_command_line(pid: int) -> str:
    if pid <= 0:
        return ""
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return str(proc.stdout).strip()


def pane_best_run_command_debug(
    pane: dict[str, str],
    *,
    shell_commands: set[str],
) -> dict[str, object]:
    pane_pid_text = pane.get("pane_pid", "")
    try:
        pane_pid = int(pane_pid_text or "0")
    except (TypeError, ValueError):
        pane_pid = 0
    tty = pane.get("pane_tty", "")
    rows = tty_process_rows(tty)
    pane_current_command = pane.get("pane_current_command", "")
    current_name = Path(str(pane_current_command or "")).name.lower()
    debug: dict[str, object] = {
        "pane_id": pane.get("pane_id", ""),
        "pane_pid": pane_pid,
        "pane_tty": tty,
        "pane_current_command": pane_current_command,
        "current_name": current_name,
        "selected": "",
        "candidates": [],
    }
    if not current_name or current_name in shell_commands:
        debug["reason"] = "current command is shell"
        return debug

    if rows:
        parent_by_pid = {pid: ppid for pid, ppid, _pgid, _tpgid, _cmd in rows}
        scored: list[tuple[tuple[int, int, int, int], str]] = []
        scored_debug: list[dict[str, object]] = []
        for pid, _ppid, pgid, tpgid, cmdline in rows:
            name = first_token_basename(cmdline)
            if not name or name in shell_commands:
                continue
            text = str(cmdline).strip()
            if not text:
                continue
            foreground = 1 if (tpgid > 0 and pgid == tpgid) else 0
            descendant = 1 if is_descendant_pid(pid, pane_pid, parent_by_pid) else 0
            cmd_match = 1 if (current_name and name == current_name) else 0
            length = len(text)
            scored.append(((cmd_match, foreground, descendant, length), text))
            scored_debug.append(
                {
                    "pid": pid,
                    "name": name,
                    "command": text,
                    "score": {
                        "cmd_match": cmd_match,
                        "foreground": foreground,
                        "descendant": descendant,
                        "length": length,
                    },
                }
            )
        debug["candidates"] = scored_debug
        if scored:
            scored.sort(key=lambda x: x[0], reverse=True)
            debug["selected"] = scored[0][1]
            debug["reason"] = "best scored tty candidate"
            return debug

    line = pid_command_line(pane_pid)
    if line and first_token_basename(line) == current_name:
        debug["selected"] = line
        debug["reason"] = "pane pid command line fallback"
        return debug

    debug["selected"] = current_name
    debug["reason"] = "current command name fallback"
    return debug


def resolve_project_root_from_panes(
    pane_start_dirs: list[str],
    base_root: Path,
    *,
    is_under: Callable[[Path, Path], bool],
    find_marker_root_upward: Callable[[Path], Path | None],
) -> tuple[Path, dict[str, object]]:
    unique_dirs = [d for d in dict.fromkeys(str(x).strip() for x in pane_start_dirs) if d]
    if not unique_dirs:
        raise RuntimeError("no pane start directories found in active window")
    inspected: list[dict[str, str]] = []
    under_base_count = 0
    roots_by_dir: dict[str, str] = {}
    for raw in unique_dirs:
        start_dir = Path(raw).expanduser().resolve(strict=False)
        start_dir_text = str(start_dir)
        if not is_under(start_dir, base_root):
            inspected.append({"start_directory": start_dir_text, "status": "outside_base_root"})
            continue
        under_base_count += 1
        marker_root = find_marker_root_upward(start_dir)
        if marker_root is None or not is_under(marker_root, base_root):
            inspected.append({"start_directory": start_dir_text, "status": "no_project_root"})
            continue
        root_text = str(marker_root)
        roots_by_dir[start_dir_text] = root_text
        inspected.append({"start_directory": start_dir_text, "status": "ok", "project_root": root_text})

    if under_base_count == 0:
        raise RuntimeError(f"no pane start directories under base root: {base_root}")
    unique_roots = sorted(set(roots_by_dir.values()))
    if not unique_roots:
        raise RuntimeError(f"no project root found in active window under base root: {base_root}")
    if len(unique_roots) != 1:
        joined = ", ".join(unique_roots)
        raise RuntimeError(f"multiple project roots in active window: {joined}")
    return Path(unique_roots[0]), {
        "base_root": str(base_root),
        "inspected_start_directories": inspected,
        "resolved_project_root": unique_roots[0],
    }


def resolve_tmux_save_output(raw_output: str, project_root: Path) -> Path:
    text = str(raw_output).strip()
    if not text:
        return project_root / ".tmuxp.yaml"
    path = Path(text).expanduser().resolve(strict=False)
    if path.is_dir():
        return path / ".tmuxp.yaml"
    return path


def format_error(exc: Exception) -> str:
    msg = str(exc).strip()
    name = type(exc).__name__
    if msg:
        return f"{name}: {msg}"
    details: list[str] = []
    for attr in ("stderr", "stdout", "cmd", "returncode"):
        value = getattr(exc, attr, None)
        if value:
            details.append(f"{attr}={value!r}")
    if details:
        return f"{name}: {', '.join(details)}"
    if getattr(exc, "args", None):
        return f"{name}: args={exc.args!r}"
    return f"{name}: {exc!r}"
