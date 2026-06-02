from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.sync import reconcile_worker as rw

# ---- minimal app stub -----------------------------------------------


class _App:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.reconcile_worker_running = False
        self.reconcile_worker_mode = ""
        self.reconcile_worker_reason = ""
        self.reconcile_worker_started_ts = 0.0
        self.reconcile_worker_last_done_ts = 0.0
        self.reconcile_queue: list[tuple[int, str, str, list[Path]]] = []
        self.reconcile_recent: dict[str, list[tuple[str, str]]] = {
            "active": [],
            "archive": [],
        }
        self.reconcile_inconsistency_streak = 0
        self.reconcile_next_due: dict[str, float] = {}
        self.debug_log: list[str] = []
        self.log_calls: list[tuple[str, str]] = []
        self.upserted: list[ProjectRow] = []
        self.removed: list[Path] = []
        self.touched_rows: list[list[ProjectRow]] = []
        self.touched_removed: list[list[Path]] = []
        self.refresh_table_calls = 0
        self.refresh_side_calls = 0
        self.queue_requests: list[tuple[str, str, list[Path], int]] = []
        self.invalidate_calls = 0
        self.cache_refreshes: list[tuple[str, bool]] = []
        self.next_reconcile_runs = 0
        self.rows: list[ProjectRow] = []
        self.start_calls: list[tuple[str, str, list[Path]]] = []

    # ---- knobs that callers in production override ------------------

    def _worker_debug(self, msg: str) -> None:
        self.debug_log.append(msg)

    def _log(self, msg: str, level: str = "info") -> None:
        self.log_calls.append((msg, level))

    def _find_row(self, path: Path):
        for idx, row in enumerate(self.rows):
            if row.path == path:
                return self.rows, idx
        return None

    def _effective_reconcile_parallelism(self, _mode: str) -> int:
        return 1

    def _effective_reconcile_wait_s(self, _mode: str) -> float:
        return 60.0

    def _start_reconcile_rows(
        self, mode: str, reason: str, paths: list[Path],
    ) -> None:
        self.start_calls.append((mode, reason, list(paths)))

    def _queue_reconcile_request(
        self, mode: str, reason: str, paths: list[Path], prio: int,
    ) -> None:
        self.queue_requests.append((mode, reason, list(paths), prio))

    def _upsert_row_local(self, row: ProjectRow, *, invalidate_cache: bool) -> None:
        self.upserted.append(row)

    def _remove_paths_local(self, paths: list[Path]) -> None:
        self.removed.extend(paths)

    def _touch_rows_cache(
        self, rows: list[ProjectRow], removed: list[Path] | None = None,
    ) -> None:
        self.touched_rows.append(list(rows))
        if removed is not None:
            self.touched_removed.append(list(removed))

    def _invalidate_current_rows_cache(self) -> None:
        self.invalidate_calls += 1

    def _refresh_table(self) -> None:
        self.refresh_table_calls += 1

    def _refresh_side(self) -> None:
        self.refresh_side_calls += 1

    def _record_reconcile_recent(self, kind: str, label: str) -> None:
        rw.record_reconcile_recent(self, kind, label)

    def _start_cache_refresh(self, reason: str, force: bool = False) -> None:
        self.cache_refreshes.append((reason, force))

    def _run_next_reconcile_from_queue(self) -> None:
        self.next_reconcile_runs += 1


def _row(path: Path, *, archived: bool = False) -> ProjectRow:
    return ProjectRow(
        path=path,
        name=path.name,
        branch="-",
        dirty="",
        last="",
        src="fs",
        created="",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=archived,
        packed=False,
        pack_format=None,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        size_bytes=0,
        size_refresh_count=0,
        worktree_of="",
        repo_dir="",
    )


# ---- queue_reconcile_request ----------------------------------------


def test_queue_reconcile_request_appends_and_logs(tmp_path: Path) -> None:
    app = _App()
    rw.queue_reconcile_request(
        app, mode="m", reason="rebuild", paths=[tmp_path], priority=2,
    )
    assert len(app.reconcile_queue) == 1
    entry = app.reconcile_queue[0]
    assert entry[1] == "m"
    assert entry[2] == "rebuild"
    assert app.debug_log and "reconcile queued" in app.debug_log[-1]


def test_queue_reconcile_request_caps_at_40(tmp_path: Path) -> None:
    """The push helper trims the queue to keep it bounded — stress
    the limit to prove the call site forwards ``limit=40``."""
    app = _App()
    for i in range(60):
        rw.queue_reconcile_request(
            app, mode="m", reason=f"r{i}", paths=[tmp_path / str(i)], priority=1,
        )
    assert len(app.reconcile_queue) <= 40


# ---- run_next_reconcile_from_queue -----------------------------------


def test_run_next_reconcile_skips_when_queue_empty() -> None:
    app = _App()
    rw.run_next_reconcile_from_queue(app)
    assert app.start_calls == []


def test_run_next_reconcile_dispatches_top_priority(tmp_path: Path) -> None:
    app = _App()
    rw.queue_reconcile_request(
        app, mode="m1", reason="low", paths=[tmp_path / "a"], priority=1,
    )
    rw.queue_reconcile_request(
        app, mode="m2", reason="high", paths=[tmp_path / "b"], priority=5,
    )
    rw.run_next_reconcile_from_queue(app)
    assert len(app.start_calls) == 1
    mode, reason, paths = app.start_calls[0]
    assert mode == "m2" and reason == "high"
    assert paths == [tmp_path / "b"]
    # Top item is consumed; lower-priority entry remains.
    assert len(app.reconcile_queue) == 1


# ---- start_reconcile_rows -------------------------------------------


def test_start_reconcile_rows_skips_when_fast_exit(tmp_path: Path) -> None:
    app = _App()
    app.fast_exit_requested = True
    rw.start_reconcile_rows(app, "m", "rebuild", [tmp_path])
    assert app.reconcile_worker_running is False
    assert app.queue_requests == []


def test_start_reconcile_rows_queues_when_worker_busy(tmp_path: Path) -> None:
    """A reconcile while another worker is already running gets
    enqueued — at priority=2 if the reason starts with ``manual``,
    otherwise priority=1."""
    app = _App()
    app.reconcile_worker_running = True
    rw.start_reconcile_rows(app, "m", "manual rebuild", [tmp_path])
    rw.start_reconcile_rows(app, "m", "auto rebuild", [tmp_path])
    assert app.queue_requests[0][3] == 2  # manual -> high prio
    assert app.queue_requests[1][3] == 1  # auto   -> low prio


def test_start_reconcile_rows_no_paths_no_op() -> None:
    app = _App()
    rw.start_reconcile_rows(app, "m", "r", [])
    assert app.reconcile_worker_running is False


def test_start_reconcile_rows_skips_unknown_paths(tmp_path: Path) -> None:
    """A path that isn't a known row gets filtered out — if every
    path is unknown the worker is not started."""
    app = _App()
    rw.start_reconcile_rows(app, "m", "r", [tmp_path / "nowhere"])
    assert app.reconcile_worker_running is False


# ---- record_reconcile_recent ----------------------------------------


def test_record_reconcile_recent_only_for_known_kinds() -> None:
    app = _App()
    rw.record_reconcile_recent(app, "bogus", "label")
    assert app.reconcile_recent["active"] == []
    assert app.reconcile_recent["archive"] == []


def test_record_reconcile_recent_keeps_last_five() -> None:
    """The recent list is capped at the most recent 5 entries."""
    app = _App()
    for i in range(8):
        rw.record_reconcile_recent(app, "active", f"label-{i}")
    labels = [label for _ts, label in app.reconcile_recent["active"]]
    assert labels == [f"label-{i}" for i in range(3, 8)]


def test_record_reconcile_recent_active_and_archive_independent() -> None:
    app = _App()
    rw.record_reconcile_recent(app, "active", "a1")
    rw.record_reconcile_recent(app, "archive", "g1")
    assert len(app.reconcile_recent["active"]) == 1
    assert len(app.reconcile_recent["archive"]) == 1


# ---- on_reconcile_rows_done -----------------------------------------


_KW = {
    "base_dir": Path("/base"),
    "archive_dir_name": "_archive",
    "mode_active": "active",
    "mode_archive": "archive",
    "level_warn": "warn",
}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def test_on_done_clears_worker_state_with_no_changes() -> None:
    app = _App()
    app.reconcile_worker_running = True
    app.reconcile_worker_mode = "active"
    app.reconcile_worker_reason = "r"
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.reconcile_worker_running is False
    assert app.reconcile_worker_mode == ""
    assert app.reconcile_worker_reason == ""
    assert app.refresh_table_calls == 0  # nothing to refresh
    assert app.next_reconcile_runs == 1


def test_on_done_applies_refreshed_rows(tmp_path: Path) -> None:
    app = _App()
    row = _row(tmp_path / "p", archived=False)
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="rebuild",
        refreshed_rows=[row],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.upserted == [row]
    assert app.refresh_table_calls == 1
    assert app.refresh_side_calls == 1
    # The active-side recent log got a single entry.
    assert len(app.reconcile_recent["active"]) == 1


def test_on_done_applies_removed_paths(tmp_path: Path) -> None:
    app = _App()
    archive_root = tmp_path / "_archive"
    archive_root.mkdir(parents=True)
    archived_path = archive_root / "old"
    archived_path.mkdir()
    rw.on_reconcile_rows_done(
        app,
        mode="archive",
        reason="rebuild",
        refreshed_rows=[],
        removed_paths=[archived_path],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        base_dir=tmp_path,
        archive_dir_name="_archive",
        mode_active="active",
        mode_archive="archive",
        level_warn="warn",
    )
    assert app.removed == [archived_path]
    assert app.refresh_table_calls == 1
    assert len(app.reconcile_recent["archive"]) == 1


def test_on_done_failure_logs_and_increments_streak(tmp_path: Path) -> None:
    app = _App()
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=2,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.reconcile_inconsistency_streak == 1
    assert any("failed=2" in m for m, _l in app.log_calls)


def test_on_done_fatal_error_logged() -> None:
    app = _App()
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=1,
        fatal_error="RuntimeError: boom",
        is_under=_is_under,
        **_KW,
    )
    assert any("fatal worker failure" in m for m, _l in app.log_calls)


def test_on_done_clears_streak_on_clean_run() -> None:
    app = _App()
    app.reconcile_inconsistency_streak = 2
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.reconcile_inconsistency_streak == 0


def test_on_done_streak_trigger_forces_cache_refresh() -> None:
    """Three consecutive failed runs → force a hard cache refresh
    and reset the streak."""
    app = _App()
    app.reconcile_inconsistency_streak = 2
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=1,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.reconcile_inconsistency_streak == 0
    assert app.cache_refreshes == [("hard inconsistency", True)]


def test_on_done_schedules_next_due_for_known_modes() -> None:
    app = _App()
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert "active" in app.reconcile_next_due


def test_on_done_skips_due_scheduling_for_unknown_mode() -> None:
    """Custom one-off modes shouldn't pollute the periodic schedule."""
    app = _App()
    rw.on_reconcile_rows_done(
        app,
        mode="adhoc",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert "adhoc" not in app.reconcile_next_due


def test_on_done_classifies_removed_archive_vs_active_paths(tmp_path: Path) -> None:
    """A removed path under the archive dir is logged under ``archive``;
    everything else lands in ``active``."""
    app = _App()
    archive_dir = tmp_path / "_archive" / "2026"
    archive_dir.mkdir(parents=True)
    in_archive = archive_dir / "x"
    in_archive.mkdir()
    in_active = tmp_path / "alive"
    in_active.mkdir()
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[in_archive, in_active],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        base_dir=tmp_path,
        archive_dir_name="_archive",
        mode_active="active",
        mode_archive="archive",
        level_warn="warn",
    )
    assert len(app.reconcile_recent["archive"]) == 1
    assert len(app.reconcile_recent["active"]) == 1


def test_on_done_starts_next_queued_reconcile() -> None:
    app = _App()
    rw.on_reconcile_rows_done(
        app,
        mode="active",
        reason="r",
        refreshed_rows=[],
        removed_paths=[],
        failed=0,
        fatal_error="",
        is_under=_is_under,
        **_KW,
    )
    assert app.next_reconcile_runs == 1
