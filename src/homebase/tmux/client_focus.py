from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable


def focus_tmux_client_app(tmux: Callable[..., str]) -> None:
    if sys.platform != "darwin":
        return
    try:
        raw_pid = tmux("display-message", "-p", "#{client_pid}").strip()
        pid = int(raw_pid)
    except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
        return
    ancestry = _process_ancestry(pid)
    app_bundle = _macos_app_bundle_for_ancestry(ancestry)
    if app_bundle is not None and _open_macos_app(app_bundle):
        return
    _focus_macos_app_processes([candidate_pid for candidate_pid, _ in ancestry])


def _process_ancestry(pid: int) -> list[tuple[int, str]]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,comm="],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except OSError:
        return [(pid, "")]
    if proc.returncode != 0:
        return [(pid, "")]
    processes: dict[int, tuple[int, str]] = {}
    for line in proc.stdout.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 2:
            continue
        try:
            process_id = int(parts[0])
            parent_id = int(parts[1])
        except ValueError:
            continue
        command = parts[2] if len(parts) == 3 else ""
        processes[process_id] = (parent_id, command)
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        seen.add(current)
        parent, command = processes.get(current, (1, ""))
        out.append((current, command))
        current = parent
    return out


def _macos_app_bundle_for_ancestry(
    ancestry: list[tuple[int, str]],
) -> Path | None:
    for _pid, command in reversed(ancestry):
        parts = Path(command).parts
        for index, part in enumerate(parts):
            if part.endswith(".app"):
                return Path(*parts[: index + 1])
    return None


def _open_macos_app(app_bundle: Path) -> bool:
    app_path = str(app_bundle).replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "{app_path}" to activate'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _focus_macos_app_processes(pids: list[int]) -> bool:
    if not pids:
        return False
    pid_list = ", ".join(str(pid) for pid in pids)
    script = (
        f"set candidatePids to {{{pid_list}}}\n"
        'tell application "System Events"\n'
        "  repeat with candidatePid in candidatePids\n"
        "    set matches to application processes whose unix id is "
        "(candidatePid as integer)\n"
        "    if (count of matches) > 0 then\n"
        "      set frontmost of item 1 of matches to true\n"
        "      return true\n"
        "    end if\n"
        "  end repeat\n"
        "end tell\n"
        "return false"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"
