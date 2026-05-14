from __future__ import annotations

from .base import ParsedUrl, UrlAdapter, strip_git_suffix


class BitbucketAdapter(UrlAdapter):
    key = "bitbucket"
    canonical_hosts = ("bitbucket.org",)

    def _host(self, parsed: ParsedUrl) -> str:
        return parsed.host or "bitbucket.org"

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) < 2:
            return None
        owner, repo = segs[0], strip_git_suffix(segs[1])
        # /owner/repo                → clone the repo root
        if len(segs) == 2:
            return f"https://{self._host(parsed)}/{owner}/{repo}.git"
        # /owner/repo/src/<ref>      → tree at branch root. Anything
        # deeper (`/src/<ref>/<path>`) is a file blob and is handled by
        # ``to_download_url``.
        if len(segs) == 4 and segs[2] == "src":
            return f"https://{self._host(parsed)}/{owner}/{repo}.git"
        return None

    def to_download_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 5 and segs[2] == "src":
            owner, repo = segs[0], strip_git_suffix(segs[1])
            ref = segs[3]
            path = "/".join(segs[4:])
            return f"https://{self._host(parsed)}/{owner}/{repo}/raw/{ref}/{path}"
        return None

    def project_name(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 2:
            return strip_git_suffix(segs[1])
        return None
