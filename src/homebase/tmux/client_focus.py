from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from ..core import debug_timers
from ..core.constants import TMUX_FOCUS_METHOD_AUTO
from ..core.debug_timers import timed_step


def _configured_focus_method(base_dir: Path) -> str:
    from ..config import prefs

    return prefs.load_tmux_focus_method(base_dir)


def focus_tmux_client_app(tmux: Callable[..., str], base_dir: Path) -> None:
    if sys.platform != "darwin":
        return
    with timed_step(base_dir, "tmux_focus.client_pid_lookup") as info:
        try:
            raw_pid = tmux("display-message", "-p", "#{client_pid}").strip()
            pid = int(raw_pid)
        except (subprocess.SubprocessError, OSError, RuntimeError, ValueError):
            info["ok"] = False
            return
        info["ok"] = True
        info["pid"] = pid

    with timed_step(base_dir, "tmux_focus.process_ancestry") as info:
        ancestry = _process_ancestry(pid)
        info["chain"] = [command for _pid, command in ancestry]

    app = _macos_app_for_ancestry(ancestry)
    method = _configured_focus_method(base_dir)
    if method == TMUX_FOCUS_METHOD_AUTO:
        _focus_auto(base_dir, app, ancestry)
    else:
        _focus_forced(base_dir, method, app, ancestry)


def _focus_auto(
    base_dir: Path,
    app: tuple[int, Path] | None,
    ancestry: list[tuple[int, str]],
) -> None:
    """Built-in waterfall: AppKit (fastest, optional pyobjc) -> osascript
    activate -> System Events. The first that reports success wins."""
    if app is not None:
        app_pid, app_bundle = app
        with timed_step(base_dir, "tmux_focus.activate_via_appkit", pid=app_pid) as info:
            activated = _activate_via_appkit(app_pid)
            info["ok"] = activated
        if not activated:
            with timed_step(
                base_dir, "tmux_focus.activate_by_bundle", bundle=str(app_bundle)
            ) as info:
                activated = _open_macos_app(app_bundle)
                info["ok"] = activated
        if activated:
            # `activate` returns once the Apple Event is delivered, not
            # once the app is actually visibly frontmost (Space switch /
            # window-manager animation happens after). Only measured in
            # debug mode since it polls for up to a few seconds.
            if debug_timers.enabled:
                with timed_step(
                    base_dir, "tmux_focus.wait_until_frontmost", pid=app_pid
                ) as info:
                    info["ok"] = _wait_until_frontmost(app_pid)
            return

    app_name = app[1].stem if app is not None else None
    with timed_step(base_dir, "tmux_focus.activate_via_system_events") as info:
        ok, method, _detail = system_events_set_frontmost(
            app_name, [candidate_pid for candidate_pid, _ in ancestry]
        )
        info["ok"] = ok
        info["method"] = method


def _focus_forced(
    base_dir: Path,
    method: str,
    app: tuple[int, Path] | None,
    ancestry: list[tuple[int, str]],
) -> None:
    """Run only the backend the user pinned via `tmux_focus.method`. No
    fallback: enforcing a backend means failures stay visible (in debug
    timers) rather than being masked by a different path."""
    app_pid = app[0] if app is not None else None
    app_bundle = app[1] if app is not None else None
    app_name = app[1].stem if app is not None else None
    pids = [candidate_pid for candidate_pid, _ in ancestry]
    if method == "appkit":
        with timed_step(base_dir, "tmux_focus.activate_via_appkit", forced=True) as info:
            info["ok"] = _activate_via_appkit(app_pid) if app_pid is not None else False
    elif method == "osascript":
        with timed_step(
            base_dir, "tmux_focus.activate_by_bundle", forced=True
        ) as info:
            info["ok"] = _open_macos_app(app_bundle) if app_bundle is not None else False
    elif method == "system_events":
        with timed_step(
            base_dir, "tmux_focus.activate_via_system_events", forced=True
        ) as info:
            ok, used, _detail = system_events_set_frontmost(app_name, pids)
            info["ok"] = ok
            info["method"] = used


def process_ancestry(pid: int) -> list[tuple[int, str]]:
    """Public wrapper: ``[(pid, comm), …]`` from ``pid`` up to the
    session root. Used by the setup Debug tab to show why a terminal
    ``.app`` was or wasn't found in the chain."""
    return _process_ancestry(pid)


def macos_app_for_client_pid(pid: int) -> tuple[int, Path] | None:
    """The ``(app_pid, app_bundle)`` that ``focus_tmux_client_app``
    would activate for ``pid``, or ``None`` when no ``.app`` is found
    in the ancestry (the case that silently falls back to System
    Events)."""
    return _macos_app_for_ancestry(_process_ancestry(pid))


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


def _macos_app_for_ancestry(
    ancestry: list[tuple[int, str]],
) -> tuple[int, Path] | None:
    for pid, command in reversed(ancestry):
        parts = Path(command).parts
        for index, part in enumerate(parts):
            if part.endswith(".app"):
                return pid, Path(*parts[: index + 1])
    return None


def _activate_via_appkit(pid: int) -> bool:
    """Fast path: direct Cocoa activation via the optional pyobjc dep.

    No subprocess, no AppleScript compile — roughly an order of
    magnitude faster than ``_open_macos_app`` when it works. Falls
    through (returns False) if pyobjc isn't installed; see ``b setup``
    for the optional install.
    """
    try:
        from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication
    except ImportError:
        return False
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return False
    return bool(app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))


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


def _wait_until_frontmost(pid: int, timeout: float = 3.0) -> bool:
    script = (
        f"set targetPid to {pid}\n"
        f"set deadline to (current date) + {timeout}\n"
        "repeat\n"
        '  tell application "System Events"\n'
        "    set matches to application processes whose unix id is targetPid\n"
        "    if (count of matches) > 0 and frontmost of item 1 of matches then\n"
        "      return true\n"
        "    end if\n"
        "  end tell\n"
        "  if (current date) > deadline then\n"
        "    return false\n"
        "  end if\n"
        "  delay 0.05\n"
        "end repeat"
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout + 1.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


# Compiled NSAppleScript objects keyed by source. Compiling is the
# expensive part of the AppleScript path; `b open` targets the same
# terminal over and over, so the cache turns every call after the first
# into a pure execute.
_COMPILED_APPLESCRIPTS: dict[str, object] = {}


def _foundation_available() -> bool:
    try:
        import Foundation  # noqa: F401
    except ImportError:
        return False
    return True


def _applescript_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _frontmost_by_name_script(name: str) -> str:
    """Target the app by process name — a single lookup, versus the
    full-process AX scan that ``whose unix id is`` forces System Events
    to do."""
    return (
        'tell application "System Events" to set frontmost of '
        f'(first process whose name is "{_applescript_escape(name)}") to true\n'
        "return true"
    )


def _frontmost_by_unix_id_script(pids: list[int]) -> str:
    pid_list = ", ".join(str(pid) for pid in pids)
    return (
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


def _run_applescript_in_process(source: str) -> tuple[bool, str]:
    """Execute AppleScript via a cached ``NSAppleScript`` — no subprocess
    and compiled once per distinct source. Must run on the main thread.
    Both focus scripts return a boolean, so ``(ok, detail)`` reflects the
    script result, not merely "did it run"."""
    from Foundation import NSAppleScript

    script = _COMPILED_APPLESCRIPTS.get(source)
    if script is None:
        script = NSAppleScript.alloc().initWithSource_(source)
        _COMPILED_APPLESCRIPTS[source] = script
    result, error = script.executeAndReturnError_(None)
    if result is None:
        if error is None:
            return False, "AppleScript failed (no result, no error info)"
        message = error.objectForKey_("NSAppleScriptErrorMessage")
        return False, str(message) if message else str(error)
    return bool(result.booleanValue()), ""


def _osascript_unix_id_focus(pids: list[int]) -> tuple[bool, str]:
    if not pids:
        return False, "no candidate pids"
    try:
        proc = subprocess.run(
            ["osascript", "-e", _frontmost_by_unix_id_script(pids)],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=1.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    ok = proc.returncode == 0 and proc.stdout.strip().lower() == "true"
    return ok, proc.stderr.strip()


def system_events_set_frontmost(
    app_name: str | None, pids: list[int]
) -> tuple[bool, str, str]:
    """Bring the target terminal frontmost via System Events — the
    Accessibility proxy that is exempt from focus-stealing prevention,
    which is why this works where Cocoa/`activate` are silently ignored.

    Returns ``(ok, method, detail)``. Order, fastest first: in-process
    ``NSAppleScript`` targeting the app by process name, then in-process
    unix-id matching, then an ``osascript`` subprocess when pyobjc is
    unavailable. The in-process paths must run on the main thread."""
    if not _foundation_available():
        ok, detail = _osascript_unix_id_focus(pids)
        return ok, "osascript:unix_id", detail

    detail = "no target: neither app name nor candidate pids"
    if app_name:
        ok, detail = _run_applescript_in_process(_frontmost_by_name_script(app_name))
        if ok:
            return True, "nsapplescript:name", detail
    if pids:
        ok, detail = _run_applescript_in_process(_frontmost_by_unix_id_script(pids))
        if ok:
            return True, "nsapplescript:unix_id", detail
    return False, "nsapplescript", detail
