from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from homebase.config.hooks import HookRefreshConfig, HookRefreshWorkerConfig
from homebase.core.models import HookSpec


def _row(path: Path, *, tags: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        path=path,
        name=path.name,
        archived=False,
        tags=list(tags or []),
        properties=[],
        description="",
        wip=False,
        suffix=None,
        packed=False,
        base_meta={},
        last_ts=0,
        created_ts=0,
        archived_ts=0,
        branch="",
        dirty="",
    )


def _spec(
    name: str,
    *,
    event: str = "tag_change",
    refresh_enabled: bool = True,
    refresh_min_interval_s: float = 60.0,
) -> HookSpec:
    return HookSpec(
        timing="post",
        event=event,
        name=name,
        source="bundled",
        enabled=True,
        views=(),
        config={},
        slow_warn_s=30.0,
        refresh_enabled=refresh_enabled,
        refresh_min_interval_s=refresh_min_interval_s,
    )


class StubBApp:
    """Lightweight stand-in for BApp exposing only what _maybe_run_hook_refresh touches."""

    def __init__(self, base_dir: Path, *, refresh_cfg: HookRefreshConfig, specs: list[HookSpec], rows: list[SimpleNamespace]) -> None:
        from homebase.core.constants import MODE_ACTIVE

        self.base_dir = base_dir
        self.view_mode = MODE_ACTIVE
        self.fast_exit_requested = False
        self.cache_worker_running = False
        self.reconcile_worker_running = False
        self.active_rows = rows
        self.archived_rows: list[SimpleNamespace] = []
        spec_map: dict[tuple[str, str], list[HookSpec]] = {}
        for spec in specs:
            spec_map.setdefault((spec.timing, spec.event), []).append(spec)
        self.ctx = SimpleNamespace(hook_specs=spec_map, hook_refresh_config=refresh_cfg)
        self.hook_refresh_last: dict[tuple[Path, str], float] = {}
        self.dispatched: list[dict[str, object]] = []
        self.hook_running: dict[str, float] = {}

    def call_from_thread(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def _critical_job_active(self) -> bool:
        return False


def _patch_dispatch(monkeypatch, app: StubBApp) -> None:
    def _fake_dispatch(
        _app,
        *,
        targets,
        view,
        hook_filter=None,
        event_filter=None,
        source="manual",
        require_refresh_enabled=False,
    ):
        app.dispatched.append({
            "targets": [t.path for t in targets],
            "view": view,
            "hook_filter": hook_filter,
            "event_filter": event_filter,
            "source": source,
            "require_refresh_enabled": require_refresh_enabled,
        })

    monkeypatch.setattr("homebase.hooks.refresh.dispatch_refresh_tui", _fake_dispatch)


def _invoke_tick(app: StubBApp) -> None:
    from homebase.ui.app import BApp

    BApp._maybe_run_hook_refresh(app)


def test_worker_picks_due_candidates_and_dispatches(tmp_path, monkeypatch) -> None:
    rows = [_row(tmp_path / "p1", tags=["py"]), _row(tmp_path / "p2", tags=["py"])]
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(
            enabled=True,
            worker=HookRefreshWorkerConfig(batch_size=10, skip_when_busy=True),
        ),
        specs=[_spec("tag_files_sync")],
        rows=rows,
    )
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched
    dispatched_paths = sorted(p for call in app.dispatched for p in call["targets"])
    assert dispatched_paths == sorted(r.path for r in rows)
    for call in app.dispatched:
        assert call["source"] == "worker"
        assert call["require_refresh_enabled"] is True


def test_worker_respects_disabled_config(tmp_path, monkeypatch) -> None:
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(enabled=False),
        specs=[_spec("tag_files_sync")],
        rows=[_row(tmp_path / "p1", tags=["py"])],
    )
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched == []


def test_worker_skips_when_min_interval_unmet(tmp_path, monkeypatch) -> None:
    row = _row(tmp_path / "p1", tags=["py"])
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(enabled=True),
        specs=[_spec("tag_files_sync", refresh_min_interval_s=600.0)],
        rows=[row],
    )
    app.hook_refresh_last[(row.path, "tag_files_sync")] = time.time()
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched == []


def test_worker_ignores_specs_without_refresh_opt_in(tmp_path, monkeypatch) -> None:
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(enabled=True),
        specs=[_spec("tag_files_sync", refresh_enabled=False)],
        rows=[_row(tmp_path / "p1", tags=["py"])],
    )
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched == []


def test_worker_skips_tag_change_for_rows_with_no_tags(tmp_path, monkeypatch) -> None:
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(enabled=True),
        specs=[_spec("tag_files_sync")],
        rows=[_row(tmp_path / "p1", tags=[])],
    )
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched == []


def test_worker_honors_batch_size(tmp_path, monkeypatch) -> None:
    rows = [_row(tmp_path / f"p{i}", tags=["py"]) for i in range(5)]
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(
            enabled=True,
            worker=HookRefreshWorkerConfig(batch_size=2),
        ),
        specs=[_spec("tag_files_sync")],
        rows=rows,
    )
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    total_targets = sum(len(call["targets"]) for call in app.dispatched)
    assert total_targets == 2


def test_worker_skips_when_critical_job_active(tmp_path, monkeypatch) -> None:
    app = StubBApp(
        tmp_path,
        refresh_cfg=HookRefreshConfig(enabled=True),
        specs=[_spec("tag_files_sync")],
        rows=[_row(tmp_path / "p1", tags=["py"])],
    )
    app._critical_job_active = lambda: True
    _patch_dispatch(monkeypatch, app)
    _invoke_tick(app)
    assert app.dispatched == []
