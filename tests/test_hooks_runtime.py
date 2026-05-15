from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import HookSpec, HookTarget
from homebase.hooks.runtime import dispatch_post, dispatch_post_cli
from homebase.metadata.api import load_base_data


def _spec(name: str, *, views: tuple[str, ...] = (), slow_warn_s: float = 30.0) -> HookSpec:
    return HookSpec(
        timing="post",
        event="rename",
        name=name,
        source="custom",
        enabled=True,
        views=views,
        config={},
        slow_warn_s=slow_warn_s,
    )


def _target(path: Path) -> HookTarget:
    return HookTarget(
        path=path,
        name=path.name,
        archived=False,
        tags=[],
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


class FakeApp:
    def __init__(self, base_dir: Path, specs: list[HookSpec]) -> None:
        self.base_dir = base_dir
        self.ctx = SimpleNamespace(hook_specs={("post", "rename"): specs})
        self.hook_recent: dict[tuple[str, str], list[object]] = {}
        self.hook_running: dict[str, float] = {}
        self.view_mode = "active"
        self.notifications: list[tuple[str, str]] = []
        self.logs: list[tuple[str, str]] = []
        self.errors: list[tuple[str, str]] = []
        self.busy_starts: list[str] = []
        self.busy_stops = 0
        self.expected_stops = len(specs)
        self.done = threading.Event()

    def call_from_thread(self, fn, *args):
        return fn(*args)

    def _log(self, text: str, level: str = "info") -> None:
        self.logs.append((level, text))

    def _set_runtime_status(self, text: str, level: str = "info", _ttl_s: float = 0.0) -> None:
        self.notifications.append((level, text))

    def _show_runtime_error(self, context: str, exc: BaseException, _traceback_tail: str = "") -> None:
        self.errors.append((context, str(exc)))

    def _busy_start(self, label: str) -> None:
        self.busy_starts.append(label)

    def _busy_stop(self) -> None:
        self.busy_stops += 1
        if self.busy_stops >= self.expected_stops:
            self.done.set()


def _write_hook(base_dir: Path, name: str, body: str) -> None:
    path = base_dir / ".homebase" / "hooks" / "post" / "rename" / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_dispatch_post_empty_specs_noop(tmp_path: Path) -> None:
    app = FakeApp(tmp_path, [])
    dispatch_post(app, event="rename", targets=[], change={}, view="active")
    assert app.busy_starts == []


def test_dispatch_post_notify_routes_to_status(tmp_path: Path) -> None:
    _write_hook(tmp_path, "notify_me", "def run(ctx):\n    ctx.notify('hi', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("notify_me")])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    assert ("info", "hi") in app.notifications


def test_dispatch_post_add_event_appends_log(tmp_path: Path) -> None:
    _write_hook(
        tmp_path,
        "event_me",
        "def run(ctx):\n    ctx.add_event(ctx.targets[0].path, 'hook_custom', {'ok': True})\n",
    )
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("event_me")])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    data = load_base_data(project)
    log_raw = data.get("log", {})
    assert isinstance(log_raw, dict)
    log_items = log_raw.get("events", [])
    assert isinstance(log_items, list)
    assert any(isinstance(entry, dict) and entry.get("_event") == "hook_custom" for entry in log_items)


def test_dispatch_post_error_contained_and_next_hook_runs(tmp_path: Path) -> None:
    _write_hook(tmp_path, "boom", "def run(ctx):\n    raise ValueError('boom')\n")
    _write_hook(tmp_path, "after", "def run(ctx):\n    ctx.notify('after', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("boom"), _spec("after")])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    assert app.errors
    assert ("info", "after") in app.notifications
    records = app.hook_recent[("post", "rename")]
    assert records[0].ok is False
    assert records[1].ok is True


def test_dispatch_post_runs_hooks_in_order(tmp_path: Path) -> None:
    _write_hook(tmp_path, "first", "def run(ctx):\n    ctx.log('first', 'info')\n")
    _write_hook(tmp_path, "second", "def run(ctx):\n    ctx.log('second', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("first"), _spec("second")])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    assert [text for _level, text in app.logs] == ["first", "second"]


def test_dispatch_post_respects_view_filter(tmp_path: Path) -> None:
    _write_hook(tmp_path, "archive_only", "def run(ctx):\n    ctx.notify('archive', 'info')\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("archive_only", views=("archive",))])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    time.sleep(0.1)
    assert app.notifications == []


def test_dispatch_post_emits_slow_warning(tmp_path: Path) -> None:
    _write_hook(tmp_path, "slow", "import time\ndef run(ctx):\n    time.sleep(0.25)\n")
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("slow", slow_warn_s=0.1)])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    assert any("still running" in text for _level, text in app.notifications)


def test_dispatch_post_captures_stdout_stderr(tmp_path: Path) -> None:
    _write_hook(
        tmp_path,
        "prints",
        "import sys\ndef run(ctx):\n    print('out-line')\n    print('err-line', file=sys.stderr)\n",
    )
    project = tmp_path / "p1"
    project.mkdir()
    app = FakeApp(tmp_path, [_spec("prints")])
    dispatch_post(app, event="rename", targets=[_target(project)], change={}, view="active")
    assert app.done.wait(2.0)
    text_lines = [text for _level, text in app.logs]
    assert any("stdout: out-line" in line for line in text_lines)
    assert any("stderr: err-line" in line for line in text_lines)


def test_dispatch_post_cli_runs_hook_and_updates_base_log(tmp_path: Path) -> None:
    _write_hook(
        tmp_path,
        "cli_event",
        "def run(ctx):\n    ctx.add_event(ctx.targets[0].path, 'cli_hook_event', {'ok': True})\n",
    )
    project = tmp_path / "p1"
    project.mkdir()
    spec = HookSpec(
        timing="post",
        event="rename",
        name="cli_event",
        source="custom",
        enabled=True,
        views=(),
        config={},
        slow_warn_s=30.0,
    )
    dispatch_post_cli(
        base_dir=tmp_path,
        hook_specs={("post", "rename"): [spec]},
        event="rename",
        targets=[_target(project)],
        change={},
        view="active",
    )
    data = load_base_data(project)
    events = data.get("log", {}).get("events", []) if isinstance(data.get("log", {}), dict) else []
    assert any(isinstance(entry, dict) and entry.get("_event") == "cli_hook_event" for entry in events)
