from __future__ import annotations

import platform
import subprocess
import sys
import time
from functools import partial
from pathlib import Path
from typing import Callable

from ..core.setup_model import MainThreadActivator, SetupDebugOption, SetupDebugTool
from . import client_focus
from .external import resolve_external_tmux_target
from .registry import load_tmux_contexts

TmuxFn = Callable[..., str]

_TMUX_ERRORS = (subprocess.SubprocessError, OSError, RuntimeError, ValueError)

# method id -> human label, shown in the option list and report headers.
_FOCUS_METHODS: dict[str, str] = {
    "auto": "Auto-detect",
    "appkit": "Force: AppKit (pyobjc)",
    "osascript": "Force: osascript activate",
    "system_events": "Force: System Events",
}


def build_focus_debug_tools(
    base_dir: Path, activator: MainThreadActivator | None = None
) -> list[SetupDebugTool]:
    """Diagnostics for the "select a project, focus the tmux terminal
    window" flow. Each tool returns a Rich-markup report.

    ``activator`` lets the AppKit activation run on the process main
    thread (the same context as live `b`); without it the call runs
    inline on the worker thread and pays the ~1s off-main-thread
    activation penalty."""
    activator = activator or MainThreadActivator()
    return [
        SetupDebugTool(
            id="focus_switch",
            label="Focus / switch tmux terminal",
            description=(
                "Activate the terminal window running the tmux session "
                "`b open` would target, and time only the activation call. "
                "Pick auto-detect (the info panel shows which backend it "
                "will use) or force a specific backend to compare."
            ),
            options=tuple(
                SetupDebugOption(
                    id=method,
                    label=label,
                    run=partial(_run_focus, base_dir, method, activator),
                )
                for method, label in _FOCUS_METHODS.items()
            ),
            detail=lambda: _focus_detail(base_dir),
        ),
        SetupDebugTool(
            id="list_clients",
            label="List tmux sessions + clients",
            description=(
                "Every session and attached client across all known "
                "sockets. Multiple clients are the usual reason the wrong "
                "terminal window gets focused."
            ),
            run=lambda: _report_clients(base_dir),
        ),
        SetupDebugTool(
            id="macos_perms",
            label="Probe macOS focus backends",
            description=(
                "Check the pyobjc fast path and whether osascript is "
                "allowed to drive System Events (Accessibility / "
                "Automation TCC permissions)."
            ),
            run=_report_macos_backends,
        ),
    ]


# --- helpers ---------------------------------------------------------


def _esc(text: object) -> str:
    from rich.markup import escape

    return escape(str(text))


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _run_osascript(script: str, *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _pyobjc_status() -> tuple[bool, str]:
    try:
        from AppKit import NSRunningApplication  # noqa: F401
    except ImportError as exc:
        return False, f"not importable ({exc})"
    return True, "available"


# activationPolicy() values; accessory/prohibited apps cannot be made
# frontmost the normal way, which is a common reason activation "succeeds"
# but the window never comes forward.
_ACTIVATION_POLICY_NAMES = {
    0: "regular (0) — normal app, can take focus",
    1: "accessory (1) — agent/UIElement, won't normally take focus",
    2: "prohibited (2) — background only, cannot take focus",
}


def _activation_policy_name(policy: int) -> str:
    return _ACTIVATION_POLICY_NAMES.get(int(policy), f"unknown ({policy})")


def _appkit_app_desc(app: object) -> str:
    """One-line ``name (pid, bundle)`` for an ``NSRunningApplication``."""
    if app is None:
        return "<none>"
    return (
        f"{app.localizedName() or '<unnamed>'} "
        f"(pid {app.processIdentifier()}, {app.bundleIdentifier() or '<no bundle>'})"
    )


def _appkit_frontmost_name() -> str:
    try:
        from AppKit import NSWorkspace
    except ImportError as exc:
        return f"<pyobjc not installed: {exc}>"
    return _appkit_app_desc(NSWorkspace.sharedWorkspace().frontmostApplication())


def _appkit_diagnostics(
    running: object,
    app_pid: int,
    active_before: bool,
    activate_returned: bool,
    ns_workspace: object,
) -> list[str]:
    """State of the target app and the workspace right after an AppKit
    activation attempt. Pinpoints the case where ``activateWithOptions_``
    reports success but the app never becomes frontmost (TCC / Spaces /
    activation-policy issues, or another app holding activation)."""
    running_pid = int(running.processIdentifier())
    pid_note = "" if running_pid == app_pid else f"  [!= detected {app_pid}]"
    workspace = ns_workspace.sharedWorkspace()
    lines = [
        f"activate returned:  {activate_returned}",
        f"bundle id:          {running.bundleIdentifier() or '<none>'}",
        f"localized name:     {running.localizedName() or '<none>'}",
        f"running pid:        {running_pid}{pid_note}",
        f"activation policy:  {_activation_policy_name(running.activationPolicy())}",
        f"finished launching: {bool(running.isFinishedLaunching())}",
        f"terminated:         {bool(running.isTerminated())}",
        f"hidden:             {bool(running.isHidden())}",
        f"owns menu bar:      {bool(running.ownsMenuBar())}",
        f"isActive before:    {active_before}",
        f"isActive after:     {bool(running.isActive())}",
        f"workspace frontmost: {_appkit_app_desc(workspace.frontmostApplication())}",
        f"workspace menubar:   {_appkit_app_desc(workspace.menuBarOwningApplication())}",
    ]
    return lines


# --- focus / switch: one tool, selectable backend -------------------


def _focus_detail(base_dir: Path) -> str:
    """Live one-liner for the info panel: what auto-detect resolves to
    for the current target right now, plus the detected app."""
    ctx = _resolve_focus_context(base_dir)
    if isinstance(ctx, str):
        return f"[bright_yellow]auto-detect: unavailable — {_esc(ctx)}[/]"
    session, _client_pid_val, _ancestry, app = ctx
    method, why = _auto_method(app)
    app_bundle = app[1] if app is not None else None
    return (
        f"[bold]auto-detect will use:[/] "
        f"{_esc(_FOCUS_METHODS.get(method, method))} [dim]({why})[/]\n"
        f"target session: {_esc(session)}   "
        f"app: {_esc(app_bundle) if app_bundle is not None else '<none>'}"
    )


def _resolve_focus_context(
    base_dir: Path,
) -> tuple[str, int, list[tuple[int, str]], tuple[int, Path] | None] | str:
    """(session, client_pid, ancestry, app) for the targeted tmux, or an
    error string when nothing can be resolved."""
    resolved = resolve_external_tmux_target(base_dir, quiet=True)
    if resolved is None:
        return "could not resolve a single tmux target (none or ambiguous)."
    _context, _prefix, tmux_fn, session = resolved
    client_pid = _client_pid(tmux_fn)
    if client_pid is None:
        return "no client_pid; no client attached to the target session."
    ancestry = client_focus.process_ancestry(client_pid)
    app = client_focus.macos_app_for_client_pid(client_pid)
    return session, client_pid, ancestry, app


def _auto_method(app: tuple[int, Path] | None) -> tuple[str, str]:
    if sys.platform != "darwin":
        return "auto", "not darwin; activation unavailable"
    if app is not None:
        if _pyobjc_status()[0]:
            return "appkit", "pyobjc installed, .app detected"
        return "osascript", "no pyobjc, .app detected"
    return "system_events", "no .app in ancestry"


def _run_focus(base_dir: Path, method: str, activator: MainThreadActivator) -> str:
    label = _FOCUS_METHODS.get(method, method)
    lines: list[str] = [
        f"[bold]Focus / switch tmux terminal — {_esc(label)}[/]",
        "",
        f"platform: {_esc(sys.platform)}",
    ]
    if sys.platform == "darwin":
        lines.append(f"macOS:    {_esc(platform.mac_ver()[0] or '<unknown>')}")

    ctx = _resolve_focus_context(base_dir)
    if isinstance(ctx, str):
        lines.append(f"[bright_red]{_esc(ctx)}[/]")
        return "\n".join(lines)
    session, client_pid, ancestry, app = ctx
    app_pid = app[0] if app is not None else None
    app_bundle = app[1] if app is not None else None
    lines.append(f"target session: {_esc(session)}")
    lines.append(f"client_pid:     {client_pid}")
    lines.append(
        "detected app:   "
        f"{_esc(app_bundle) if app_bundle is not None else '<none>'}"
        f"{f' (pid {app_pid})' if app_pid is not None else ''}"
    )

    chosen = method
    if method == "auto":
        chosen, why = _auto_method(app)
        lines.append(
            f"auto-detect ->  [bold]{_esc(_FOCUS_METHODS.get(chosen, chosen))}[/] "
            f"[dim]({why})[/]"
        )

    lines.append("")
    if sys.platform != "darwin":
        lines.append("[dim]window activation is darwin-only; not attempting here.[/]")
        return "\n".join(lines)

    ok, detail, elapsed = _activate_with(
        chosen, app_pid, app_bundle, ancestry, activator
    )
    lines.append(f"[bold]{_esc(chosen)}[/]: {_ok(ok)}   [bold]{_ms(elapsed)}[/]")
    if detail:
        for detail_line in detail.splitlines():
            lines.append(f"  {_esc(detail_line)}")

    lines.append("")
    lines.append("[bold]frontmost after (System Events):[/] " + _esc(_frontmost_app_name()))
    lines.append("[bold]frontmost after (AppKit):[/] " + _esc(_appkit_frontmost_name()))
    lines.append(
        "[dim]timing is the activation call only; the visible switch completes "
        "asynchronously after it returns. osascript backends spawn a process "
        "and compile AppleScript, so they run ~10-50x slower than AppKit.[/]"
    )
    return "\n".join(lines)


def _activate_with(
    method: str,
    app_pid: int | None,
    app_bundle: Path | None,
    ancestry: list[tuple[int, str]],
    activator: MainThreadActivator,
) -> tuple[bool, str, float]:
    """Run one activation backend, timing only the call itself. Returns
    (ok, detail, elapsed_seconds)."""
    if method == "appkit":
        try:
            from AppKit import (
                NSApplicationActivateIgnoringOtherApps,
                NSRunningApplication,
                NSWorkspace,
            )
        except ImportError as exc:
            return (
                False,
                f"pyobjc is NOT installed — fast path unavailable ({exc})",
                0.0,
            )
        if app_pid is None:
            return False, "no app pid (no .app in ancestry)", 0.0
        running = NSRunningApplication.runningApplicationWithProcessIdentifier_(app_pid)
        if running is None:
            return False, f"no running application for pid {app_pid}", 0.0

        active_before = bool(running.isActive())

        def _activate() -> tuple[bool, float]:
            # Must run on the main thread; off it this call blocks ~1s.
            start = time.perf_counter()
            ok = bool(
                running.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            )
            return ok, time.perf_counter() - start

        ok, elapsed = activator.run(_activate)
        detail = "\n".join(
            _appkit_diagnostics(running, app_pid, active_before, ok, NSWorkspace)
        )
        return ok, detail, elapsed
    if method == "osascript":
        if app_bundle is None:
            return False, "no app bundle (no .app in ancestry)", 0.0
        start = time.perf_counter()
        ok, detail = _osascript_activate_bundle(app_bundle)
        return ok, detail, time.perf_counter() - start
    if method == "system_events":
        pids = [pid for pid, _ in ancestry]
        start = time.perf_counter()
        ok, detail = _osascript_system_events_focus(pids)
        return ok, detail or f"pids {pids}", time.perf_counter() - start
    return False, f"unknown method {method!r}", 0.0


def _ok(value: bool) -> str:
    return "[bright_green]ok[/]" if value else "[bright_red]failed[/]"


def _osascript_activate_bundle(app_bundle: Path) -> tuple[bool, str]:
    app_path = str(app_bundle).replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "{app_path}" to activate'
    try:
        proc = _run_osascript(script, timeout=3.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return proc.returncode == 0, proc.stderr.strip()


def _osascript_system_events_focus(pids: list[int]) -> tuple[bool, str]:
    if not pids:
        return False, "no candidate pids"
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
        proc = _run_osascript(script, timeout=3.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    ok = proc.returncode == 0 and proc.stdout.strip().lower() == "true"
    return ok, proc.stderr.strip()


def _frontmost_app_name() -> str:
    if sys.platform != "darwin":
        return "<n/a>"
    script = (
        'tell application "System Events" to get name of first application '
        "process whose frontmost is true"
    )
    try:
        proc = _run_osascript(script, timeout=3.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"<probe failed: {type(exc).__name__}>"
    if proc.returncode != 0:
        return f"<probe failed: {proc.stderr.strip() or 'osascript error'}>"
    return proc.stdout.strip() or "<unknown>"


# --- report: clients -------------------------------------------------


def _report_clients(base_dir: Path) -> str:
    lines: list[str] = ["[bold]tmux sessions + clients[/]", ""]
    sockets = _known_sockets(base_dir)
    if not sockets:
        lines.append("[bright_yellow]no tmux sockets found.[/]")
        lines.append(
            "Either no tmux is running, or no homebase tmux context was "
            "registered (open a project via `b` from inside the tmux first)."
        )
        return "\n".join(lines)

    resolved = resolve_external_tmux_target(base_dir, quiet=True)
    target_session = resolved[3] if resolved is not None else None

    for socket_path in sockets:
        lines.append(f"[bold]socket:[/] {_esc(socket_path or '<default>')}")
        tmux_fn = _socket_tmux_fn(socket_path)
        lines.extend(_sessions_block(tmux_fn, target_session))
        lines.extend(_clients_block(tmux_fn))
        lines.append("")
    if target_session is not None:
        lines.append(f"[dim]`b open` would target session: {_esc(target_session)}[/]")
    else:
        lines.append(
            "[bright_yellow]`b open` could not resolve a single target "
            "session (none or ambiguous).[/]"
        )
    return "\n".join(lines)


def _sessions_block(tmux_fn: TmuxFn, target_session: str | None) -> list[str]:
    try:
        raw = tmux_fn(
            "list-sessions",
            "-F",
            "#{session_id}\t#{session_name}\t#{session_attached}",
        )
    except _TMUX_ERRORS as exc:
        return [f"  [bright_red]list-sessions failed: {_esc(exc)}[/]"]
    rows = [line for line in raw.splitlines() if line.strip()]
    if not rows:
        return ["  [dim](no sessions)[/]"]
    out = ["  sessions:"]
    for row in rows:
        parts = row.split("\t")
        sid = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else ""
        attached = parts[2] if len(parts) > 2 else "?"
        marker = (
            " [bright_green]<- target[/]"
            if target_session in {sid, name} and target_session is not None
            else ""
        )
        out.append(f"    {_esc(sid)} {_esc(name)} (attached={_esc(attached)}){marker}")
    return out


def _clients_block(tmux_fn: TmuxFn) -> list[str]:
    try:
        raw = tmux_fn(
            "list-clients",
            "-F",
            "#{client_name}\t#{client_pid}\t#{client_session}\t"
            "#{client_termname}\t#{client_activity}",
        )
    except _TMUX_ERRORS as exc:
        return [f"  [bright_red]list-clients failed: {_esc(exc)}[/]"]
    rows = [line for line in raw.splitlines() if line.strip()]
    if not rows:
        return ["  [dim](no attached clients)[/]"]
    out = [f"  clients ({len(rows)}):"]
    for row in rows:
        parts = row.split("\t")
        tty = parts[0] if parts else ""
        pid = parts[1] if len(parts) > 1 else ""
        sess = parts[2] if len(parts) > 2 else ""
        term = parts[3] if len(parts) > 3 else ""
        out.append(
            f"    pid={_esc(pid)} tty={_esc(tty)} session={_esc(sess)} "
            f"term={_esc(term)}"
        )
    if len(rows) > 1:
        out.append(
            "  [bright_yellow]more than one client attached[/] — the focus "
            "logic may pick the wrong one."
        )
    return out


# --- report: macOS backends ------------------------------------------


def _report_macos_backends() -> str:
    lines: list[str] = ["[bold]macOS focus backends[/]", ""]
    lines.append(f"platform: {_esc(sys.platform)}")
    if sys.platform != "darwin":
        lines.append("[dim]not darwin; these backends are unused here.[/]")
        return "\n".join(lines)

    pyobjc_ok, pyobjc_detail = _pyobjc_status()
    lines.append("")
    lines.append(f"pyobjc fast path: {_ok(pyobjc_ok)} ({_esc(pyobjc_detail)})")
    if not pyobjc_ok:
        lines.append(
            "  [dim]without pyobjc, activation uses osascript (slower) and "
            "depends on the TCC permissions probed below.[/]"
        )

    lines.append("")
    lines.append("[bold]osascript / System Events (TCC)[/]")
    ok, detail = _system_events_probe()
    lines.append(f"  drive System Events: {_ok(ok)}")
    if detail:
        lines.append(f"    {_esc(detail)}")
    if not ok:
        lines.append(
            "  [bright_yellow]System Events is blocked.[/] Grant the "
            "terminal app (and/or osascript) Automation + Accessibility "
            "access in System Settings > Privacy & Security. Window focus "
            "for non-.app clients depends on this."
        )
    return "\n".join(lines)


def _system_events_probe() -> tuple[bool, str]:
    script = (
        'tell application "System Events" to get name of first application '
        "process whose frontmost is true"
    )
    try:
        proc = _run_osascript(script, timeout=3.0)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "osascript returned non-zero"
    return True, f"frontmost = {proc.stdout.strip() or '<unknown>'}"


# --- socket / tmux plumbing ------------------------------------------


def _known_sockets(base_dir: Path) -> list[str]:
    from .core import tmux_socket_path_from_env

    sockets: list[str] = []
    seen: set[str] = set()
    for context in load_tmux_contexts(base_dir):
        socket_path = str(context.get("socket_path", "")).strip()
        if socket_path and socket_path not in seen:
            seen.add(socket_path)
            sockets.append(socket_path)
    env_socket = tmux_socket_path_from_env()
    if env_socket and env_socket not in seen:
        sockets.append(env_socket)
    elif not sockets:
        # No registered context and no $TMUX: still try the default
        # server so a plain `tmux` session is visible.
        sockets.append("")
    return sockets


def _socket_tmux_fn(socket_path: str) -> TmuxFn:
    from ..core import utils as core_utils
    from ..core.constants import TMUX_BIN_CANDIDATES
    from .core import resolve_tmux_bin

    prefix = [resolve_tmux_bin(TMUX_BIN_CANDIDATES)]
    if socket_path:
        prefix.extend(["-S", socket_path])
    return lambda *args: core_utils.run_out(*prefix, *args)


def _client_pid(tmux_fn: TmuxFn) -> int | None:
    try:
        raw = tmux_fn("display-message", "-p", "#{client_pid}").strip()
    except _TMUX_ERRORS:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
