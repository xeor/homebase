from __future__ import annotations

import os
from pathlib import Path

import pytest

from homebase.core.models import HookInfo, HookRuntime, HookTarget
from homebase.hooks.api import HookContext
from homebase.hooks.bundled.post.tag_change.tag_files_sync import (
    HOMEBASE_DIR_NAME,
    TAG_FILES_DIR_NAME,
    refresh,
    run,
)


def _require_symlinks() -> None:
    if not getattr(os, "symlink", None):
        pytest.skip("symlinks not supported on this platform")


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


def _ctx(
    *,
    base_dir: Path,
    project: Path,
    added: list[str] | None = None,
    removed: list[str] | None = None,
    notices: list[tuple[str, str]] | None = None,
    statuses: list[tuple[str, str]] | None = None,
    events: list[tuple[Path, str, dict[str, object]]] | None = None,
    config: dict[str, object] | None = None,
) -> HookContext:
    notices = notices if notices is not None else []
    statuses = statuses if statuses is not None else []
    events = events if events is not None else []
    per_target = {
        project: {
            "before": [],
            "after": [],
            "added": list(added or []),
            "removed": list(removed or []),
        }
    }
    return HookContext(
        event="tag_change",
        timing="post",
        view="active",
        base_dir=base_dir,
        targets=(_target(project),),
        change={"plan": {}, "per_target": per_target},
        runtime=HookRuntime(invoker="tui", homebase_version="0", now_iso="", now_ts=0, user="t"),
        hook=HookInfo(
            name="tag_files_sync",
            source="bundled",
            timing="post",
            event="tag_change",
            config=dict(config or {}),
        ),
        add_event=lambda path, kind, payload: events.append((path, kind, payload)),
        notify=lambda text, level: notices.append((level, text)),
        status_update=lambda text, level: statuses.append((level, text)),
        log=lambda *_a, **_k: None,
        ask=lambda *_a, **_k: None,
    )


def _refresh_ctx(
    *,
    base_dir: Path,
    project: Path,
    current_tags: list[str],
    notices: list[tuple[str, str]] | None = None,
    statuses: list[tuple[str, str]] | None = None,
    logs: list[tuple[str, str]] | None = None,
    events: list[tuple[Path, str, dict[str, object]]] | None = None,
    config: dict[str, object] | None = None,
) -> HookContext:
    notices = notices if notices is not None else []
    statuses = statuses if statuses is not None else []
    logs = logs if logs is not None else []
    events = events if events is not None else []
    per_target = {project: {"current_tags": list(current_tags)}}
    return HookContext(
        event="tag_change",
        timing="post",
        view="active",
        base_dir=base_dir,
        targets=(_target(project),),
        change={"per_target": per_target},
        runtime=HookRuntime(invoker="tui", homebase_version="0", now_iso="", now_ts=0, user="t"),
        hook=HookInfo(
            name="tag_files_sync",
            source="bundled",
            timing="post",
            event="tag_change",
            config=dict(config or {}),
        ),
        add_event=lambda path, kind, payload: events.append((path, kind, payload)),
        notify=lambda text, level: notices.append((level, text)),
        status_update=lambda text, level: statuses.append((level, text)),
        log=lambda text, level: logs.append((level, text)),
        ask=lambda *_a, **_k: None,
        mode="refresh",
    )


def _make_tag_source(base_dir: Path, tag: str) -> Path:
    src = base_dir / HOMEBASE_DIR_NAME / TAG_FILES_DIR_NAME / tag
    src.mkdir(parents=True, exist_ok=True)
    return src


def _make_project(base_dir: Path, name: str = "proj") -> Path:
    project = base_dir / name
    project.mkdir()
    return project


def test_add_creates_symlinks_to_source(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "scripts").mkdir()
    (src / "scripts" / "lint.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (src / "README.md").write_text("hello", encoding="utf-8")
    project = _make_project(tmp_path)
    statuses: list[tuple[str, str]] = []
    events: list[tuple[Path, str, dict[str, object]]] = []

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        statuses=statuses,
        events=events,
    ))

    readme = project / "README.md"
    lint = project / "scripts" / "lint.sh"
    assert readme.is_symlink()
    assert lint.is_symlink()
    assert os.readlink(readme) == str((src / "README.md").resolve())
    assert os.readlink(lint) == str((src / "scripts" / "lint.sh").resolve())
    assert (project / "scripts").is_dir() and not (project / "scripts").is_symlink()
    assert any("linked 2 file" in text for _, text in statuses)
    rels = sorted(payload["rel"] for _, kind, payload in events if kind == "tag_files_linked")
    assert rels == ["README.md", "scripts/lint.sh"]


def test_source_edits_propagate_through_symlink(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    src_file = src / "config.toml"
    src_file.write_text("v1", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    src_file.write_text("v2", encoding="utf-8")

    assert (project / "config.toml").read_text(encoding="utf-8") == "v2"


def test_add_does_not_overwrite_real_file_and_warns(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "README.md").write_text("from-tag", encoding="utf-8")
    project = _make_project(tmp_path)
    (project / "README.md").write_text("user-edits", encoding="utf-8")
    notices: list[tuple[str, str]] = []

    run(_ctx(base_dir=tmp_path, project=project, added=["py"], notices=notices))

    assert not (project / "README.md").is_symlink()
    assert (project / "README.md").read_text(encoding="utf-8") == "user-edits"
    assert any("real file in the way" in text for _, text in notices)


def test_add_keeps_existing_symlink_pointing_elsewhere(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "config.toml").write_text("from-tag", encoding="utf-8")
    project = _make_project(tmp_path)
    other = tmp_path / "other.toml"
    other.write_text("other", encoding="utf-8")
    os.symlink(other, project / "config.toml")
    notices: list[tuple[str, str]] = []

    run(_ctx(base_dir=tmp_path, project=project, added=["py"], notices=notices))

    assert os.readlink(project / "config.toml") == str(other)
    assert any("symlink points elsewhere" in text for _, text in notices)


def test_add_is_idempotent_when_symlink_already_correct(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    notices: list[tuple[str, str]] = []
    statuses: list[tuple[str, str]] = []
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        notices=notices,
        statuses=statuses,
        events=events,
    ))

    assert notices == []
    assert statuses == []
    assert events == []


def test_remove_unlinks_only_matching_symlinks_and_cleans_empty_dir(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "scripts").mkdir()
    (src / "scripts" / "lint.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    statuses: list[tuple[str, str]] = []
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(
        base_dir=tmp_path,
        project=project,
        removed=["py"],
        statuses=statuses,
        events=events,
    ))

    assert not (project / "scripts" / "lint.sh").exists()
    assert not (project / "scripts").exists()
    assert any(kind == "tag_files_unlinked" for _, kind, _ in events)
    assert any("unlinked 1 file" in text for _, text in statuses)


def test_remove_keeps_real_file_replacing_symlink(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "lint.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    (project / "lint.sh").unlink()
    (project / "lint.sh").write_text("now real", encoding="utf-8")
    notices: list[tuple[str, str]] = []

    run(_ctx(base_dir=tmp_path, project=project, removed=["py"], notices=notices))

    assert (project / "lint.sh").is_file()
    assert (project / "lint.sh").read_text(encoding="utf-8") == "now real"
    assert any("replaced by real file" in text for _, text in notices)


def test_remove_keeps_symlink_repointed_elsewhere(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "config.toml").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    other = tmp_path / "other.toml"
    other.write_text("other", encoding="utf-8")
    (project / "config.toml").unlink()
    os.symlink(other, project / "config.toml")
    notices: list[tuple[str, str]] = []

    run(_ctx(base_dir=tmp_path, project=project, removed=["py"], notices=notices))

    assert os.readlink(project / "config.toml") == str(other)
    assert any("symlink points elsewhere" in text for _, text in notices)


def test_remove_keeps_non_empty_dir(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "scripts").mkdir()
    (src / "scripts" / "lint.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    (project / "scripts" / "user.sh").write_text("user", encoding="utf-8")

    run(_ctx(base_dir=tmp_path, project=project, removed=["py"]))

    assert not (project / "scripts" / "lint.sh").exists()
    assert (project / "scripts" / "user.sh").exists()
    assert (project / "scripts").is_dir()


def test_missing_tag_dir_is_silent_noop(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    notices: list[tuple[str, str]] = []
    statuses: list[tuple[str, str]] = []

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["nope"],
        removed=["also-nope"],
        notices=notices,
        statuses=statuses,
    ))

    assert notices == []
    assert statuses == []


def test_path_traversal_in_tag_name_is_rejected(tmp_path: Path) -> None:
    _require_symlinks()
    other = tmp_path / "outside"
    other.mkdir()
    (other / "leak.txt").write_text("secret", encoding="utf-8")
    (tmp_path / HOMEBASE_DIR_NAME / TAG_FILES_DIR_NAME).mkdir(parents=True)
    project = _make_project(tmp_path)

    run(_ctx(base_dir=tmp_path, project=project, added=["../../outside"]))

    assert not (project / "leak.txt").exists()


def test_symlink_in_source_is_skipped(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    os.symlink(outside, src / "link.txt")
    project = _make_project(tmp_path)

    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))

    assert not (project / "link.txt").exists()


def test_dry_run_makes_no_changes(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "x.txt").write_text("hi", encoding="utf-8")
    project = _make_project(tmp_path)
    statuses: list[tuple[str, str]] = []
    events: list[tuple[Path, str, dict[str, object]]] = []

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        config={"dry_run": True},
        statuses=statuses,
        events=events,
    ))

    assert not (project / "x.txt").exists()
    assert events == []
    assert any("would link" in text for _, text in statuses)


def test_root_config_relative_to_base(tmp_path: Path) -> None:
    _require_symlinks()
    custom_root = tmp_path / "shared" / "tag-overlays"
    src = custom_root / "py"
    src.mkdir(parents=True)
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        config={"root": "shared/tag-overlays"},
    ))

    assert (project / "x.txt").is_symlink()
    assert os.readlink(project / "x.txt") == str((src / "x.txt").resolve())


def test_root_config_absolute_path(tmp_path: Path) -> None:
    _require_symlinks()
    custom_root = tmp_path / "elsewhere" / "tags"
    src = custom_root / "py"
    src.mkdir(parents=True)
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        config={"root": str(custom_root)},
    ))

    assert (project / "x.txt").is_symlink()
    assert os.readlink(project / "x.txt") == str((src / "x.txt").resolve())


def test_root_config_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_symlinks()
    home = tmp_path / "fakehome"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    src = home / "tag-overlays" / "py"
    src.mkdir(parents=True)
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        config={"root": "~/tag-overlays"},
    ))

    assert os.readlink(project / "x.txt") == str((src / "x.txt").resolve())


def test_explicit_root_missing_warns_and_skips(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    notices: list[tuple[str, str]] = []

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        config={"root": "does/not/exist"},
        notices=notices,
    ))

    assert any("root not a usable directory" in text for _, text in notices)


def test_default_root_missing_is_silent(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    notices: list[tuple[str, str]] = []
    statuses: list[tuple[str, str]] = []

    run(_ctx(
        base_dir=tmp_path,
        project=project,
        added=["py"],
        notices=notices,
        statuses=statuses,
    ))

    assert notices == []
    assert statuses == []


def test_dir_in_source_with_file_in_dest_warns_type_conflict(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "scripts").mkdir()
    (src / "scripts" / "x.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    (project / "scripts").write_text("user wrote a file here", encoding="utf-8")
    notices: list[tuple[str, str]] = []

    run(_ctx(base_dir=tmp_path, project=project, added=["py"], notices=notices))

    assert (project / "scripts").is_file()
    assert any("type conflict" in text for _, text in notices)


def test_refresh_links_new_source_files(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "first.txt").write_text("first", encoding="utf-8")
    project = _make_project(tmp_path)
    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    (src / "second.txt").write_text("second", encoding="utf-8")

    refresh(_refresh_ctx(base_dir=tmp_path, project=project, current_tags=["py"]))

    assert (project / "second.txt").is_symlink()
    assert os.readlink(project / "second.txt") == str((src / "second.txt").resolve())


def test_refresh_is_idempotent_when_nothing_changed(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    run(_ctx(base_dir=tmp_path, project=project, added=["py"]))
    notices: list[tuple[str, str]] = []
    statuses: list[tuple[str, str]] = []
    events: list[tuple[Path, str, dict[str, object]]] = []

    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        notices=notices,
        statuses=statuses,
        events=events,
    ))

    assert notices == []
    assert statuses == []
    assert events == []


def test_refresh_prunes_orphan_when_source_deleted(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "extra.txt").write_text("extra", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    # The TUI test harness collects events but the real append_base_log
    # was bypassed (test ctx records into a list). For refresh's
    # orphan detection to fire, the events must actually be in
    # .base.yaml. Replay them now.
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    (src / "extra.txt").unlink()

    refresh_events: list[tuple[Path, str, dict[str, object]]] = []
    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        events=refresh_events,
    ))

    assert not (project / "extra.txt").exists()
    assert any(kind == "tag_files_unlinked" for _, kind, _ in refresh_events)


def test_refresh_keeps_repointed_symlink(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    other = tmp_path / "other.txt"
    other.write_text("other", encoding="utf-8")
    (project / "x.txt").unlink()
    os.symlink(other, project / "x.txt")
    (src / "x.txt").unlink()

    logs: list[tuple[str, str]] = []
    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        logs=logs,
    ))

    assert os.readlink(project / "x.txt") == str(other)
    assert any("symlink points elsewhere" in text for _, text in logs)


def test_refresh_keeps_real_file_replacing_symlink(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "x.txt").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    (project / "x.txt").unlink()
    (project / "x.txt").write_text("user now", encoding="utf-8")
    (src / "x.txt").unlink()

    logs: list[tuple[str, str]] = []
    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        logs=logs,
    ))

    assert (project / "x.txt").is_file()
    assert (project / "x.txt").read_text(encoding="utf-8") == "user now"
    assert any("replaced by real file" in text for _, text in logs)


def test_refresh_skips_when_root_missing(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    notices: list[tuple[str, str]] = []

    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        config={"root": "does/not/exist"},
        notices=notices,
    ))

    assert any("root not a usable directory" in text for _, text in notices)


def test_refresh_dry_run_does_not_mutate(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "extra.txt").write_text("extra", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    (src / "extra.txt").unlink()

    refresh(_refresh_ctx(
        base_dir=tmp_path,
        project=project,
        current_tags=["py"],
        config={"dry_run": True},
    ))

    # Symlink still exists (dry-run does not actually unlink)
    assert (project / "extra.txt").is_symlink()


def test_remove_unlinks_when_source_file_was_deleted_first(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "extra.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    # User deletes source file before removing the tag
    (src / "extra.sh").unlink()

    refresh_events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(
        base_dir=tmp_path,
        project=project,
        removed=["py"],
        events=refresh_events,
    ))

    assert not (project / "extra.sh").exists()
    assert any(kind == "tag_files_unlinked" for _, kind, _ in refresh_events)


def test_remove_unlinks_when_entire_source_dir_was_deleted(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "scripts").mkdir()
    (src / "scripts" / "lint.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    # User deletes the entire source dir before removing the tag
    import shutil
    shutil.rmtree(src)

    run(_ctx(base_dir=tmp_path, project=project, removed=["py"]))

    assert not (project / "scripts" / "lint.sh").exists()
    assert not (project / "scripts").exists()


def test_remove_with_deleted_source_keeps_user_replaced_files(tmp_path: Path) -> None:
    _require_symlinks()
    src = _make_tag_source(tmp_path, "py")
    (src / "lint.sh").write_text("x", encoding="utf-8")
    project = _make_project(tmp_path)
    events: list[tuple[Path, str, dict[str, object]]] = []
    run(_ctx(base_dir=tmp_path, project=project, added=["py"], events=events))
    from homebase.metadata.api import append_base_log
    for path, kind, payload in events:
        append_base_log(path, kind, payload)
    # User replaces symlink with a real file, then deletes source
    (project / "lint.sh").unlink()
    (project / "lint.sh").write_text("now real", encoding="utf-8")
    (src / "lint.sh").unlink()

    notices: list[tuple[str, str]] = []
    run(_ctx(base_dir=tmp_path, project=project, removed=["py"], notices=notices))

    assert (project / "lint.sh").is_file()
    assert (project / "lint.sh").read_text(encoding="utf-8") == "now real"
    assert any("replaced by real file" in text for _, text in notices)
