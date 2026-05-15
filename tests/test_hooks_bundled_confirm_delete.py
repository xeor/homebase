from __future__ import annotations

from pathlib import Path

from homebase.core.models import HookInfo, HookRuntime, HookTarget
from homebase.hooks.api import HookContext
from homebase.hooks.bundled.pre.delete.confirm_delete import run


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


def _ctx(path: Path, *, answer: str | None):
    return HookContext(
        event="delete",
        timing="pre",
        view="active",
        base_dir=path.parent,
        targets=(_target(path),),
        change={},
        runtime=HookRuntime(invoker="tui", homebase_version="0", now_iso="", now_ts=0, user="u"),
        hook=HookInfo(
            name="confirm_delete",
            source="bundled",
            timing="pre",
            event="delete",
            config={"require_confirm": True},
        ),
        add_event=lambda *_args, **_kwargs: None,
        notify=lambda *_args, **_kwargs: None,
        log=lambda *_args, **_kwargs: None,
        ask=lambda **_kwargs: answer,
    )


def test_confirm_delete_allows_yes(tmp_path: Path) -> None:
    out = run(_ctx(tmp_path / "p1", answer="yes"))
    assert out is None


def test_confirm_delete_cancels_on_none(tmp_path: Path) -> None:
    out = run(_ctx(tmp_path / "p1", answer=None))
    assert out is not None
    assert out.decision == "cancel"
