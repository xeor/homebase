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


def test_discover_copier_templates_returns_sorted_visible_dirs(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    assert projects.discover_copier_templates(base) == []

    copier = base / ".copier"
    copier.mkdir()
    (copier / "Beta").mkdir()
    (copier / "alpha").mkdir()
    (copier / ".hidden").mkdir()
    (copier / "afile").write_text("x")
    out = projects.discover_copier_templates(base)
    assert out == ["alpha", "Beta"]


def test_resolve_new_project_name_strips_legacy_prefix_and_tmp() -> None:
    name = projects.resolve_new_project_name(
        "2025-01-01_demo.tmp", add_date_prefix=True, add_tmp_suffix=False
    )
    assert name.endswith("_demo")
    assert name.startswith(datetime.now().strftime("%Y-%m-%d_"))


def test_resolve_new_project_name_rejects_invalid_inputs() -> None:
    import pytest

    for bad in ("", "   ", ".", "..", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            projects.resolve_new_project_name(
                bad, add_date_prefix=False, add_tmp_suffix=False
            )


def test_classify_name_detects_suffixes() -> None:
    assert projects.classify_name("alpha.fork") == (True, False, "fork")
    assert projects.classify_name("beta.tmp") == (False, True, "tmp")
    assert projects.classify_name("gamma") == (False, False, None)


def test_alpha_name_at_and_next_available(tmp_path: Path) -> None:
    base = tmp_path / "b"
    base.mkdir()
    assert projects._alpha_name_at(0) == "a"
    assert projects._alpha_name_at(25) == "z"
    assert projects._alpha_name_at(26) == "aa"
    assert projects._alpha_name_at(26 + 25) == "az"

    nxt = projects._next_available_alpha_name(
        base, add_date_prefix=False, add_tmp_suffix=False
    )
    assert nxt == "a"
    (base / "a").mkdir()
    (base / "b").mkdir()
    nxt2 = projects._next_available_alpha_name(
        base, add_date_prefix=False, add_tmp_suffix=False
    )
    assert nxt2 == "c"


def test_path_size_bytes_handles_file_and_dir_and_missing(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_bytes(b"hello")
    assert projects._path_size_bytes(f) == 5

    d = tmp_path / "d"
    d.mkdir()
    (d / "a.bin").write_bytes(b"abc")
    (d / "b.bin").write_bytes(b"de")
    assert projects._path_size_bytes(d) == 5

    missing = tmp_path / "missing"
    assert projects._path_size_bytes(missing) == 0


def test_resolve_row_size_refresh_branches(tmp_path: Path) -> None:
    d = tmp_path / "p"
    d.mkdir()
    (d / "f.bin").write_bytes(b"x" * 100)

    size_a, count_a = projects._resolve_row_size(d, None, 0)
    assert size_a == 100
    assert count_a == 1

    (d / "g.bin").write_bytes(b"y" * 50)
    size_b, count_b = projects._resolve_row_size(d, size_a, count_a)
    assert size_b == size_a
    assert count_b == count_a + 1

    size_c, _ = projects._resolve_row_size(d, size_b, count_b, force_refresh=True)
    assert size_c == 150


def test_create_project_writes_marker_and_tags(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    target = projects.create_project(
        base,
        "alpha",
        add_date_prefix=False,
        add_tmp_suffix=False,
        copier_template=None,
        initial_tags=["alpha", "  ", "beta", "alpha"],
    )
    assert target.is_dir()
    assert (target / ".base.yaml").is_file()
    text = (target / ".base.yaml").read_text()
    # tags deduped and sorted
    assert "alpha" in text and "beta" in text


def test_create_project_rejects_existing_target(tmp_path: Path) -> None:
    import pytest

    base = tmp_path / "base"
    base.mkdir()
    (base / "alpha").mkdir()
    with pytest.raises(ValueError, match="already exists"):
        projects.create_project(
            base, "alpha", add_date_prefix=False, add_tmp_suffix=False
        )


def test_create_project_scaffolds_plain_template(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    tmpl_dir = base / ".copier" / "plain"
    (tmpl_dir / "subdir").mkdir(parents=True)
    (tmpl_dir / "subdir" / "inner.txt").write_text("inner\n")
    (tmpl_dir / "root.txt").write_text("root\n")
    target = projects.create_project(
        base,
        "beta",
        add_date_prefix=False,
        add_tmp_suffix=False,
        copier_template="plain",
    )
    assert (target / "root.txt").read_text() == "root\n"
    assert (target / "subdir" / "inner.txt").read_text() == "inner\n"


def test_create_project_missing_template_raises(tmp_path: Path) -> None:
    import pytest

    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValueError, match="template not found"):
        projects.create_project(
            base,
            "gamma",
            add_date_prefix=False,
            add_tmp_suffix=False,
            copier_template="missing",
        )
    assert not (base / "gamma").exists()


def test_scaffold_template_directory_noops_on_empty(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "dst"
    dst.mkdir()
    projects.scaffold_template_directory(src, dst)
    assert list(dst.iterdir()) == []


def test_run_post_commands_runs_and_succeeds(tmp_path: Path, capsys) -> None:
    projects.run_post_commands(tmp_path, [])  # no-op fast path

    target = tmp_path / "work"
    target.mkdir()
    projects.run_post_commands(target, ["echo hi > marker.txt"])
    assert (target / "marker.txt").exists()


def test_run_post_commands_raises_on_nonzero_exit(tmp_path: Path) -> None:
    import pytest

    target = tmp_path / "work"
    target.mkdir()
    with pytest.raises(ValueError, match="post command failed"):
        projects.run_post_commands(target, ["exit 7"])


def test_resolve_git_dirs_handles_gitfile_pointer(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _init_git_repo(parent)
    wt = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(parent), "worktree", "add", "-b", "feat", str(wt)],
        check=True,
        capture_output=True,
    )
    result = projects._resolve_git_dirs(wt)
    assert result is not None
    gitdir, commondir = result
    assert gitdir != commondir
    assert (commondir / "HEAD").is_file() or (commondir / "refs").is_dir()


def test_resolve_git_dirs_returns_none_for_non_repo(tmp_path: Path) -> None:
    assert projects._resolve_git_dirs(tmp_path) is None


def test_resolve_head_ref_text_returns_input_when_not_ref(tmp_path: Path) -> None:
    assert projects._resolve_head_ref_text(tmp_path, "abc123") == "abc123"
    # ref:<missing> path returns input
    assert projects._resolve_head_ref_text(tmp_path, "ref: ").startswith("ref: ")


def test_combine_dirty_truth_table() -> None:
    assert projects._combine_dirty("", "") == ""
    assert projects._combine_dirty("*", "") == "*"
    assert projects._combine_dirty("", "*") == "*"
    assert projects._combine_dirty("?", "") == "?"
    assert projects._combine_dirty("", "?") == "?"


def test_git_info_no_repo_dir_returns_dashes(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    branch, dirty, ts = projects.git_info(plain, repo_dir="")
    assert (branch, dirty, ts) == ("-", "-", 0)


def test_git_info_missing_dotgit_returns_dashes(tmp_path: Path) -> None:
    plain = tmp_path / "plain2"
    plain.mkdir()
    branch, dirty, ts = projects.git_info(plain, repo_dir=".")
    assert (branch, dirty, ts) == ("-", "-", 0)
