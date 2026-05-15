from __future__ import annotations

from pathlib import Path

from homebase.core.models import HookInfo, HookRuntime, HookTarget
from homebase.hooks.api import HookContext
from homebase.hooks.bundled.post import _tag_symlink_sync_common as sync_common


def _ctx(base_dir: Path, notices: list[tuple[str, str]], logs: list[tuple[str, str]]) -> HookContext:
    target = HookTarget(
        path=base_dir,
        name=base_dir.name,
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
    return HookContext(
        event="tag_change",
        timing="post",
        view="active",
        base_dir=base_dir,
        targets=(target,),
        change={},
        runtime=HookRuntime(
            invoker="tui",
            homebase_version="0",
            now_iso="",
            now_ts=0,
            user="tester",
        ),
        hook=HookInfo(
            name="tag_symlink_sync",
            source="bundled",
            timing="post",
            event="tag_change",
            config={},
        ),
        add_event=lambda *_args, **_kwargs: None,
        notify=lambda text, level: notices.append((level, text)),
        log=lambda text, level: logs.append((level, text)),
        ask=lambda *_args, **_kwargs: None,
    )


def test_tag_symlink_sync_success_notifies_info(tmp_path: Path, monkeypatch) -> None:
    notices: list[tuple[str, str]] = []
    logs: list[tuple[str, str]] = []
    monkeypatch.setattr(sync_common, "sync_tag_symlinks", lambda _bd: None)
    sync_common.run_tag_symlink_sync(_ctx(tmp_path, notices, logs))
    assert notices == [("info", "tag symlink sync complete")]
    assert logs == []


def test_tag_symlink_sync_error_notifies_and_logs(tmp_path: Path, monkeypatch) -> None:
    notices: list[tuple[str, str]] = []
    logs: list[tuple[str, str]] = []
    monkeypatch.setattr(sync_common, "sync_tag_symlinks", lambda _bd: "boom")
    sync_common.run_tag_symlink_sync(_ctx(tmp_path, notices, logs))
    assert notices and notices[0][0] == "warn"
    assert logs and logs[0][0] == "warn"
