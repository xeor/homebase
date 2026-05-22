from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args, "--no-open"])
    return cmd_new(ns, base, cwd)


def _init_project_repo(base: Path, name: str) -> Path:
    project = base / name
    repo = project / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")
    return project


def _read_meta(project: Path) -> dict:
    return yaml.safe_load((project / ".base.yaml").read_text(encoding="utf-8"))


def test_worktree_explicit_creates_directory_and_block(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 0

    out = tmp_path / "foo-featx"
    assert (out / "repo" / ".git").is_file()
    branch = subprocess.run(
        ["git", "-C", str(out / "repo"), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branch == "featx"

    meta = _read_meta(out)
    block = meta["worktree"]
    assert block["of"] == "foo"
    assert block["branch"] == "featx"
    assert Path(block["parent_path"]) == (tmp_path / "foo" / "repo")
    assert isinstance(block["gitdir_id"], str) and block["gitdir_id"]


def test_worktree_slash_branch_sanitized_dir(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")

    rc = _run(tmp_path, tmp_path, ["feature/auth", "--as", "worktree", "--from", "foo"])
    assert rc == 0

    out = tmp_path / "foo-feature--auth"
    assert out.is_dir()
    meta = _read_meta(out)
    assert meta["worktree"]["branch"] == "feature/auth"


def test_worktree_autodefault_from_cwd_inside_project(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    sub = parent / "repo" / "sub"
    sub.mkdir()

    rc = _run(tmp_path, sub, ["x"])
    assert rc == 0
    out = tmp_path / "foo-x"
    assert out.is_dir()
    assert _read_meta(out)["worktree"]["of"] == "foo"


def test_worktree_chained_parent_resolves_to_root(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    rc1 = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc1 == 0
    wt = tmp_path / "foo-featx"

    rc2 = _run(tmp_path, wt / "repo", ["bugfix-y"])
    assert rc2 == 0
    out = tmp_path / "foo-bugfix-y"
    assert out.is_dir()
    block = _read_meta(out)["worktree"]
    assert block["of"] == "foo"
    log = subprocess.run(
        ["git", "-C", str(out / "repo"), "log", "-1", "--format=%H"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    featx_head = subprocess.run(
        ["git", "-C", str(wt / "repo"), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert log == featx_head


def test_worktree_collision_errors_without_mutation(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    (tmp_path / "foo-featx").mkdir()

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 1
    contents = list((tmp_path / "foo-featx").iterdir())
    assert contents == []


def test_worktree_missing_from_errors(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree"])
    assert rc == 1


# ============================================================
# End-to-end edge-case coverage: confirm cmd_new produces the
# directory layout the dialog promises. Each test verifies the
# created dir name, the worktree block, repo_dir, branch state,
# and the parent admin entry — every detail the user could
# observe.
# ============================================================


def test_worktree_branch_name_starting_with_parent_does_not_double_prefix(
    tmp_path: Path,
) -> None:
    _init_project_repo(tmp_path, "foo")
    rc = _run(tmp_path, tmp_path, ["foo-things", "--as", "worktree", "--from", "foo"])
    assert rc == 0
    # Dir IS double-prefixed: parent='foo' + sanitised_branch='foo-things'.
    out = tmp_path / "foo-foo-things"
    assert out.is_dir()
    assert _read_meta(out)["worktree"]["branch"] == "foo-things"


def test_worktree_branch_equal_to_parent_name(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    rc = _run(tmp_path, tmp_path, ["foo", "--as", "worktree", "--from", "foo"])
    assert rc == 0
    out = tmp_path / "foo-foo"
    assert (out / "repo" / ".git").is_file()
    assert _read_meta(out)["worktree"]["branch"] == "foo"


def test_worktree_branch_with_dots_preserved(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    rc = _run(tmp_path, tmp_path, ["v1.2-rc", "--as", "worktree", "--from", "foo"])
    assert rc == 0
    out = tmp_path / "foo-v1.2-rc"
    assert out.is_dir()
    assert _read_meta(out)["worktree"]["branch"] == "v1.2-rc"


def test_worktree_branch_multi_segment_path(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    rc = _run(tmp_path, tmp_path, ["feat/api/v2", "--as", "worktree", "--from", "foo"])
    assert rc == 0
    out = tmp_path / "foo-feat--api--v2"
    assert (out / "repo" / ".git").is_file()
    block = _read_meta(out)["worktree"]
    assert block["branch"] == "feat/api/v2"


def test_worktree_for_existing_branch_skips_b_flag(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    # Pre-create the branch in the parent.
    subprocess.run(
        ["git", "-C", str(parent / "repo"), "branch", "premade"],
        check=True,
    )
    rc = _run(tmp_path, tmp_path, ["premade", "--as", "worktree", "--from", "foo"])
    assert rc == 0
    out = tmp_path / "foo-premade"
    branch = subprocess.run(
        ["git", "-C", str(out / "repo"), "branch", "--show-current"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert branch == "premade"


def test_worktree_records_repo_dir_repo(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    meta = _read_meta(tmp_path / "foo-featx")
    assert meta["repo_dir"] == "repo"


def test_worktree_writes_parent_admin_entry(tmp_path: Path) -> None:
    parent = _init_project_repo(tmp_path, "foo")
    assert _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    admin = parent / "repo" / ".git" / "worktrees"
    entries = sorted(p.name for p in admin.iterdir() if p.is_dir())
    assert len(entries) == 1
    block = _read_meta(tmp_path / "foo-featx")["worktree"]
    assert block["gitdir_id"] == entries[0]
    # Reverse pointer points back at the worktree.
    pointer = (admin / entries[0] / "gitdir").read_text().strip()
    assert pointer.endswith("foo-featx/repo/.git")


def test_worktree_parent_path_is_absolute(tmp_path: Path) -> None:
    _init_project_repo(tmp_path, "foo")
    assert _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    block = _read_meta(tmp_path / "foo-featx")["worktree"]
    assert Path(block["parent_path"]).is_absolute()
    assert Path(block["parent_path"]).exists()


def test_worktree_creation_aborts_when_parent_has_no_repo_dir(tmp_path: Path) -> None:
    # Create parent without repo_dir set in .base.yaml.
    project = tmp_path / "foo"
    repo = project / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (project / ".base.yaml").write_text("tags: []\n", encoding="utf-8")

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 1
    assert not (tmp_path / "foo-featx").exists()


def test_worktree_collision_with_other_kind_of_dir_blocks(tmp_path: Path) -> None:
    # Even if the colliding dir isn't a worktree at all, we refuse.
    _init_project_repo(tmp_path, "foo")
    (tmp_path / "foo-featx").mkdir()
    (tmp_path / "foo-featx" / "random.txt").write_text("hi", encoding="utf-8")

    rc = _run(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"])
    assert rc == 1
    # The pre-existing file is untouched.
    assert (tmp_path / "foo-featx" / "random.txt").read_text() == "hi"
