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
from textual.containers import Grid
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
    DaemonState,
    cmd_daemon,
    new_daemon_state,
    run_daemon,
    status_of,
)
from ..core.constants import (
    CACHE_MAX_AGE_S,
    DAEMON_SIGNATURE_CHECK_S,
    UI_TICK_WORKTREE_HEALTH_S,
)
from ..core.proc_stats import (
    CpuSampler,
    current_rss_bytes,
    other_process_usage,
    peak_rss_bytes,
    process_cpu_s,
)
from ..core.utils import fmt_duration, fmt_size_human

# How long quitting waits for a running full scan before leaving it behind.
STOP_WAIT_S = 30.0
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


def daemon_section(
    status: DaemonStatus | None, *, main: bool, base_dir: Path, owner: str, now: float
) -> Section:
    if status is None or (not main and not daemon_status_alive(status, now)):
        return ("Daemon", [("running", "no"), ("base", str(base_dir))])
    rows = [
        ("this screen", "main daemon" if main else f"viewer of pid {status.pid}"),
        ("pid", str(status.pid)),
        ("version", status.version),
        ("base", str(base_dir)),
        ("uptime", fmt_duration(now - status.started_ts)),
        ("role", _role(status, owner)),
        ("doing", _doing(status, now)),
        ("heartbeat", _ago(status.heartbeat_ts, now)),
    ]
    return ("Daemon", rows)


def process_section(proc: ProcFacts) -> Section:
    rows = [
        ("cpu now", _pct(proc.cpu_pct)),
        ("cpu average", _pct(proc.cpu_avg_pct)),
        ("memory", _size(proc.rss_bytes)),
        ("memory peak", _size(proc.peak_rss_bytes)),
        ("threads", "-" if proc.threads is None else str(proc.threads)),
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


def cache_section(status: DaemonStatus | None, cache: CacheFacts, now: float) -> Section:
    last = "-"
    if status is not None and status.refreshes:
        last = f"took {status.last_refresh_s:.1f}s ({status.last_reason or '-'})"
    rows = [
        ("rows", _rows_text(status)),
        ("database", fmt_size_human(cache.db_bytes)),
        ("full scan", _ago(cache.full_scan_ts, now)),
        ("last scan", last),
        ("scans", "-" if status is None else str(status.refreshes)),
        ("next scan", _next_scan(cache, now)),
        ("last write", _ago(cache.last_write_ts, now)),
        ("request", cache.pending_request or "-"),
        ("worktree health", _health_text(status, now)),
    ]
    return ("Cache", rows)


def _short_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def clients_section(clients: list[ClientInfo], owner: str, now: float) -> Section:
    owner_pid = owner.split(" ", 1)[0]
    rows: list[tuple[str, str]] = [("connected b", str(len(clients)))]
    for client in clients:
        mark = ", cache owner" if str(client.pid) == owner_pid else ""
        tty = client.tty.removeprefix("/dev/") or "-"
        rows.append(
            (
                f"pid {client.pid}",
                f"{tty}  up {fmt_duration(now - client.started_ts)}{mark}  {_short_path(client.cwd)}",
            )
        )
    return ("Clients", rows)


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
    #panels { grid-size: 2; grid-gutter: 0 1; height: auto; }
    .panel { border: round $primary; padding: 0 1; height: auto; }
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
        with Grid(id="panels"):
            for name in ("daemon", "process", "cache", "clients"):
                yield Static(id=name, classes="panel")
        yield Log(id="log")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "main daemon" if self.st is not None else "viewer"
        for name in ("daemon", "process", "cache", "clients"):
            self.query_one(f"#{name}", Static).border_title = name.capitalize()
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
            "clients": clients_section(list_clients(self.base_dir), cache.owner, now),
        }
        for name, section in sections.items():
            self.query_one(f"#{name}", Static).update(render_section(section))
        self._update_log(status)

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
