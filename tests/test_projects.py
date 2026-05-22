from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from homebase.workspace import projects


def test_build_row_haystack_lower_lowercases_and_joins() -> None:
    hay = projects.build_row_haystack_lower(
        name="MyProject",
        description="A Demo",
        tags=["CLI", "Web"],
        properties=[],
        branch="MAIN",
        path=Path("/tmp/MyProject"),
    )
    assert hay == hay.lower()
    for needle in ("myproject", "a demo", "cli", "web", "main", "/tmp/myproject"):
        assert needle in hay


def test_refresh_row_caches_picks_up_field_mutations(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    row = projects.project_row(target, include_git_dirty=False)
    assert "demo" in row.haystack_lower
    assert "feature-x" not in row.haystack_lower
    assert row.tags_lower == frozenset()

    row.tags = ["NewTag"]
    row.branch = "feature-x"
    row.name = "renamed"
    projects.refresh_row_caches(row)

    assert "newtag" in row.haystack_lower
    assert "feature-x" in row.haystack_lower
    assert "renamed" in row.haystack_lower
    assert row.tags_lower == frozenset({"newtag"})


def test_project_row_populates_haystack_lower(tmp_path: Path) -> None:
    target = tmp_path / "demo-project"
    target.mkdir()
    (target / ".base.yaml").write_text("tags:\n  - cli\n  - web\n", encoding="utf-8")

    row = projects.project_row(target, include_git_dirty=False)
    assert row.haystack_lower
    assert "demo-project" in row.haystack_lower
    for tag in ("cli", "web"):
        assert tag in row.haystack_lower


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def test_git_info_caches_branch_and_ts_until_index_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    projects._git_clear_cache()

    branch1, dirty1, ts1 = projects.git_info(repo, repo_dir=".")
    assert dirty1 == ""
    assert repo in projects._GIT_INFO_CACHE

    branch2, dirty2, ts2 = projects.git_info(repo, repo_dir=".")
    assert (branch1, ts1) == (branch2, ts2)
    assert dirty2 == ""

    (repo / "f.txt").write_text("b\n", encoding="utf-8")
    _, dirty3, _ = projects.git_info(repo, repo_dir=".")
    assert dirty3 == "*"
    assert repo in projects._GIT_INFO_CACHE

    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=repo, check=True)
    branch4, dirty4, ts4 = projects.git_info(repo, repo_dir=".")
    assert dirty4 == ""
    assert ts4 >= ts1


def test_git_info_cache_keeps_staged_dirty_under_working_tree_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo_staged"
    _init_git_repo(repo)
    projects._git_clear_cache()

    (repo / "f.txt").write_text("staged-change\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)

    _, dirty1, _ = projects.git_info(repo, repo_dir=".")
    assert dirty1 == "*"

    _, dirty2, _ = projects.git_info(repo, repo_dir=".")
    assert dirty2 == "*"


def test_git_info_cache_invalidates_on_soft_reset_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo_soft"
    _init_git_repo(repo)
    env = {**os.environ, "GIT_AUTHOR_DATE": "2024-06-15T12:00:00", "GIT_COMMITTER_DATE": "2024-06-15T12:00:00"}
    (repo / "f.txt").write_text("v2\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "v2"], cwd=repo, check=True, env=env)
    projects._git_clear_cache()

    _, _, ts_v2 = projects.git_info(repo, repo_dir=".")
    assert ts_v2 == int(datetime(2024, 6, 15, 12, 0, 0).timestamp())

    subprocess.run(["git", "reset", "--soft", "HEAD^"], cwd=repo, check=True)
    _, _, ts_after = projects.git_info(repo, repo_dir=".")
    assert ts_after != ts_v2


def test_git_info_returns_unverified_when_dirty_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    _init_git_repo(repo)
    projects._git_clear_cache()

    _, dirty_warm, _ = projects.git_info(repo, include_dirty=True, repo_dir=".")
    assert dirty_warm == ""

    _, dirty_skip, _ = projects.git_info(repo, include_dirty=False, repo_dir=".")
    assert dirty_skip == "~"


def test_git_info_resolves_worktree_branch(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _init_git_repo(parent)
    parent_branch = subprocess.run(
        ["git", "-C", str(parent), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    wt = tmp_path / "wt-featx"
    subprocess.run(
        ["git", "-C", str(parent), "worktree", "add", "-b", "featx", str(wt)],
        check=True,
        capture_output=True,
    )
    projects._git_clear_cache()

    wt_branch, wt_dirty, wt_ts = projects.git_info(wt, repo_dir=".")
    assert wt_branch == "featx"
    assert wt_dirty == ""
    assert wt_ts > 0

    parent_branch_after, _, _ = projects.git_info(parent, repo_dir=".")
    assert parent_branch_after == parent_branch


def test_git_info_worktree_cache_invalidates_on_commit(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _init_git_repo(parent)
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(parent), "worktree", "add", "-b", "side", str(wt)],
        check=True,
        capture_output=True,
    )
    projects._git_clear_cache()

    _, _, ts1 = projects.git_info(wt, repo_dir=".")
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-02T12:00:00",
        "GIT_COMMITTER_DATE": "2026-01-02T12:00:00",
    }
    (wt / "f.txt").write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(wt), "add", "f.txt"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "wt"], check=True, env=env)

    _, dirty_after, ts2 = projects.git_info(wt, repo_dir=".")
    assert dirty_after == ""
    assert ts2 != ts1


