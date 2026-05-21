from __future__ import annotations

from pathlib import Path

import pytest

from homebase.metadata import api as metadata_api
from homebase.metadata.api import (
    clear_base_worktree,
    load_base_worktree,
    property_tokens,
    save_base_worktree,
    sync_tag_symlinks,
)


def test_sync_tag_symlinks_does_not_raise_import_error(tmp_path) -> None:
    err = sync_tag_symlinks(tmp_path)
    assert err is None


def test_property_tokens_memoizes_repeated_calls(monkeypatch) -> None:
    metadata_api._PROPERTY_TOKENS_CACHE.clear()
    calls = {"count": 0}
    real_tokens = metadata_api.property_utils.property_tokens

    def counting_tokens(*args, **kwargs):
        calls["count"] += 1
        return real_tokens(*args, **kwargs)

    monkeypatch.setattr(metadata_api.property_utils, "property_tokens", counting_tokens)

    property_tokens(["act"])
    property_tokens(["act"])
    assert calls["count"] == 1

    property_tokens(["doc"])
    assert calls["count"] == 2

    property_tokens(["act"])
    assert calls["count"] == 2


def test_save_and_load_base_worktree_roundtrip(tmp_path: Path) -> None:
    save_base_worktree(
        tmp_path,
        of="foo",
        branch="feature/auth",
        parent_path="/abs/foo/repo",
        gitdir_id="feature-auth",
    )

    block = load_base_worktree(tmp_path)
    assert block == {
        "of": "foo",
        "branch": "feature/auth",
        "parent_path": "/abs/foo/repo",
        "gitdir_id": "feature-auth",
    }


def test_save_base_worktree_minimal_block(tmp_path: Path) -> None:
    save_base_worktree(tmp_path, of="foo", branch="x")
    assert load_base_worktree(tmp_path) == {"of": "foo", "branch": "x"}


def test_save_base_worktree_rejects_empty_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_base_worktree(tmp_path, of="", branch="x")
    with pytest.raises(ValueError):
        save_base_worktree(tmp_path, of="foo", branch=" ")


def test_save_base_worktree_rejects_relative_parent_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        save_base_worktree(tmp_path, of="foo", branch="x", parent_path="rel/path")


def test_load_base_worktree_returns_none_when_absent(tmp_path: Path) -> None:
    (tmp_path / ".base.yaml").write_text("tags: [a]\n", encoding="utf-8")
    assert load_base_worktree(tmp_path) is None


def test_clear_base_worktree_removes_block(tmp_path: Path) -> None:
    save_base_worktree(tmp_path, of="foo", branch="x")
    clear_base_worktree(tmp_path)
    assert load_base_worktree(tmp_path) is None
