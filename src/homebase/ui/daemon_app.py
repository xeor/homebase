"""`b daemon` status screen.

In a terminal, `b daemon` runs its loop in a thread and shows what it does.
A second `b daemon` (one already runs for the base) shows the running one
read-only from its heartbeat file. `--plain`, `--once` or no terminal: log
lines on stdout as before."""
from __future__ import annotations

import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from rich.table import Table
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Log, Static

from ..cache.api import cache_db_path, cache_full_scan_ts, cache_last_refresh_ts
from ..cache.clients import ClientInfo, list_clients
from ..cache.daemon_status import (
    DaemonStatus,
    daemon_lock_path,
    daemon_status_alive,
    read_daemon_status,
)
from ..cache.owner import (
    peek_cache_refresh_request,
    read_cache_owner,
    request_cache_refresh,
    try_flock,
)
from ..commands.daemon import (
    WARM_COLD_S,
    DaemonState,
    cmd_daemon,
    new_daemon_state,
    run_daemon,
    status_of,
)
from ..core.constants import (
    CACHE_MAX_AGE_S,
    DAEMON_SIGNATURE_CHECK_S,
    DAEMON_STARTUP_WARM_S,
    UI_TICK_WORKTREE_HEALTH_S,
)
from ..core.proc_stats import (
    CpuSampler,
    current_rss_bytes,
    other_process_usage,
    peak_rss_bytes,
    process_cpu_s,
)
from ..core.startup_warm import DEFAULT_LIST_PATH
from ..core.utils import fmt_duration, fmt_size_human

# How long quitting waits for a running full scan before leaving it behind.
STOP_WAIT_S = 30.0
# Two columns of panels, left to right, top to bottom.
PANEL_COLUMNS = (("daemon", "cache"), ("process", "startup", "clients"))
PANELS = tuple(name for column in PANEL_COLUMNS for name in column)
PANEL_TITLES = {
    "daemon": "Daemon",
    "process": "Process",
    "cache": "Project cache",
    "startup": "Start-up speed",
    "clients": "Open b windows",
}
SCREEN_TICK_S = 1.0

Section = tuple[str, list[tuple[str, str]]]


@dataclass(frozen=True)
class ProcFacts:
    cpu_pct: float | None = None
    cpu_avg_pct: float | None = None
    rss_bytes: int | None = None
    peak_rss_bytes: int | None = None
    threads: int | None = None


@dataclass(frozen=True)
class CacheFacts:
    full_scan_ts: int
    last_write_ts: int
    db_bytes: int
    pending_request: str | None
    owner: str


def db_bytes(base_dir: Path) -> int:
    db = cache_db_path(base_dir)
    total = 0
    for path in (db, db.with_name(db.name + "-wal")):
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


def gather_cache_facts(base_dir: Path) -> CacheFacts:
    return CacheFacts(
        full_scan_ts=cache_full_scan_ts(base_dir),
        last_write_ts=cache_last_refresh_ts(base_dir),
        db_bytes=db_bytes(base_dir),
        pending_request=peek_cache_refresh_request(base_dir),
        owner=read_cache_owner(base_dir),
    )


def _ago(ts: float, now: float) -> str:
    return "-" if ts <= 0 else f"{fmt_duration(now - ts)} ago"


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def _size(value: int | None) -> str:
    return "-" if value is None else fmt_size_human(value)


def _role(status: DaemonStatus, owner: str) -> str:
    if status.role == "owner":
        return "cache owner"
    if status.role == "waiting":
        return f"waiting for cache owner ({owner or '?'})"
    return status.role or "-"


def _doing(status: DaemonStatus, now: float) -> str:
    if status.activity:
        return f"{status.activity}, {fmt_duration(now - status.activity_since)}"
    return status.state


def _warm_files_text(status: DaemonStatus) -> str:
    if status.warm_listed <= 0:
        return "none read yet"
    size = fmt_size_human(status.warm_bytes)
    if status.warm_files != status.warm_listed:
        return f"{status.warm_files} of {status.warm_listed} listed files, {size}"
    return f"{status.warm_files} files, {size}"


def _warm_last_text(status: DaemonStatus, now: float) -> str:
    if status.warm_runs <= 0:
        return f"not yet, runs every {fmt_duration(DAEMON_STARTUP_WARM_S)}"
    cold = " (cold: it would have been a slow start)" if status.warm_took_s >= WARM_COLD_S else ""
    return f"{_ago(status.warm_ts, now)}, took {status.warm_took_s:.1f}s{cold}"


def _warm_passes_text(status: DaemonStatus) -> str:
    if status.warm_runs <= 0:
        return "none yet"
    return (
        f"{status.warm_runs} done, {status.warm_cold_runs} found the files cold, "
        f"one every {fmt_duration(DAEMON_STARTUP_WARM_S)}"
    )


def _warm_list_text(now: float) -> str:
    """Where the file list comes from: the last `b` TUI start wrote it."""
    path = DEFAULT_LIST_PATH.expanduser()
    try:
        written = path.stat().st_mtime
    except OSError:
        return f"{_short_path(str(path))} (no b TUI has started yet)"
    return f"{_short_path(str(path))}, written {_ago(written, now)}"


def startup_section(status: DaemonStatus | None, now: float) -> Section:
    """What the daemon does to keep the next `b` start fast.

    A TUI start reads ~750 module files, and a virus scanner rescans every one
    of them once they have left the file cache, which is what makes the first
    `b` after an idle period slow. Re-reading them here keeps them cached.
    """
    if status is None:
        return ("Start-up speed", [("files kept warm", "-")])
    rows = [
        ("files kept warm", _warm_files_text(status)),
        ("last warm-up", _warm_last_text(status, now)),
        ("warm-ups", _warm_passes_text(status)),
        ("file list from", _warm_list_text(now)),
        ("this keeps", "b's imports in the file cache, so a new b opens fast"),
    ]
    return ("Start-up speed", rows)


def daemon_section(
    status: DaemonStatus | None, *, main: bool, base_dir: Path, owner: str, now: float
) -> Section:
    if status is None or (not main and not daemon_status_alive(status, now)):
        return ("Daemon", [("daemon running", "no"), ("base directory", str(base_dir))])
    rows = [
        ("this screen", "the running daemon" if main else f"a viewer of pid {status.pid}"),
        ("process id", str(status.pid)),
        ("homebase version", status.version),
        ("base directory", str(base_dir)),
        ("running for", fmt_duration(now - status.started_ts)),
        ("background work", _role(status, owner)),
        ("doing right now", _doing(status, now)),
        ("last heartbeat", _ago(status.heartbeat_ts, now)),
    ]
    return ("Daemon", rows)


def process_section(proc: ProcFacts) -> Section:
    rows = [
        ("cpu right now", _pct(proc.cpu_pct)),
        ("cpu since start", _pct(proc.cpu_avg_pct)),
        ("memory in use", _size(proc.rss_bytes)),
        ("memory high mark", _size(proc.peak_rss_bytes)),
        ("threads running", "-" if proc.threads is None else str(proc.threads)),
    ]
    return ("Process", rows)


def _rows_text(status: DaemonStatus | None) -> str:
    if status is None or status.active_rows < 0:
        return "-"
    return f"{status.active_rows} active, {status.archived_rows} archived"


def _next_scan(cache: CacheFacts, now: float) -> str:
    if cache.full_scan_ts <= 0:
        return "now"
    due = cache.full_scan_ts + CACHE_MAX_AGE_S - now
    return (
        f"max age in {fmt_duration(max(0.0, due))}, "
        f"change check every {fmt_duration(DAEMON_SIGNATURE_CHECK_S)}"
    )


def _health_text(status: DaemonStatus | None, now: float) -> str:
    if status is None or status.health_issues < 0:
        return "not swept yet"
    return (
        f"{status.health_issues} issues, swept {_ago(status.health_ts, now)} "
        f"({status.health_took_s:.1f}s), every {fmt_duration(UI_TICK_WORKTREE_HEALTH_S)}"
    )


def _last_scan_text(status: DaemonStatus | None, now: float) -> str:
    if status is None or not status.refreshes:
        return "-"
    ago = _ago(status.last_refresh_ts, now)
    when = "" if ago == "-" else f", {ago}"
    return f"took {status.last_refresh_s:.1f}s{when} ({status.last_reason or '-'})"


def cache_section(status: DaemonStatus | None, cache: CacheFacts, now: float) -> Section:
    rows = [
        ("projects cached", _rows_text(status)),
        ("database size", fmt_size_human(cache.db_bytes)),
        ("last full scan", _ago(cache.full_scan_ts, now)),
        ("that scan took", _last_scan_text(status, now)),
        ("scans since start", "-" if status is None else str(status.refreshes)),
        ("next full scan", _next_scan(cache, now)),
        ("last cache write", _ago(cache.last_write_ts, now)),
        ("rescan requested by", cache.pending_request or "nobody"),
        ("worktree health", _health_text(status, now)),
    ]
    return ("Project cache", rows)


def _short_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def clients_section(clients: list[ClientInfo], owner: str, now: float) -> Section:
    owner_pid = owner.split(" ", 1)[0]
    rows: list[tuple[str, str]] = [("b windows open", str(len(clients)))]
    for client in clients:
        mark = ", cache owner" if str(client.pid) == owner_pid else ""
        tty = client.tty.removeprefix("/dev/") or "-"
        rows.append(
            (
                f"pid {client.pid}",
                f"{tty}  up {fmt_duration(now - client.started_ts)}{mark}  {_short_path(client.cwd)}",
            )
        )
    return ("Open b windows", rows)


def render_section(section: Section) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    for label, value in section[1]:
        table.add_row(label, value)
    return table


class DaemonApp(App[None]):
    TITLE = "b daemon"
    CSS = """
    #panels { height: auto; }
    #panels > Vertical { width: 1fr; height: auto; }
    .panel { border: round $primary; padding: 0 1; height: auto; }
    /* The column height follows the left one (see _balance_columns) and the
       window list takes whatever the panels above it leave. */
    #clients-panel { height: 1fr; min-height: 3; }
    #log { border: round $primary; height: 1fr; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("r", "rescan", "Rescan now"),
        Binding("w", "health", "Worktree health now"),
    ]

    def __init__(
        self,
        base_dir: Path,
        *,
        st: DaemonState | None,
        stop: threading.Event,
        worker: threading.Thread | None,
    ) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.st = st
        self.stop_event = stop
        self.worker_thread = worker
        self.cpu = CpuSampler()
        self.shown_log_count = 0
        self.shown_recent: tuple[str, ...] = ()
        self.sections: dict[str, Section] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panels"):
            for index, column in enumerate(PANEL_COLUMNS):
                with Vertical(id=f"column{index}"):
                    for name in column:
                        if name == "clients":
                            # More windows than fit: the list scrolls.
                            with VerticalScroll(id="clients-panel", classes="panel"):
                                yield Static(id=name)
                        else:
                            yield Static(id=name, classes="panel")
        yield Log(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "main daemon" if self.st is not None else "viewer"
        for name in PANELS:
            panel = self.query_one("#clients-panel" if name == "clients" else f"#{name}")
            panel.border_title = PANEL_TITLES[name]
        self.query_one("#log", Log).border_title = "Log"
        self.tick()
        self.set_interval(SCREEN_TICK_S, self.tick)

    def _status(self) -> DaemonStatus | None:
        if self.st is not None:
            return status_of(self.st)
        return read_daemon_status(self.base_dir)

    def _proc(self, status: DaemonStatus | None, now: float) -> ProcFacts:
        if self.st is not None:
            uptime = max(1.0, now - self.st.started_ts)
            return ProcFacts(
                cpu_pct=self.cpu.sample(),
                cpu_avg_pct=process_cpu_s() / uptime * 100.0,
                rss_bytes=current_rss_bytes(),
                peak_rss_bytes=peak_rss_bytes(),
                threads=threading.active_count(),
            )
        if status is None or not daemon_status_alive(status, now):
            return ProcFacts()
        rss, cpu = other_process_usage(status.pid)
        return ProcFacts(cpu_pct=cpu, rss_bytes=rss)

    def _update_log(self, status: DaemonStatus | None) -> None:
        log = self.query_one("#log", Log)
        if self.st is not None:
            new = self.st.log_count - self.shown_log_count
            if new > 0:
                lines = list(self.st.lines)
                log.write_lines(lines[-min(new, len(lines)):])
                self.shown_log_count = self.st.log_count
            return
        recent = status.recent if status is not None else ()
        if recent != self.shown_recent:
            log.clear()
            log.write_lines(list(recent))
            self.shown_recent = recent

    def tick(self) -> None:
        if self.stop_event.is_set() or (
            self.worker_thread is not None and not self.worker_thread.is_alive()
        ):
            self.exit()
            return
        now = time.time()
        status = self._status()
        cache = gather_cache_facts(self.base_dir)
        self.sections = sections = {
            "daemon": daemon_section(
                status, main=self.st is not None, base_dir=self.base_dir,
                owner=cache.owner, now=now,
            ),
            "process": process_section(self._proc(status, now)),
            "cache": cache_section(status, cache, now),
            "startup": startup_section(status, now),
            "clients": clients_section(list_clients(self.base_dir), cache.owner, now),
        }
        for name, section in sections.items():
            self.query_one(f"#{name}", Static).update(render_section(section))
        self._update_log(status)
        self.call_after_refresh(self._balance_columns)

    def _balance_columns(self) -> None:
        """Make the right column as tall as the left one; the window list then
        fills what the panels above it leave, and scrolls when it is longer."""
        left = self.query_one("#column0").outer_size.height
        if left > 0:
            self.query_one("#column1").styles.height = left

    def action_rescan(self) -> None:
        request_cache_refresh(self.base_dir, "daemon screen")
        self.notify("full rescan requested")

    def action_health(self) -> None:
        if self.st is None:
            self.notify("only the main daemon's screen can do this", severity="warning")
            return
        self.st.health_due_at = 0.0
        self.notify("worktree health sweep on the next tick")

    async def action_quit(self) -> None:
        self.stop_event.set()
        self.exit()


def run_daemon_screen(base_dir: Path) -> int:
    stop = threading.Event()
    lock = try_flock(daemon_lock_path(base_dir), str(os.getpid()))
    if lock is None:
        DaemonApp(base_dir, st=None, stop=stop, worker=None).run()
        return 0
    st = new_daemon_state(base_dir, echo=False)
    result: list[int] = []
    worker = threading.Thread(
        target=lambda: result.append(run_daemon(st, stop)), name="b-daemon", daemon=True
    )
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_args: stop.set())
    try:
        worker.start()
        DaemonApp(base_dir, st=st, stop=stop, worker=worker).run()
    finally:
        stop.set()
        if worker.is_alive():
            print("b daemon - stopping, waiting for the running scan", flush=True)
        worker.join(timeout=STOP_WAIT_S)
        lock.close()
    return result[0] if result else 0


def daemon_entry(base_dir: Path, *, once: bool = False, plain: bool = False) -> int:
    """Status screen in a terminal, log lines otherwise."""
    if once or plain or not (sys.stdin.isatty() and sys.stdout.isatty()):
        return cmd_daemon(base_dir, once=once)
    return run_daemon_screen(base_dir)
