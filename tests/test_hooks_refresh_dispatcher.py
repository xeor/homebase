from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import HookSpec, HookTarget
from homebase.hooks.refresh import (
    _build_refresh_change,
    dispatch_refresh_cli,
    dispatch_refresh_tui,
)
from homebase.metadata.api import load_base_data


def _spec(
    name: str,
    *,
    event: str = "tag_change",
    enabled: bool = True,
    views: tuple[str, ...] = (),
    refresh_enabled: bool = True,
) -> HookSpec:
    return HookSpec(
        timing="post",
        event=event,
        name=name,
        source="custom",
        enabled=enabled,
        views=views,
        config={},
        slow_warn_s=30.0,
        refresh_enabled=refresh_enabled,
        refresh_min_interval_s=60.0,
    )


def _target(path: Path, *, tags: list[str] | None = None) -> HookTarget:
    return HookTarget(
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
        last_modified_ts=0,
        created_ts=0,
        archived_ts=0,
        git_branch="",
        git_dirty="",
    )


def _write_hook(base_dir: Path, event: str, name: str, body: str) -> None:
    path = base_dir / ".homebase" / "hooks" / "post" / event / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class FakeApp:
    def __init__(self, base_dir: Path, specs: list[HookSpec], *, view: str = "active") -> None:
        self.base_dir = base_dir
        self.view_mode = view
        spec_map: dict[tuple[str, str], list[HookSpec]] = {}
        for spec in specs:
            spec_map.setdefault((spec.timing, spec.event), []).append(spec)
        self.ctx = SimpleNamespace(hook_specs=spec_map)
        self.hook_running: dict[str, float] = {}
        self.logs: list[tuple[str, str]] = []
        self.notifications: list[tuple[str, str]] = []
        self.toasts: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.busy_starts: list[str] = []
        self.busy_stops = 0
        self.done = threading.Event()
        self.expected_stops = 0

    def call_from_thread(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    def _log(self, text: str, level: str = "info") -> None:
        self.logs.append((level, text))

    def _set_runtime_status(self, text: str, level: str = "info", _ttl_s: float = 0.0) -> None:
        self.notifications.append((level, text))

    def notify(self, text: str, *, severity: str = "information", timeout: float = 0.0) -> None:
        self.toasts.append((severity, text))

    def _show_runtime_error(self, context: str, exc: BaseException, _tb: str = "") -> None:
        self.errors.append((context, str(exc)))

    def _busy_start(self, label: str) -> None:
        self.busy_starts.append(label)

    def _busy_stop(self) -> None:
        self.busy_stops += 1
        if self.busy_stops >= self.expected_stops:
            self.done.set()


def test_build_refresh_change_for_tag_change_carries_current_tags(tmp_path: Path) -> None:
    target = _target(tmp_path / "p1", tags=["py", "scratch"])
    change = _build_refresh_change("tag_change", target)
    assert change == {"per_target": {target.path: {"current_tags": ["py", "scratch"]}}}


def test_build_refresh_change_other_events_return_empty(tmp_path: Path) -> None:
    target = _target(tmp_path / "p1", tags=["py"])
    assert _build_refresh_change("rename", target) == {}
    assert _build_refresh_change("delete", target) == {}


def test_tui_dispatch_skips_modules_without_refresh(tmp_path: Path) -> None:
    _write_hook(tmp_path, "tag_change", "no_refresh", "def run(ctx):\n    ctx.log('event-only', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("no_refresh")])
    app.expected_stops = 0
    dispatch_refresh_tui(app, targets=[_target(project)], view="active")
    assert app.busy_starts == []


def test_tui_dispatch_runs_refresh_and_records_events(tmp_path: Path) -> None:
    body = (
        "def run(ctx):\n"
        "    pass\n"
        "def refresh(ctx):\n"
        "    target = ctx.targets[0]\n"
        "    tags = ctx.change['per_target'][target.path]['current_tags']\n"
        "    ctx.add_event(target.path, 'refresh_seen', {'tags': list(tags), 'mode': ctx.mode})\n"
    )
    _write_hook(tmp_path, "tag_change", "with_refresh", body)
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("with_refresh")])
    app.expected_stops = 1
    dispatch_refresh_tui(app, targets=[_target(project, tags=["py"])], view="active")
    assert app.done.wait(2.0)
    data = load_base_data(project)
    events = data.get("log", {}).get("events", [])
    kinds = [e.get("_event") for e in events if isinstance(e, dict)]
    assert "hook_refresh_started" in kinds
    assert "hook_refresh_done" in kinds
    assert "refresh_seen" in kinds
    refresh_seen = next(e for e in events if isinstance(e, dict) and e.get("_event") == "refresh_seen")
    assert refresh_seen.get("tags") == ["py"]
    assert refresh_seen.get("mode") == "refresh"


def test_tui_dispatch_hook_filter_restricts_specs(tmp_path: Path) -> None:
    _write_hook(tmp_path, "tag_change", "alpha", "def run(c):\n    pass\ndef refresh(c):\n    c.log('a', 'info')\n")
    _write_hook(tmp_path, "tag_change", "beta", "def run(c):\n    pass\ndef refresh(c):\n    c.log('b', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("alpha"), _spec("beta")])
    app.expected_stops = 1
    dispatch_refresh_tui(
        app,
        targets=[_target(project)],
        view="active",
        hook_filter=("alpha",),
    )
    assert app.done.wait(2.0)
    assert ("info", "a") in app.logs
    assert ("info", "b") not in app.logs


def test_tui_dispatch_swallows_hook_errors(tmp_path: Path) -> None:
    _write_hook(
        tmp_path,
        "tag_change",
        "boom",
        "def run(c):\n    pass\ndef refresh(c):\n    raise ValueError('boom')\n",
    )
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("boom")])
    app.expected_stops = 1
    dispatch_refresh_tui(app, targets=[_target(project)], view="active")
    assert app.done.wait(2.0)
    assert app.errors
    data = load_base_data(project)
    events = data.get("log", {}).get("events", [])
    done = [e for e in events if isinstance(e, dict) and e.get("_event") == "hook_refresh_done"]
    assert done and done[-1].get("error") == "boom"


def test_tui_dispatch_require_refresh_enabled_skips_when_off(tmp_path: Path) -> None:
    _write_hook(tmp_path, "tag_change", "off", "def run(c):\n    pass\ndef refresh(c):\n    c.log('hit', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    spec = _spec("off", refresh_enabled=False)
    app = FakeApp(tmp_path, [spec])
    app.expected_stops = 0
    dispatch_refresh_tui(
        app,
        targets=[_target(project)],
        view="active",
        require_refresh_enabled=True,
    )
    assert ("info", "hit") not in app.logs


def test_cli_dispatch_runs_refresh(tmp_path: Path) -> None:
    body = (
        "def run(ctx):\n"
        "    pass\n"
        "def refresh(ctx):\n"
        "    target = ctx.targets[0]\n"
        "    ctx.add_event(target.path, 'refresh_seen', {'mode': ctx.mode})\n"
    )
    _write_hook(tmp_path, "tag_change", "cli_refresh", body)
    project = tmp_path / "p1"
    project.mkdir()
    spec = _spec("cli_refresh")
    hook_specs = {("post", "tag_change"): [spec]}
    dispatch_refresh_cli(
        base_dir=tmp_path,
        hook_specs=hook_specs,
        targets=[_target(project)],
        view="active",
    )
    data = load_base_data(project)
    events = data.get("log", {}).get("events", [])
    kinds = [e.get("_event") for e in events if isinstance(e, dict)]
    assert "hook_refresh_started" in kinds
    assert "hook_refresh_done" in kinds
    assert "refresh_seen" in kinds


def test_cli_dispatch_skips_without_refresh(tmp_path: Path) -> None:
    _write_hook(tmp_path, "tag_change", "evt_only", "def run(c):\n    c.log('hit', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    spec = _spec("evt_only")
    hook_specs = {("post", "tag_change"): [spec]}
    dispatch_refresh_cli(
        base_dir=tmp_path,
        hook_specs=hook_specs,
        targets=[_target(project)],
        view="active",
    )
    data = load_base_data(project)
    events = data.get("log", {}).get("events", [])
    kinds = [e.get("_event") for e in events if isinstance(e, dict)]
    assert "hook_refresh_started" not in kinds
