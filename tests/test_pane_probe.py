"""Tests for ``ui/sync/pane_probe`` helpers — the pure decision
functions and the on-done state update. The threaded tmux probe
itself is not exercised here (it'd require tmux on the test host)."""
from __future__ import annotations

from pathlib import Path

from homebase.core.models import PaneRef
from homebase.ui.sync import pane_probe as pp

# ---- project_for_path -----------------------------------------------


def test_project_for_path_matches_exact(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    proj.mkdir()
    out = pp.project_for_path(proj, {proj})
    assert out == proj


def test_project_for_path_walks_up(tmp_path: Path) -> None:
    """A subdirectory inside a project root resolves to the root."""
    proj = tmp_path / "p"
    inside = proj / "sub" / "deeper"
    inside.mkdir(parents=True)
    out = pp.project_for_path(inside, {proj})
    assert out == proj


def test_project_for_path_returns_none_when_no_match(tmp_path: Path) -> None:
    out = pp.project_for_path(tmp_path / "x", {tmp_path / "other"})
    assert out is None


def test_project_for_path_stops_at_filesystem_root(tmp_path: Path) -> None:
    """The walk-up must terminate even if no root matches — never spin."""
    out = pp.project_for_path(Path("/"), {tmp_path / "anything"})
    assert out is None


# ---- _resolve_cached ------------------------------------------------


def test_resolve_cached_returns_path_when_resolvable(tmp_path: Path) -> None:
    pp._resolved_path_str.cache_clear()
    real = tmp_path / "f.txt"
    real.write_text("x")
    out = pp._resolve_cached(real)
    assert out == real.resolve()


def test_resolve_cached_returns_none_on_failure(monkeypatch) -> None:
    pp._resolved_path_str.cache_clear()

    def boom(*_args, **_kwargs):
        raise OSError("nope")

    monkeypatch.setattr(pp.Path, "resolve", boom)
    assert pp._resolve_cached(Path("/anywhere")) is None


# ---- on_probe_open_panes_done ---------------------------------------


class _App:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.pane_probe_running = True
        self.open_panes_by_project: dict[Path, list[PaneRef]] = {}
        self.open_pane_count_by_project: dict[Path, int] = {}
        self.open_pane_overflow_projects: set[Path] = set()
        self.pane_state_sig = ""
        self.pane_probe_last_done_ts = 0.0
        self.pane_probe_next_due_at = 0.0
        self.queued: list[list[Path]] = []
        self.fast_interval = 1.0
        self.slow_interval = 30.0
        self.table_refreshes = 0
        self.side_refreshes = 0

    def _queue_dynamic_property_refresh(self, paths: list[Path]) -> None:
        self.queued.append(list(paths))

    def _refresh_table(self) -> None:
        self.table_refreshes += 1

    def _refresh_side(self) -> None:
        self.side_refreshes += 1

    def _pane_probe_desired_interval_s(self) -> float:
        return self.slow_interval


def _pane(path: Path, pid: str = "0") -> PaneRef:
    return PaneRef(
        pane_id=pid,
        target=f"s:1.0-{pid}",
        window_name="",
        command="",
        cwd=path,
        active=False,
    )


def test_on_probe_done_short_circuits_on_fast_exit(tmp_path: Path) -> None:
    app = _App()
    app.fast_exit_requested = True
    pp.on_probe_open_panes_done(app, {tmp_path: [_pane(tmp_path)]})
    # No state mutation: app.pane_probe_running stays True since
    # the early return skips assignment.
    assert app.pane_probe_running is True
    assert app.open_panes_by_project == {}


def test_on_probe_done_writes_counts_and_clears_running(tmp_path: Path) -> None:
    app = _App()
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    pp.on_probe_open_panes_done(app, {p1: [_pane(p1), _pane(p1, "1")], p2: [_pane(p2)]})
    assert app.pane_probe_running is False
    assert app.open_pane_count_by_project == {p1: 2, p2: 1}
    assert app.table_refreshes == 1
    assert app.side_refreshes == 1
    # Below the overflow threshold (>9 panes) — set should be empty.
    assert app.open_pane_overflow_projects == set()


def test_on_probe_failed_preserves_counts_and_schedules_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _App()
    app.open_pane_count_by_project = {tmp_path: 3}
    app.pane_probe_running = True
    logs: list[tuple[str, str]] = []
    app._log = lambda message, level: logs.append((message, level))
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)

    pp.on_probe_open_panes_failed(app, "tmux pane probe failed: unavailable")

    assert app.pane_probe_running is False
    assert app.open_pane_count_by_project == {tmp_path: 3}
    assert app.pane_probe_next_due_at == 130.0
    assert logs == [("tmux pane probe failed: unavailable", "warn")]


def test_on_probe_done_flags_overflow_projects(tmp_path: Path) -> None:
    app = _App()
    proj = tmp_path / "wide"
    panes = [_pane(proj, str(i)) for i in range(11)]
    pp.on_probe_open_panes_done(app, {proj: panes})
    assert proj in app.open_pane_overflow_projects


def test_on_probe_done_queues_dynamic_refresh_on_change(tmp_path: Path) -> None:
    """When pane counts change, the affected project paths get
    queued for a dynamic property refresh."""
    app = _App()
    app.open_pane_count_by_project = {tmp_path / "p1": 1}
    pp.on_probe_open_panes_done(app, {tmp_path / "p2": [_pane(tmp_path / "p2")]})
    assert app.queued, "expected a refresh queue call"
    # Both the disappearing project and the new one were touched.
    touched = set(app.queued[-1])
    assert (tmp_path / "p1") in touched
    assert (tmp_path / "p2") in touched


def test_on_probe_done_no_queue_when_signature_stable(tmp_path: Path) -> None:
    """When the new mapping matches the cached signature exactly,
    nothing is requeued."""
    app = _App()
    p = tmp_path / "p"
    panes = [_pane(p)]
    # Seed: matching signature + counts.
    app.pane_state_sig = f"{p}:1"
    app.open_pane_count_by_project = {p: 1}
    pp.on_probe_open_panes_done(app, {p: panes})
    assert app.queued == []


def test_on_probe_done_schedules_next_due(tmp_path: Path, monkeypatch) -> None:
    app = _App()
    monkeypatch.setattr(pp.time, "time", lambda: 1000.0)
    pp.on_probe_open_panes_done(app, {})
    assert app.pane_probe_last_done_ts == 1000.0
    assert app.pane_probe_next_due_at == 1030.0


# ---- pane_probe_desired_interval_s -----------------------------------


class _IntervalApp:
    def __init__(self) -> None:
        self.pane_probe_fast_until_ts = 0.0
        self.view_mode = "archive"
        self.query = ""

    def _pane_probe_profile_fast_interval_s(self) -> float:
        return 1.5

    def _pane_probe_profile_slow_interval_s(self) -> float:
        return 30.0

    def _table_visible_columns_for_view(self, _mode: str):
        return [{"id": "name"}, {"id": "branch"}]


def test_desired_interval_slow_when_not_in_tmux(monkeypatch) -> None:
    """Without ``$TMUX`` the probe drops to the slow cadence — there's
    no tmux server to talk to."""
    monkeypatch.delenv("TMUX", raising=False)
    app = _IntervalApp()
    assert pp.pane_probe_desired_interval_s(app) == 30.0


def test_desired_interval_fast_when_in_fast_window(monkeypatch) -> None:
    """If a recent event armed a fast window, that wins regardless of
    view or query state."""
    monkeypatch.setattr(pp, "is_inside_current_tmux_pane", lambda: True)
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    app = _IntervalApp()
    app.pane_probe_fast_until_ts = 200.0
    assert pp.pane_probe_desired_interval_s(app) == 1.5


def test_desired_interval_fast_when_properties_column_visible(monkeypatch) -> None:
    """The properties column shows per-project info that depends on
    pane state — keep the probe at fast cadence whenever it's
    visible."""
    monkeypatch.setattr(pp, "is_inside_current_tmux_pane", lambda: True)
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    app = _IntervalApp()
    app.view_mode = "active"
    app._table_visible_columns_for_view = lambda _m: [{"id": "properties"}]
    assert pp.pane_probe_desired_interval_s(app) == 1.5


def test_desired_interval_fast_when_query_contains_act(monkeypatch) -> None:
    """A query that includes the literal ``act`` token (e.g. ``:act``,
    ``act+``, etc.) implies the user is filtering on activity — go
    fast."""
    monkeypatch.setattr(pp, "is_inside_current_tmux_pane", lambda: True)
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    app = _IntervalApp()
    app.query = ":act"
    assert pp.pane_probe_desired_interval_s(app) == 1.5


def test_desired_interval_slow_default(monkeypatch) -> None:
    """In tmux, archive view, no fast triggers — slow cadence."""
    monkeypatch.setenv("TMUX", "/tmp/tmux-1")
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    app = _IntervalApp()
    assert pp.pane_probe_desired_interval_s(app) == 30.0


# ---- maybe_probe_open_panes -----------------------------------------


class _MaybeApp:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.pane_probe_running = False
        self.pane_probe_last_done_ts = 0.0
        self.pane_probe_next_due_at = 0.0
        self.started = 0

    def _pane_probe_profile_min_interval_s(self) -> float:
        return 0.5

    def _start_probe_open_panes(self) -> None:
        self.started += 1


def test_maybe_probe_skips_when_fast_exit() -> None:
    app = _MaybeApp()
    app.fast_exit_requested = True
    pp.maybe_probe_open_panes(app)
    assert app.started == 0


def test_maybe_probe_skips_when_already_running() -> None:
    app = _MaybeApp()
    app.pane_probe_running = True
    pp.maybe_probe_open_panes(app)
    assert app.started == 0


def test_maybe_probe_respects_min_interval(monkeypatch) -> None:
    """A probe that just finished must wait at least
    ``_pane_probe_profile_min_interval_s`` before another one fires —
    even if the periodic ``next_due_at`` has already elapsed."""
    app = _MaybeApp()
    app.pane_probe_last_done_ts = 100.0
    monkeypatch.setattr(pp.time, "time", lambda: 100.1)  # min is 0.5
    pp.maybe_probe_open_panes(app)
    assert app.started == 0


def test_maybe_probe_respects_next_due_at(monkeypatch) -> None:
    app = _MaybeApp()
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    app.pane_probe_next_due_at = 101.0
    pp.maybe_probe_open_panes(app)
    assert app.started == 0


def test_maybe_probe_fires_when_due(monkeypatch) -> None:
    app = _MaybeApp()
    monkeypatch.setattr(pp.time, "time", lambda: 100.0)
    pp.maybe_probe_open_panes(app)
    assert app.started == 1


# ---- start_probe_open_panes (no-tmux branch) ------------------------


class _StartApp:
    def __init__(self) -> None:
        self.fast_exit_requested = False
        self.pane_probe_running = False
        self.open_panes_by_project: dict[Path, list[PaneRef]] = {}
        self.open_pane_count_by_project: dict[Path, int] = {}
        self.open_pane_overflow_projects: set[Path] = set()
        self.pane_probe_next_due_at = 0.0
        self.queued: list[list[Path]] = []

    def _queue_dynamic_property_refresh(self, paths: list[Path]) -> None:
        self.queued.append(list(paths))

    def _pane_probe_desired_interval_s(self) -> float:
        return 60.0


def test_start_probe_skips_when_fast_exit() -> None:
    app = _StartApp()
    app.fast_exit_requested = True
    pp.start_probe_open_panes(app)
    assert app.pane_probe_running is False


def test_start_probe_clears_stale_state_when_no_tmux(monkeypatch, tmp_path: Path) -> None:
    """Outside of tmux, the probe doesn't run — but any stale
    ``open_panes_by_project`` from a previous tmux session must be
    cleared and dependents requeued."""
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(pp.time, "time", lambda: 1000.0)
    app = _StartApp()
    p = tmp_path / "p"
    app.open_panes_by_project = {p: [_pane(p)]}
    app.open_pane_count_by_project = {p: 1}
    pp.start_probe_open_panes(app)
    assert app.open_panes_by_project == {}
    assert app.open_pane_count_by_project == {}
    assert app.queued and app.queued[0] == [p]
    assert app.pane_probe_next_due_at == 1060.0


def test_start_probe_no_clear_when_no_tmux_and_already_empty(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(pp.time, "time", lambda: 1000.0)
    app = _StartApp()
    pp.start_probe_open_panes(app)
    assert app.queued == []
    assert app.pane_probe_next_due_at == 1060.0
