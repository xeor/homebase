"""Routing tests for ``autodetect_source_key`` — exercises how a raw
URL flows through ``adapter_for_host`` → ``to_clone_url`` /
``to_download_url`` and ends up picking ``git`` or ``download``.

The interesting cases are the ones where the URL points at a *file*
inside a forge — github blob, gitlab raw, gitea ``src/branch/<ref>/…``,
codeberg, bitbucket — and crucially the self-hosted gitea case via
``git.config.hosts``.
"""
from __future__ import annotations

from pathlib import Path

from homebase.workspace.new.adapters import (
    adapter_for_host,
    parse_url,
)
from homebase.workspace.new.cmd import autodetect_source_key
from homebase.workspace.new.sources.download import resolve_download_url
from homebase.workspace.new.sources.git import detect_git_url

# ------------------------------------------------------------------
# Helpers — the autodetect API takes a sources_cfg dict; we test the
# raw `git.config.hosts` map by wrapping it.
# ------------------------------------------------------------------


def _cfg(git_hosts: dict[str, str] | None = None) -> dict[str, dict]:
    return {"git": {"config": {"hosts": dict(git_hosts or {})}}}


# ============================================================
# github — sanity that the documented behavior is preserved
# ============================================================


def test_github_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://github.com/xeor/karb", _cfg()
    ) == "git"


def test_github_dot_git_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://github.com/xeor/karb.git", _cfg()
    ) == "git"


def test_github_tree_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://github.com/xeor/karb/tree/main", _cfg()
    ) == "git"


def test_github_ssh_routes_to_git() -> None:
    assert autodetect_source_key(
        "git@github.com:xeor/karb.git", _cfg()
    ) == "git"


def test_github_blob_routes_to_download() -> None:
    # The exact case the user pointed to.
    assert autodetect_source_key(
        "https://github.com/xeor/karb/blob/main/Tiltfile", _cfg()
    ) == "download"


def test_github_blob_resolves_to_raw() -> None:
    url = "https://github.com/xeor/karb/blob/main/Tiltfile"
    assert resolve_download_url(url, {}, []) == (
        "https://raw.githubusercontent.com/xeor/karb/refs/heads/main/Tiltfile"
    )


def test_github_blob_is_not_a_git_url() -> None:
    # detect_git_url is what `--git` calls — it should explicitly
    # decline a github blob URL rather than silently cloning the repo
    # and losing the file path.
    url = "https://github.com/xeor/karb/blob/main/Tiltfile"
    assert detect_git_url(url, {}) is None


# ============================================================
# gitlab.com — canonical host
# ============================================================


def test_gitlab_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://gitlab.com/group/proj", _cfg()
    ) == "git"


def test_gitlab_nested_group_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://gitlab.com/group/sub/proj", _cfg()
    ) == "git"


def test_gitlab_tree_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://gitlab.com/group/proj/-/tree/main", _cfg()
    ) == "git"


def test_gitlab_blob_routes_to_download() -> None:
    assert autodetect_source_key(
        "https://gitlab.com/group/proj/-/blob/main/README.md", _cfg()
    ) == "download"


def test_gitlab_raw_routes_to_download() -> None:
    # The URL is already raw; we shouldn't try to clone it.
    assert autodetect_source_key(
        "https://gitlab.com/group/proj/-/raw/main/README.md", _cfg()
    ) == "download"


def test_gitlab_blob_resolves_to_raw() -> None:
    url = "https://gitlab.com/group/proj/-/blob/main/README.md"
    assert resolve_download_url(url, {}, []) == (
        "https://gitlab.com/group/proj/-/raw/main/README.md"
    )


# ============================================================
# bitbucket — same blob/tree distinction as gitea
# ============================================================


def test_bitbucket_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://bitbucket.org/u/r", _cfg()
    ) == "git"


def test_bitbucket_tree_routes_to_git() -> None:
    # /u/r/src/<ref>  (no path)  → branch tree, clone
    assert autodetect_source_key(
        "https://bitbucket.org/u/r/src/main", _cfg()
    ) == "git"


def test_bitbucket_blob_routes_to_download() -> None:
    # /u/r/src/<ref>/<path>  → file blob, download
    assert autodetect_source_key(
        "https://bitbucket.org/u/r/src/main/README.md", _cfg()
    ) == "download"


# ============================================================
# codeberg — gitea hosted on codeberg.org (canonical mapping)
# ============================================================


def test_codeberg_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://codeberg.org/u/r", _cfg()
    ) == "git"


def test_codeberg_branch_tree_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://codeberg.org/u/r/src/branch/main", _cfg()
    ) == "git"


def test_codeberg_blob_routes_to_download() -> None:
    assert autodetect_source_key(
        "https://codeberg.org/u/r/src/branch/main/README.md", _cfg()
    ) == "download"


def test_codeberg_blob_resolves_to_raw() -> None:
    url = "https://codeberg.org/u/r/src/branch/main/README.md"
    assert resolve_download_url(url, {}, []) == (
        "https://codeberg.org/u/r/raw/branch/main/README.md"
    )


# ============================================================
# Self-hosted gitea via git.config.hosts — THE USER'S CASE
# ============================================================


_USER_HOSTS = {"odin.iv.boa.nu": "gitea"}


def test_self_hosted_gitea_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://odin.iv.boa.nu/lars/corex-infra",
        _cfg(_USER_HOSTS),
    ) == "git"


def test_self_hosted_gitea_branch_tree_routes_to_git() -> None:
    # /<owner>/<repo>/src/branch/<ref>  with no file path → still a clone
    assert autodetect_source_key(
        "https://odin.iv.boa.nu/lars/corex-infra/src/branch/main",
        _cfg(_USER_HOSTS),
    ) == "git"


def test_self_hosted_gitea_blob_routes_to_download() -> None:
    """The exact failing case the user reported: a Markdown file URL
    on a self-hosted gitea was being cloned instead of downloaded."""
    assert autodetect_source_key(
        "https://odin.iv.boa.nu/lars/corex-infra/src/branch/main/BOOTSTRAP-STATUS.md",
        _cfg(_USER_HOSTS),
    ) == "download"


def test_self_hosted_gitea_blob_resolves_to_raw() -> None:
    url = "https://odin.iv.boa.nu/lars/corex-infra/src/branch/main/BOOTSTRAP-STATUS.md"
    assert resolve_download_url(url, _USER_HOSTS, []) == (
        "https://odin.iv.boa.nu/lars/corex-infra/raw/branch/main/BOOTSTRAP-STATUS.md"
    )


def test_self_hosted_gitea_blob_is_not_a_git_url() -> None:
    url = "https://odin.iv.boa.nu/lars/corex-infra/src/branch/main/BOOTSTRAP-STATUS.md"
    assert detect_git_url(url, _USER_HOSTS) is None


def test_self_hosted_gitea_blob_deeper_path() -> None:
    # File buried under multiple subdirectories — same routing.
    url = "https://odin.iv.boa.nu/lars/corex/src/branch/main/docs/v2/setup.md"
    assert autodetect_source_key(url, _cfg(_USER_HOSTS)) == "download"
    assert resolve_download_url(url, _USER_HOSTS, []) == (
        "https://odin.iv.boa.nu/lars/corex/raw/branch/main/docs/v2/setup.md"
    )


def test_self_hosted_gitea_with_dot_git_suffix() -> None:
    assert autodetect_source_key(
        "https://odin.iv.boa.nu/lars/corex.git",
        _cfg(_USER_HOSTS),
    ) == "git"


def test_self_hosted_gitea_ssh_clone() -> None:
    assert autodetect_source_key(
        "git@odin.iv.boa.nu:lars/corex.git",
        _cfg(_USER_HOSTS),
    ) == "git"


# ============================================================
# Self-hosted gitlab via git.config.hosts
# ============================================================


_GITLAB_HOSTS = {"git.mycompany.com": "gitlab"}


def test_self_hosted_gitlab_root_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://git.mycompany.com/team/proj",
        _cfg(_GITLAB_HOSTS),
    ) == "git"


def test_self_hosted_gitlab_blob_routes_to_download() -> None:
    assert autodetect_source_key(
        "https://git.mycompany.com/team/proj/-/blob/main/README.md",
        _cfg(_GITLAB_HOSTS),
    ) == "download"


def test_self_hosted_gitlab_raw_routes_to_download() -> None:
    assert autodetect_source_key(
        "https://git.mycompany.com/team/proj/-/raw/main/README.md",
        _cfg(_GITLAB_HOSTS),
    ) == "download"


# ============================================================
# Hosts without an adapter — generic .git heuristic / fallback
# ============================================================


def test_unknown_host_dot_git_routes_to_git() -> None:
    assert autodetect_source_key(
        "https://example.com/path/to/repo.git",
        _cfg(),
    ) == "git"


def test_unknown_host_arbitrary_url_routes_to_download() -> None:
    assert autodetect_source_key(
        "https://example.com/file.zip",
        _cfg(),
    ) == "download"


def test_unknown_host_ssh_routes_to_git() -> None:
    assert autodetect_source_key(
        "git@example.com:team/repo.git",
        _cfg(),
    ) == "git"


# ============================================================
# Sanity — non-URL inputs stay out of the URL routing path.
# ============================================================


def test_bare_token_routes_to_empty() -> None:
    assert autodetect_source_key("myproj", _cfg()) == "empty"


def test_existing_path_routes_to_local(tmp_path: Path) -> None:
    assert autodetect_source_key(str(tmp_path), _cfg()) == "local"


def test_missing_relative_path_routes_to_empty() -> None:
    assert autodetect_source_key("./somepath", _cfg()) == "empty"


def test_missing_absolute_path_routes_to_local() -> None:
    assert autodetect_source_key("/no/such/dir-xyz", _cfg()) == "local"


# ============================================================
# Adapter unit tests for the tightened to_clone_url contracts.
# ============================================================


def test_gitea_to_clone_url_declines_file_path() -> None:
    """Direct check: gitea must not claim a file URL as a clone target.
    This is the unit-level guarantee the routing depends on."""
    adapter = adapter_for_host("odin.iv.boa.nu", _USER_HOSTS)
    assert adapter is not None
    p = parse_url("https://odin.iv.boa.nu/u/r/src/branch/main/file.md")
    assert adapter.to_clone_url(p) is None


def test_gitea_to_clone_url_accepts_branch_tree_root() -> None:
    adapter = adapter_for_host("odin.iv.boa.nu", _USER_HOSTS)
    p = parse_url("https://odin.iv.boa.nu/u/r/src/branch/main")
    assert adapter.to_clone_url(p) == "https://odin.iv.boa.nu/u/r.git"


def test_gitlab_to_clone_url_declines_blob() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/g/p/-/blob/main/f.md")
    assert adapter.to_clone_url(p) is None


def test_gitlab_to_clone_url_declines_raw() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/g/p/-/raw/main/f.md")
    assert adapter.to_clone_url(p) is None


def test_gitlab_to_clone_url_declines_tree_with_path() -> None:
    adapter = adapter_for_host("gitlab.com")
    p = parse_url("https://gitlab.com/g/p/-/tree/main/subdir")
    assert adapter.to_clone_url(p) is None


def test_bitbucket_to_clone_url_declines_file_path() -> None:
    adapter = adapter_for_host("bitbucket.org")
    p = parse_url("https://bitbucket.org/u/r/src/main/README.md")
    assert adapter.to_clone_url(p) is None
