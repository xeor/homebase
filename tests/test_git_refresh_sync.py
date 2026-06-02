from __future__ import annotations

from pathlib import Path

from homebase.ui.sync import git_refresh


class _Row:
    def __init__(self, i: int, *, branch: str = "main", dirty: str = "~") -> None:
        self.path = Path(f"/tmp/p{i}")
        self.branch = branch
        self.dirty = dirty
        self.git_ts = 0
        self.last_ts = 0
        self.last = ""
        self.src = "fs"
        self.last_cached_ts = 0
        # caches that refresh_row_caches will touch
        self.name = f"p{i}"
        self.description = ""
        self.tags: list[str] = []
        self.properties: list[str] = []
        self.tags_lower: frozenset[str] = frozenset()
        self.haystack_lower = ""


class _App:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.git_refresh_running = False
        self.cache_worker_running = False
        self.git_refresh_last_ts = 0.0
        self.git_refresh_next_due_at = 0.0
        self.git_refresh_paths: set[Path] = set()
        self.git_refresh_reason = ""
        self.selected = None
        self.rows = [_Row(i) for i in range(20)]
        self.started: list[Path] = []
        self.touched: list[_Row] = []
        self.refresh_table_calls = 0
        self.refresh_side_calls = 0

    def _critical_job_active(self) -> bool:
        return False

    def _current_rows(self):
        return self.rows

    def _selected_row(self):
        return self.selected

    def _start_git_refresh(self, paths: list[Path], reason: str) -> None:
        self.started = paths

    def _git_refresh_min_interval_s(self) -> float:
        return 0.1

    def _git_refresh_interval_s(self) -> float:
        return 5.0

    def _git_refresh_batch_size(self) -> int:
        return 3

    def _find_row(self, path: Path):
        for idx, row in enumerate(self.rows):
            if row.path == path:
                return self.rows, idx
        return None

    def _refresh_table(self) -> None:
        self.refresh_table_calls += 1

    def _refresh_side(self) -> None:
        self.refresh_side_calls += 1

    def _touch_rows_cache(self, rows) -> None:
        self.touched = list(rows)


def test_maybe_refresh_visible_git_uses_profile_batch_size(monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert len(app.started) == 3


def test_maybe_refresh_visible_git_respects_next_due(monkeypatch) -> None:
    app = _App()
    app.git_refresh_next_due_at = 11.0
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_skips_when_fast_exit() -> None:
    app = _App()
    app.fast_exit_requested = True
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_skips_when_already_running() -> None:
    app = _App()
    app.git_refresh_running = True
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_skips_when_cache_worker_running() -> None:
    app = _App()
    app.cache_worker_running = True
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_respects_min_interval(monkeypatch) -> None:
    """A recent successful refresh must throttle the next one."""
    app = _App()
    app.git_refresh_last_ts = 10.0
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.05)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_noop_when_no_rows(monkeypatch) -> None:
    app = _App()
    app.rows = []
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_skips_clean_rows(monkeypatch) -> None:
    """Rows already showing a known clean state ("" dirty) don't
    need a re-probe."""
    app = _App()
    app.rows = [_Row(i, dirty="") for i in range(5)]
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_skips_non_git_rows(monkeypatch) -> None:
    """branch=='-' or '?' means we already know there's no git repo;
    no point spawning a worker for them."""
    app = _App()
    app.rows = [_Row(i, branch="-") for i in range(5)]
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started == []


def test_maybe_refresh_visible_git_prioritises_selected_row(monkeypatch) -> None:
    """The currently-selected row jumps the queue — it appears first
    in the batch even if it would otherwise have been further down."""
    app = _App()
    # Selected row is the LAST one — without prioritisation it
    # wouldn't make it into a 3-wide batch starting from index 0.
    sel = app.rows[19]
    app.selected = sel
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started[0] == sel.path
    assert len(app.started) == 3


def test_maybe_refresh_visible_git_deduplicates_selected_into_batch(monkeypatch) -> None:
    """If the selected row would also have been picked from scanning
    the visible window, it appears once — not twice."""
    app = _App()
    app.selected = app.rows[0]
    monkeypatch.setattr(git_refresh.time, "time", lambda: 10.0)
    git_refresh.maybe_refresh_visible_git(app)
    assert app.started.count(app.rows[0].path) == 1


def test_start_git_refresh_no_paths_no_op(monkeypatch) -> None:
    app = _App()
    git_refresh.start_git_refresh(app, [], reason="visible")
    assert app.git_refresh_running is False


def test_start_git_refresh_filters_non_git_rows(monkeypatch) -> None:
    """Rows whose branch is ``"-"`` are skipped — the worker would
    just no-op on them."""
    app = _App()
    target = app.rows[0]
    target.branch = "-"
    # Patch git_info to never run, threading.Thread.start to no-op.
    started_thread_count = {"n": 0}

    class _Thread:
        def __init__(self, *args, **kwargs) -> None:
            self.daemon = True

        def start(self) -> None:
            started_thread_count["n"] += 1

    monkeypatch.setattr(git_refresh.threading, "Thread", _Thread)
    git_refresh.start_git_refresh(app, [target.path], reason="visible")
    # No worker spun up because the only candidate was filtered out.
    assert started_thread_count["n"] == 0
    assert app.git_refresh_running is False


def test_start_git_refresh_skips_unknown_paths(monkeypatch) -> None:
    """A path that doesn't resolve via _find_row is dropped silently."""
    app = _App()
    spawned = {"n": 0}

    class _Thread:
        def __init__(self, *args, **kwargs) -> None:
            self.daemon = True

        def start(self) -> None:
            spawned["n"] += 1

    monkeypatch.setattr(git_refresh.threading, "Thread", _Thread)
    git_refresh.start_git_refresh(app, [Path("/nowhere")], reason="visible")
    assert spawned["n"] == 0
    assert app.git_refresh_running is False


def test_start_git_refresh_arms_state_and_spawns_worker(monkeypatch) -> None:
    app = _App()
    target = app.rows[0]
    spawned = {"args": None, "n": 0}

    class _Thread:
        def __init__(self, *args, target_fn=None, **kwargs) -> None:
            # threading.Thread uses ``target`` kw; capture it.
            self.daemon = True
            self._target = kwargs.get("target")
            spawned["args"] = self._target

        def start(self) -> None:
            spawned["n"] += 1

    monkeypatch.setattr(git_refresh.threading, "Thread", _Thread)
    monkeypatch.setattr(git_refresh.time, "time", lambda: 50.0)
    git_refresh.start_git_refresh(app, [target.path], reason="visible")
    assert app.git_refresh_running is True
    assert app.git_refresh_paths == {target.path}
    assert app.git_refresh_reason == "visible"
    assert app.git_refresh_last_ts == 50.0
    assert app.git_refresh_next_due_at == 55.0  # last_ts + interval
    assert spawned["n"] == 1
    assert app.refresh_table_calls == 1
    assert app.refresh_side_calls == 1


def test_on_git_refresh_done_clears_state(monkeypatch) -> None:
    app = _App()
    app.git_refresh_running = True
    app.git_refresh_paths = {app.rows[0].path}
    app.git_refresh_reason = "visible"
    monkeypatch.setattr(git_refresh.time, "time", lambda: 100.0)
    git_refresh.on_git_refresh_done(app, [])
    assert app.git_refresh_running is False
    assert app.git_refresh_paths == set()
    assert app.git_refresh_reason == ""
    assert app.git_refresh_last_ts == 100.0
    assert app.git_refresh_next_due_at == 105.0


def test_on_git_refresh_done_applies_updates_and_touches_cache(monkeypatch) -> None:
    app = _App()
    target = app.rows[0]
    monkeypatch.setattr(git_refresh.time, "time", lambda: 200.0)
    git_refresh.on_git_refresh_done(
        app, [(target.path, "main", "", 12345)],
    )
    assert target.branch == "main"
    assert target.dirty == ""
    assert target.git_ts == 12345
    assert target.src == "git"
    assert target.last_ts == 12345
    assert target.last_cached_ts == 200
    # Cache touch was called with the updated row.
    assert app.touched == [target]


def test_on_git_refresh_done_fs_when_no_git_ts(monkeypatch) -> None:
    """A row that doesn't yield a git_ts is marked src=fs and not
    promoted to a new last_ts."""
    app = _App()
    target = app.rows[0]
    target.last_ts = 999
    target.last = "1999-01-01"
    monkeypatch.setattr(git_refresh.time, "time", lambda: 200.0)
    git_refresh.on_git_refresh_done(
        app, [(target.path, "main", "", 0)],
    )
    assert target.src == "fs"
    assert target.last_ts == 999  # untouched
    assert target.last == "1999-01-01"


def test_on_git_refresh_done_ignores_unknown_paths(monkeypatch) -> None:
    """Updates for paths that no longer exist in the row index are
    silently dropped — the worker may complete after a row was
    archived or removed."""
    app = _App()
    monkeypatch.setattr(git_refresh.time, "time", lambda: 50.0)
    git_refresh.on_git_refresh_done(
        app, [(Path("/nowhere"), "main", "", 1)],
    )
    assert app.touched == []
