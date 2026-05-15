from __future__ import annotations

from pathlib import Path

from homebase.core.models import HookInfo, HookRuntime, HookTarget
from homebase.hooks.api import HookContext
from homebase.hooks.bundled.post.delete import notify as delete_notify
from homebase.hooks.bundled.post.new_project import notify as new_project_notify
from homebase.hooks.bundled.post.rename import notify as rename_notify
from homebase.hooks.bundled.post.tag_change import notify as tag_change_notify


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


def _ctx(
    *,
    event: str,
    name: str,
    base_dir: Path,
    targets: tuple[HookTarget, ...],
    change: dict[str, object],
    notices: list[tuple[str, str]],
    config: dict[str, object] | None = None,
) -> HookContext:
    return HookContext(
        event=event,
        timing="post",
        view="active",
        base_dir=base_dir,
        targets=targets,
        change=change,
        runtime=HookRuntime(
            invoker="tui",
            homebase_version="0",
            now_iso="",
            now_ts=0,
            user="tester",
        ),
        hook=HookInfo(
            name=name,
            source="bundled",
            timing="post",
            event=event,
            config=dict(config or {}),
        ),
        add_event=lambda _path, _kind, _payload: None,
        notify=lambda text, level: notices.append((level, text)),
        status_update=lambda *_args, **_kwargs: None,
        log=lambda _text, _level: None,
        ask=lambda *_args, **_kwargs: None,
    )


def test_rename_notify_emits_old_and_new_name(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    target = tmp_path / "new"
    ctx = _ctx(
        event="rename",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(target),),
        change={"old_name": "old", "new_name": "new"},
        notices=notices,
    )
    rename_notify.run(ctx)
    assert notices == [("info", "renamed: old -> new")]


def test_tag_change_notify_summarises_added_and_removed(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    target = tmp_path / "p1"
    ctx = _ctx(
        event="tag_change",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(target),),
        change={"plan": {"alpha": "add", "beta": "remove", "gamma": "add"}},
        notices=notices,
    )
    tag_change_notify.run(ctx)
    assert notices == [("info", "tags on 1 project(s): +alpha,gamma -beta")]


def test_tag_change_notify_no_changes(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    ctx = _ctx(
        event="tag_change",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(tmp_path / "p1"),),
        change={"plan": {}},
        notices=notices,
    )
    tag_change_notify.run(ctx)
    assert notices == [("info", "tags on 1 project(s): no tag changes")]


def test_new_project_notify_includes_source_and_template(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    created = tmp_path / "proj"
    ctx = _ctx(
        event="new_project",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(created),),
        change={
            "created_path": created,
            "source": "git",
            "template": "python-uv",
        },
        notices=notices,
    )
    new_project_notify.run(ctx)
    assert notices == [("info", "new project: proj (source=git, template=python-uv)")]


def test_new_project_notify_minimal(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    created = tmp_path / "proj"
    ctx = _ctx(
        event="new_project",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(created),),
        change={"created_path": created, "source": "", "template": None},
        notices=notices,
    )
    new_project_notify.run(ctx)
    assert notices == [("info", "new project: proj")]


def test_delete_notify_uses_removed_paths(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    a = tmp_path / "a"
    b = tmp_path / "b"
    ctx = _ctx(
        event="delete",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(a), _target(b)),
        change={"removed_paths": [a, b]},
        notices=notices,
    )
    delete_notify.run(ctx)
    assert notices == [("info", "deleted 2 project(s)")]


def test_delete_notify_falls_back_to_targets(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    ctx = _ctx(
        event="delete",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(tmp_path / "a"),),
        change={},
        notices=notices,
    )
    delete_notify.run(ctx)
    assert notices == [("info", "deleted 1 project(s)")]


def test_notify_level_override_propagates(tmp_path: Path) -> None:
    notices: list[tuple[str, str]] = []
    ctx = _ctx(
        event="rename",
        name="notify",
        base_dir=tmp_path,
        targets=(_target(tmp_path / "n"),),
        change={"old_name": "old", "new_name": "new"},
        notices=notices,
        config={"level": "warn"},
    )
    rename_notify.run(ctx)
    assert notices == [("warn", "renamed: old -> new")]
