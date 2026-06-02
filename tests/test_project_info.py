from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from homebase.workspace import project_info as project_info


@dataclass
class Row:
    name: str
    path: Path
    archived: bool = False
    wip: bool = False
    suffix: str | None = None
    created_ts: int = 0
    opened_ts: int = 0
    last_ts: int = 0
    src: str = "fs"
    branch: str = "main"
    dirty: str = ""
    stale: bool = False
    cache_age_s: int = 0
    last_cached_ts: int = 0
    last_reconciled_ts: int = 0
    tags: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    description: str = ""
    repo_dir: str = ""
    worktree_of: str = ""


def _build(row: Row, **overrides):
    kwargs = dict(
        base_marker_file=".base.yaml",
        legacy_base_marker_file=".base.yml",
        color_age_unit_hex="#7CFC7C",
        wip_hotkey=None,
        include_meta_checks=False,
        fmt_iso=lambda _ts: "",
        fmt_age_short=lambda _ts, _now=None: "-0m",
        property_display_lines=lambda _keys: [],
        base_meta_issues=lambda _path: [],
        load_base_data=lambda _path: {},
        run_out=lambda *_args: "",
    )
    kwargs.update(overrides)
    return project_info.build_project_info_text(row, **kwargs)


def test_build_project_info_text_contains_name_and_description(tmp_path: Path) -> None:
    row = Row(name="proj", path=tmp_path / "proj", description="desc")
    text = _build(row)
    assert "proj" in text
    assert "desc" in text


def test_build_project_info_renders_cached_meta_health_warning(tmp_path: Path) -> None:
    row = Row(
        name="ghost",
        path=tmp_path / "ghost",
        archived=True,
        properties=["warn"],
    )
    text = _build(
        row,
        cached_meta_health=("warning", "missing .base.yaml; tags must be a list"),
    )
    assert "WARNING" in text
    assert "missing .base.yaml" in text
    assert "tags must be a list" in text
    assert "deferred" not in text


def test_build_project_info_renders_cached_meta_health_error(tmp_path: Path) -> None:
    row = Row(
        name="ghost",
        path=tmp_path / "ghost",
        archived=True,
        properties=["err"],
    )
    text = _build(
        row,
        cached_meta_health=("error", "invalid yaml: bad token"),
    )
    assert "ERROR" in text
    assert "invalid yaml" in text


def test_build_project_info_falls_back_when_no_cache(tmp_path: Path) -> None:
    row = Row(
        name="ghost",
        path=tmp_path / "ghost",
        archived=True,
        properties=["warn"],
    )
    text = _build(row, cached_meta_health=None)
    assert "loading" in text or "flagged" in text


def test_build_project_info_shows_repo_path_for_repo_dir_repo(tmp_path: Path) -> None:
    row = Row(name="foo", path=tmp_path / "foo", repo_dir="repo")
    text = _build(row)
    assert "repo path" in text
    assert str(tmp_path / "foo" / "repo") in text


def test_build_project_info_shows_flat_repo_dir_hint(tmp_path: Path) -> None:
    row = Row(name="flat", path=tmp_path / "flat", repo_dir=".")
    text = _build(row)
    assert ".git at project root" in text


def test_build_project_info_renders_worktree_lineage(tmp_path: Path) -> None:
    row = Row(
        name="foo-featx",
        path=tmp_path / "foo-featx",
        repo_dir="repo",
        worktree_of="foo",
    )

    def _meta(_path):
        return {
            "worktree": {
                "of": "foo",
                "branch": "featx",
                "parent_path": str(tmp_path / "foo" / "repo"),
                "gitdir_id": "featx",
            }
        }

    text = _build(row, load_base_data=_meta)
    assert "worktree of" in text
    assert "foo" in text
    assert "worktree branch" in text
    assert "featx" in text
    assert "parent repo" in text
    assert str(tmp_path / "foo" / "repo") in text
    assert "parent admin" in text


def test_build_project_info_omits_worktree_block_when_meta_unavailable(
    tmp_path: Path,
) -> None:
    row = Row(
        name="foo-featx",
        path=tmp_path / "foo-featx",
        repo_dir="repo",
        worktree_of="foo",
    )
    # load_base_data returns no worktree block — only the row-level
    # 'worktree of: foo' line appears, no parent_path detail.
    text = _build(row, load_base_data=lambda _p: {})
    assert "worktree of" in text
    assert "parent repo" not in text


def test_build_project_info_meta_checks_renders_issue_fix_hints(tmp_path: Path) -> None:
    row = Row(name="proj", path=tmp_path / "proj")
    issues = [
        ("error", "legacy_only", "legacy .base.yml present"),
        ("warning", "missing_meta", ".base.yaml missing"),
        ("error", "invalid_yaml", "bad yaml"),
        ("error", "invalid_root", "root must be mapping"),
        ("warning", "schema_warn", "unexpected key x"),
        ("warning", "other", "misc warn"),
    ]
    text = _build(
        row,
        include_meta_checks=True,
        base_meta_issues=lambda _path: issues,
        load_base_data=lambda _p: {"tags": ["a"]},
    )
    assert "ERROR" in text and "WARNING" in text
    assert "legacy_only" in text
    assert "missing_meta" in text
    assert "invalid_yaml" in text
    assert "invalid_root" in text
    assert "schema_warn" in text
    assert ".base.yaml keys" in text


def test_build_project_info_renders_wip_with_hotkey(tmp_path: Path) -> None:
    row = Row(name="proj", path=tmp_path / "proj", wip=True)
    text = _build(row, wip_hotkey=2)
    assert "wip" in text
    assert "alt+2" in text


def test_build_project_info_renders_dirty_marker(tmp_path: Path) -> None:
    row = Row(name="proj", path=tmp_path / "proj", branch="main", dirty="*")
    text = _build(row)
    assert "main" in text
    assert "*" in text


def test_build_project_info_runs_git_log_for_repo_dir(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    (repo / "repo" / ".git").mkdir(parents=True)
    row = Row(name="proj", path=repo, repo_dir="repo")
    captured: dict[str, tuple[str, ...]] = {}

    def fake_run(*args: str) -> str:
        captured["args"] = args
        return "abc123 2026-06-01 hello"

    text = _build(row, run_out=fake_run)
    assert "last commit" in text
    assert "abc123" in text
    assert "git" in captured["args"]


def test_build_project_info_handles_git_log_failure(tmp_path: Path) -> None:
    import subprocess as sp

    repo = tmp_path / "proj"
    (repo / "repo" / ".git").mkdir(parents=True)
    row = Row(name="proj", path=repo, repo_dir="repo")

    def boom(*_args: str) -> str:
        raise sp.SubprocessError("nope")

    text = _build(row, run_out=boom)
    assert "last commit" in text


def test_build_project_info_renders_cached_timestamps(tmp_path: Path) -> None:
    row = Row(
        name="proj",
        path=tmp_path / "proj",
        last_cached_ts=1700000000,
        last_reconciled_ts=1700000000,
    )
    text = _build(row, fmt_iso=lambda ts: f"iso({ts})")
    assert "last cached" in text
    assert "last reconciled" in text


def test_read_worktree_block_returns_none_on_error(tmp_path: Path) -> None:
    def boom(_path: Path) -> dict[str, object]:
        raise OSError("nope")

    assert project_info._read_worktree_block(boom, tmp_path) is None
    assert project_info._read_worktree_block(lambda _p: {"worktree": "not-a-dict"}, tmp_path) is None
    assert project_info._read_worktree_block(lambda _p: {"worktree": {"x": 1}}, tmp_path) == {"x": 1}
