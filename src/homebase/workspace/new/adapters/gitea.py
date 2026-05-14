from __future__ import annotations

from .base import ParsedUrl, UrlAdapter, strip_git_suffix


class GiteaAdapter(UrlAdapter):
    """Adapter for gitea / forgejo style forges. No canonical host —
    self-hosted users must add their host to git.config.hosts."""

    key = "gitea"
    canonical_hosts = ()

    def _host(self, parsed: ParsedUrl) -> str:
        return parsed.host

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) < 2:
            return None
        owner, repo = segs[0], strip_git_suffix(segs[1])
        # /owner/repo                       → clone the repo root
        if len(segs) == 2:
            return f"https://{self._host(parsed)}/{owner}/{repo}.git"
        # /owner/repo/src/branch/<ref>      → tree at branch root (no
        # file/dir path after) is also a clone target. Anything deeper
        # (`/src/branch/<ref>/<path>`) is a file blob or directory tree
        # and is handled by ``to_download_url`` so the router can pick
        # ``download`` instead of cloning the entire repo.
        if (
            len(segs) == 5
            and segs[2] == "src"
            and segs[3] == "branch"
        ):
            return f"https://{self._host(parsed)}/{owner}/{repo}.git"
        return None

    def to_download_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 6 and segs[2] == "src" and segs[3] == "branch":
            owner, repo = segs[0], strip_git_suffix(segs[1])
            ref = segs[4]
            path = "/".join(segs[5:])
            return f"https://{self._host(parsed)}/{owner}/{repo}/raw/branch/{ref}/{path}"
        return None

    def project_name(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 2:
            return strip_git_suffix(segs[1])
        return None


class CodebergAdapter(GiteaAdapter):
    """codeberg.org runs on gitea — same URL shape."""

    key = "codeberg"
    canonical_hosts = ("codeberg.org",)
