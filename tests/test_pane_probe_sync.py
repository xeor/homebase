from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homebase.core.models import PropertyDef
from homebase.ui.sync import pane_probe


@dataclass
class _Ctx:
    property_defs: list[PropertyDef]


class _App:
    def __init__(self, defs: list[PropertyDef]) -> None:
        self.fast_exit_requested = False
        self.pane_probe_running = False
        self.pane_probe_fast_until_ts = 0.0
        self.pane_probe_next_due_at = 0.0
        self.pane_probe_last_done_ts = 0.0
        self.view_mode = "active"
        self.query = ""
        self.ctx = _Ctx(property_defs=defs)
        self.started = 0

    def _table_visible_columns_for_view(self, _view: str):
        return [{"id": "name"}]

    def _start_probe_open_panes(self) -> None:
        self.started += 1

    def _pane_probe_profile_min_interval_s(self) -> float:
        min_interval_s: float | None = None
        for pdef in self.ctx.property_defs:
            has_tmux_query = any(
                str(query.get("type", "")).strip()
                in {"tmux_open_panes", "tmux_editor_commands"}
                for query in pdef.queries
            )
            if not has_tmux_query:
                continue
            profile = pdef.cache_profiles_by_view.get("active", {}) if pdef.cache_profiles_by_view else {}
            if not isinstance(profile, dict):
                continue
            raw = profile.get("min_interval_s", profile.get("update_interval_s", 0.5))
            try:
                candidate = max(0.05, float(raw))
            except (TypeError, ValueError):
                continue
            min_interval_s = candidate if min_interval_s is None else min(min_interval_s, candidate)
        return min_interval_s if min_interval_s is not None else 0.5

    def _pane_probe_profile_slow_interval_s(self) -> float:
        slow_interval_s: float | None = None
        for pdef in self.ctx.property_defs:
            has_tmux_query = any(
                str(query.get("type", "")).strip()
                in {"tmux_open_panes", "tmux_editor_commands"}
                for query in pdef.queries
            )
            if not has_tmux_query:
                continue
            profile = pdef.cache_profiles_by_view.get("active", {}) if pdef.cache_profiles_by_view else {}
            if not isinstance(profile, dict):
                continue
            try:
                candidate = max(0.05, float(profile.get("update_interval_s", 6.0)))
            except (TypeError, ValueError):
                continue
            slow_interval_s = candidate if slow_interval_s is None else min(slow_interval_s, candidate)
        return slow_interval_s if slow_interval_s is not None else 6.0

    def _pane_probe_profile_fast_interval_s(self) -> float:
        return min(
            self._pane_probe_profile_min_interval_s(),
            self._pane_probe_profile_slow_interval_s(),
        )


def test_pane_probe_desired_interval_uses_profile_policy(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "1")
    pdef = PropertyDef(
        key="act",
        label="act",
        token="ACT",
        queries=(
            {
                "type": "tmux_open_panes",
            },
        ),
        cache_profiles_by_view={
            "active": {
                "update_interval_s": 9.0,
                "min_interval_s": 0.2,
            }
        },
    )
    app = _App([pdef])
    out = pane_probe.pane_probe_desired_interval_s(app)
    assert out == 9.0


def test_maybe_probe_open_panes_uses_profile_min_interval(monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "1")
    pdef = PropertyDef(
        key="act",
        label="act",
        token="ACT",
        queries=(
            {
                "type": "tmux_open_panes",
            },
        ),
        cache_profiles_by_view={
            "active": {
                "update_interval_s": 4.0,
                "min_interval_s": 2.0,
            }
        },
    )
    app = _App([pdef])
    app.pane_probe_last_done_ts = 100.0
    app.pane_probe_next_due_at = 0.0

    monkeypatch.setattr(pane_probe.time, "time", lambda: 101.0)
    pane_probe.maybe_probe_open_panes(app)
    assert app.started == 0

    monkeypatch.setattr(pane_probe.time, "time", lambda: 103.1)
    pane_probe.maybe_probe_open_panes(app)
    assert app.started == 1


def test_pane_probe_desired_interval_without_tmux_uses_profile_slow(monkeypatch) -> None:
    monkeypatch.delenv("TMUX", raising=False)
    pdef = PropertyDef(
        key="act",
        label="act",
        token="ACT",
        queries=({"type": "tmux_open_panes"},),
        cache_profiles_by_view={"active": {"update_interval_s": 7.5}},
    )
    app = _App([pdef])
    app._pane_probe_profile_slow_interval_s = lambda: 7.5
    assert pane_probe.pane_probe_desired_interval_s(app) == 7.5


def test_start_probe_open_panes_honors_project_scan_limit(monkeypatch) -> None:
    class _Row:
        def __init__(self, path: Path) -> None:
            self.path = path

    class _ProbeApp:
        def __init__(self) -> None:
            self.fast_exit_requested = False
            self.pane_probe_running = False
            self.open_panes_by_project = {}
            self.open_pane_count_by_project = {}
            self.open_pane_overflow_projects = set()
            self.active_rows = [_Row(Path("/tmp/p1")), _Row(Path("/tmp/p2"))]
            self.archived_rows = []
            self.mapping = None

        def _current_rows(self):
            return self.active_rows

        def _pane_probe_project_scan_limit(self) -> int:
            return 1

        def _queue_dynamic_property_refresh(self, _paths):
            return None

        def _pane_probe_desired_interval_s(self) -> float:
            return 1.0

        def call_from_thread(self, fn, mapping):
            self.mapping = mapping
            fn(mapping)

        def _on_probe_open_panes_done(self, _mapping):
            self.pane_probe_running = False

    class _ImmediateThread:
        def __init__(self, target, daemon: bool) -> None:
            self._target = target

        def start(self) -> None:
            self._target()

    class _Proc:
        returncode = 0
        stdout = "%1\ts:1.1\tw\tbash\t/tmp/p1/sub\t1\n%2\ts:1.2\tw\tbash\t/tmp/p2/sub\t1\n"

    app = _ProbeApp()
    monkeypatch.setenv("TMUX", "1")
    monkeypatch.setattr(pane_probe.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(pane_probe.subprocess, "run", lambda *a, **k: _Proc())
    pane_probe.start_probe_open_panes(app)
    assert app.mapping is not None
    mapped_names = {p.name for p in app.mapping.keys()}
    assert "p1" in mapped_names
    assert "p2" not in mapped_names
