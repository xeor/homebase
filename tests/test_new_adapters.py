from __future__ import annotations

from homebase.workspace.new.adapters import (
    adapter_for_host,
    adapter_for_key,
    parse_url,
)


def test_parse_https() -> None:
    p = parse_url("https://github.com/foo/bar")
    assert p is not None
    assert p.scheme == "https"
    assert p.host == "github.com"
    assert p.path == "foo/bar"
    assert p.segments == ["foo", "bar"]


def test_parse_ssh() -> None:
    p = parse_url("git@github.com:foo/bar.git")
    assert p is not None
    assert p.is_ssh
    assert p.host == "github.com"
    assert p.path == "foo/bar.git"


def test_parse_nonurl_returns_none() -> None:
    assert parse_url("myproj") is None
    assert parse_url("./path") is None


# ------------------------ github ------------------------


def test_github_clone_root() -> None:
    adapter = adapter_for_host("github.com")
    assert adapter is not None
    p = parse_url("https://github.com/foo/bar")
    assert adapter.to_clone_url(p) == "https://github.com/foo/bar.git"
    assert adapter.project_name(p) == "bar"


def test_github_clone_dot_git_suffix() -> None:
    adapter = adapter_for_host("github.com")
    p = parse_url("https://github.com/foo/bar.git")
    assert adapter.to_clone_url(p) == "https://github.com/foo/bar.git"
    assert adapter.project_name(p) == "bar"


def test_github_clone_tree_ref() -> None:
    adapter = adapter_for_host("github.com")
    p = parse_url("https://github.com/foo/bar/tree/main")
    assert adapter.to_clone_url(p) == "https://github.com/foo/bar.git"


def test_github_blob_to_raw() -> None:
    adapter = adapter_for_host("github.com")
    p = parse_url("https://github.com/foo/bar/blob/main/TODO.md")
    assert (
        adapter.to_download_url(p)
        == "https://raw.githubusercontent.com/foo/bar/refs/heads/main/TODO.md"
    )


# ------------------------ gitlab ------------------------


def test_gitlab_clone_root() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/group/proj")
    assert adapter.to_clone_url(p) == "https://gitlab.com/group/proj.git"


def test_gitlab_clone_nested_subgroup() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/group/sub/proj")
    assert adapter.to_clone_url(p) == "https://gitlab.com/group/sub/proj.git"


def test_gitlab_blob_to_raw() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/group/proj/-/blob/main/README.md")
    assert (
        adapter.to_download_url(p)
        == "https://gitlab.com/group/proj/-/raw/main/README.md"
    )


def test_gitlab_tree_to_clone() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/group/proj/-/tree/main")
    assert adapter.to_clone_url(p) == "https://gitlab.com/group/proj.git"


# ---------------------- bitbucket -----------------------


def test_bitbucket_clone() -> None:
    adapter = adapter_for_host("bitbucket.org")
    p = parse_url("https://bitbucket.org/u/r")
    assert adapter.to_clone_url(p) == "https://bitbucket.org/u/r.git"


def test_bitbucket_blob() -> None:
    adapter = adapter_for_host("bitbucket.org")
    p = parse_url("https://bitbucket.org/u/r/src/main/README.md")
    assert (
        adapter.to_download_url(p)
        == "https://bitbucket.org/u/r/raw/main/README.md"
    )


# ---------------------- codeberg ------------------------


def test_codeberg_clone() -> None:
    adapter = adapter_for_host("codeberg.org")
    p = parse_url("https://codeberg.org/u/r")
    assert adapter.to_clone_url(p) == "https://codeberg.org/u/r.git"


def test_codeberg_blob() -> None:
    adapter = adapter_for_host("codeberg.org")
    p = parse_url("https://codeberg.org/u/r/src/branch/main/README.md")
    assert (
        adapter.to_download_url(p)
        == "https://codeberg.org/u/r/raw/branch/main/README.md"
    )


# --------------------- sourcehut ------------------------


def test_sourcehut_clone() -> None:
    adapter = adapter_for_host("git.sr.ht")
    p = parse_url("https://git.sr.ht/~me/repo")
    assert adapter.to_clone_url(p) == "https://git.sr.ht/~me/repo"


# ------------- user-configured self-hosted --------------


def test_user_host_routes_to_gitlab_adapter() -> None:
    adapter = adapter_for_host("git.example.com", {"git.example.com": "gitlab"})
    assert adapter is not None
    assert adapter.key == "gitlab"
    p = parse_url("https://git.example.com/team/proj")
    assert adapter.to_clone_url(p) == "https://git.example.com/team/proj.git"


def test_user_host_routes_to_gitea_adapter() -> None:
    adapter = adapter_for_host("code.example.org", {"code.example.org": "gitea"})
    assert adapter is not None
    assert adapter.key == "gitea"
    p = parse_url("https://code.example.org/u/r/src/branch/main/file.md")
    assert (
        adapter.to_download_url(p)
        == "https://code.example.org/u/r/raw/branch/main/file.md"
    )


def test_user_host_subpath_longest_prefix() -> None:
    user_hosts = {
        "git.example.com": "gitlab",
        "git.example.com/scm": "bitbucket",
    }
    adapter = adapter_for_host("git.example.com/scm", user_hosts)
    assert adapter.key == "bitbucket"


def test_unknown_host_returns_none() -> None:
    assert adapter_for_host("example.com") is None


def test_adapter_for_key() -> None:
    assert adapter_for_key("github").key == "github"
    assert adapter_for_key("nonexistent") is None
