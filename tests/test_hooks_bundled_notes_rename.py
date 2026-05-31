from __future__ import annotations

from pathlib import Path

from homebase.core.models import HookInfo, HookRuntime, HookTarget
from homebase.hooks.api import HookContext
from homebase.hooks.bundled.post.rename.notes_rename import run


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
        modified_ts=0,
        created_ts=0,
        archived_ts=0,
        git_branch="",
        git_dirty="",
    )


def _ctx(base_dir: Path, target: Path, change: dict[str, object], events: list[tuple[Path, str, dict[str, object]]], notices: list[tuple[str, str]]) -> HookContext:
    return HookContext(
        event="rename",
        timing="post",
        view="active",
        base_dir=base_dir,
        targets=(_target(target),),
        change=change,
        runtime=HookRuntime(
            invoker="tui",
            homebase_version="0",
            now_iso="",
            now_ts=0,
            user="tester",
        ),
        hook=HookInfo(
            name="notes_rename",
            source="bundled",
            timing="post",
            event="rename",
            config={},
        ),
        add_event=lambda path, kind, payload: events.append((path, kind, payload)),
        notify=lambda text, level: notices.append((level, text)),
        status_update=lambda *_args, **_kwargs: None,
        log=lambda _text, _level: None,
        ask=lambda *_args, **_kwargs: None,
    )


def test_notes_rename_moves_file_and_emits_event(tmp_path: Path) -> None:
    project = tmp_path / "p1"
    project.mkdir()
    old_note = tmp_path / "old.md"
    old_note.write_text("x", encoding="utf-8")
    new_note = tmp_path / "new.md"
    events: list[tuple[Path, str, dict[str, object]]] = []
    notices: list[tuple[str, str]] = []
    ctx = _ctx(
        tmp_path,
        project,
        {
            "old_note_path": old_note,
            "new_note_path": new_note,
            "rendered_note_cmd": "",
        },
        events,
        notices,
    )
    run(ctx)
    assert not old_note.exists()
    assert new_note.exists()
    assert events and events[0][1] == "note_rename"
    assert notices == []


def test_notes_rename_failed_command_notifies(tmp_path: Path) -> None:
    project = tmp_path / "p1"
    project.mkdir()
    old_note = tmp_path / "old.md"
    old_note.write_text("x", encoding="utf-8")
    new_note = tmp_path / "new.md"
    events: list[tuple[Path, str, dict[str, object]]] = []
    notices: list[tuple[str, str]] = []
    ctx = _ctx(
        tmp_path,
        project,
        {
            "old_note_path": old_note,
            "new_note_path": new_note,
            "rendered_note_cmd": "exit 7",
        },
        events,
        notices,
    )
    run(ctx)
    assert old_note.exists()
    assert not new_note.exists()
    assert events == []
    assert notices and notices[0][0] == "warn"
