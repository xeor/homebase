from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.workspace import projects as projects_mod
from homebase.workspace.projects import (
    _alpha_name_at,
    _combine_dirty,
    _next_available_alpha_name,
    _porcelain_dirty,
    _resolve_git_dirs,
    _resolve_head_ref_text,
    _resolve_repo_path,
    create_project,
)


def test_alpha_name_at_handles_double_letter_rollover() -> None:
    assert _alpha_name_at(0) == "a"
    assert _alpha_name_at(25) == "z"
    assert _alpha_name_at(26) == "aa"
    assert _alpha_name_at(27) == "ab"
    assert _alpha_name_at(51) == "az"
    assert _alpha_name_at(52) == "ba"


def test_next_available_alpha_name_skips_existing(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert (
        _next_available_alpha_name(tmp_path, add_date_prefix=False, add_tmp_suffix=False)
        == "c"
    )


def test_resolve_repo_path_absolute_returned_as_is(tmp_path: Path) -> None:
    abs_path = tmp_path / "abs"
    abs_path.mkdir()
    assert _resolve_repo_path(tmp_path, str(abs_path)) == abs_path


def test_resolve_repo_path_relative_resolved_under_project(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()
    (project / "repo").mkdir()
    assert _resolve_repo_path(project, "repo") == (project / "repo").resolve()


def test_combine_dirty_truth_table() -> None:
    assert _combine_dirty("?", "") == "?"
    assert _combine_dirty("", "?") == "?"
    assert _combine_dirty("*", "") == "*"
    assert _combine_dirty("", "*") == "*"
    assert _combine_dirty("", "") == ""


def test_resolve_head_ref_text_passes_through_non_ref() -> None:
    assert _resolve_head_ref_text(Path("/tmp"), "abcdef1234") == "abcdef1234"


def test_resolve_head_ref_text_empty_ref_passes_through(tmp_path: Path) -> None:
    assert _resolve_head_ref_text(tmp_path, "ref:  ") == "ref:  "


def test_resolve_head_ref_text_loose_ref_appends_sha(tmp_path: Path) -> None:
    refs = tmp_path / "refs" / "heads"
    refs.mkdir(parents=True)
    (refs / "main").write_text("deadbeef\n")
    out = _resolve_head_ref_text(tmp_path, "ref: refs/heads/main")
    assert out == "ref: refs/heads/main@deadbeef"


def test_resolve_head_ref_text_packed_refs_fallback(tmp_path: Path) -> None:
    # No loose ref file; falls back to packed-refs scan.
    packed = tmp_path / "packed-refs"
    packed.write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        "^ignored-line\n"
        "1234abcd refs/heads/main\n"
        "5678cdef refs/tags/v1\n"
    )
    out = _resolve_head_ref_text(tmp_path, "ref: refs/heads/main")
    assert out == "ref: refs/heads/main@1234abcd"


def test_resolve_head_ref_text_packed_refs_missing_returns_passthrough(
    tmp_path: Path,
) -> None:
    # Neither loose ref nor packed-refs file → fall back to original text.
    out = _resolve_head_ref_text(tmp_path, "ref: refs/heads/main")
    assert out == "ref: refs/heads/main"


def test_resolve_git_dirs_returns_none_when_missing(tmp_path: Path) -> None:
    assert _resolve_git_dirs(tmp_path) is None


def test_resolve_git_dirs_returns_dir_for_plain_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    gitdir, common = _resolve_git_dirs(tmp_path) or (None, None)
    assert gitdir == tmp_path / ".git"
    assert common == tmp_path / ".git"


def test_resolve_git_dirs_follows_gitdir_pointer_with_commondir(
    tmp_path: Path,
) -> None:
    real_git = tmp_path / "actual.git"
    real_git.mkdir()
    # Worktree pointer
    work = tmp_path / "worktree"
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {real_git}\n")
    # commondir file in real git
    common_target = tmp_path / "common.git"
    common_target.mkdir()
    (real_git / "commondir").write_text(str(common_target) + "\n")
    out = _resolve_git_dirs(work)
    assert out is not None
    gitdir, common = out
    assert gitdir == real_git
    assert common == common_target


def test_resolve_git_dirs_empty_gitfile_returns_none(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("")
    assert _resolve_git_dirs(tmp_path) is None


def test_resolve_git_dirs_non_gitdir_text_returns_none(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("not a gitfile pointer\n")
    assert _resolve_git_dirs(tmp_path) is None


def test_resolve_git_dirs_empty_gitdir_value_returns_none(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir:\n")
    assert _resolve_git_dirs(tmp_path) is None


def test_resolve_git_dirs_relative_gitdir_resolves(tmp_path: Path) -> None:
    real_git = tmp_path / "outer" / "real.git"
    real_git.mkdir(parents=True)
    work = tmp_path / "outer" / "work"
    work.mkdir()
    (work / ".git").write_text("gitdir: ../real.git\n")
    out = _resolve_git_dirs(work)
    assert out is not None
    assert out[0] == real_git.resolve()


def test_porcelain_dirty_returns_question_on_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a, **_kw):
        raise OSError("git missing")

    monkeypatch.setattr(projects_mod.core_utils, "run_out", boom)
    assert _porcelain_dirty(tmp_path) == "?"


def test_create_project_runs_plain_scaffold(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    template = base / ".copier" / "tpl"
    template.mkdir(parents=True)
    (template / "hello.txt").write_text("hi")
    target = create_project(
        base,
        "demo",
        add_date_prefix=False,
        add_tmp_suffix=False,
        copier_template="tpl",
    )
    assert target.is_dir()
    assert (target / "hello.txt").read_text() == "hi"
    assert (target / ".base.yaml").is_file()


def test_create_project_missing_template_raises_and_cleans_up(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValueError, match="template not found"):
        create_project(
            base,
            "demo",
            add_date_prefix=False,
            add_tmp_suffix=False,
            copier_template="nope",
        )
    assert not (base / "demo").exists()


def test_create_project_copier_missing_binary_raises_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    template = base / ".copier" / "tpl"
    template.mkdir(parents=True)
    (template / "copier.yml").write_text("_subdirectory: .\n")
    monkeypatch.setattr(projects_mod.shutil, "which", lambda _n: None)
    with pytest.raises(ValueError, match="copier is not installed"):
        create_project(
            base,
            "demo",
            add_date_prefix=False,
            add_tmp_suffix=False,
            copier_template="tpl",
        )
    assert not (base / "demo").exists()


def test_create_project_copier_failure_raises_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    template = base / ".copier" / "tpl"
    template.mkdir(parents=True)
    (template / "copier.yaml").write_text("_subdirectory: .\n")
    monkeypatch.setattr(projects_mod.shutil, "which", lambda _n: "/usr/local/bin/copier")

    def fake_run(cmd, **_kw):
        raise subprocess.CalledProcessError(returncode=2, cmd=cmd)

    monkeypatch.setattr(projects_mod.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="copier failed"):
        create_project(
            base,
            "demo",
            add_date_prefix=False,
            add_tmp_suffix=False,
            copier_template="tpl",
        )
    assert not (base / "demo").exists()


def test_create_project_plain_scaffold_failure_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    template = base / ".copier" / "tpl"
    template.mkdir(parents=True)
    (template / "hello.txt").write_text("hi")

    def fake_scaffold(_src: Path, _dst: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(projects_mod, "scaffold_template_directory", fake_scaffold)
    with pytest.raises(OSError, match="disk full"):
        create_project(
            base,
            "demo",
            add_date_prefix=False,
            add_tmp_suffix=False,
            copier_template="tpl",
        )
    assert not (base / "demo").exists()
