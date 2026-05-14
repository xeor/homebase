from __future__ import annotations

from .base import ParsedUrl, UrlAdapter, strip_git_suffix


class GithubAdapter(UrlAdapter):
    key = "github"
    canonical_hosts = ("github.com",)

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) < 2:
            return None
        owner, repo = segs[0], strip_git_suffix(segs[1])
        if len(segs) == 2:
            return f"https://github.com/{owner}/{repo}.git"
        if segs[2] == "tree":
            return f"https://github.com/{owner}/{repo}.git"
        if parsed.is_ssh and parsed.path.endswith(".git"):
            return parsed.raw
        return None

    def to_download_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 5 and segs[2] in {"blob", "raw"}:
            owner, repo = segs[0], strip_git_suffix(segs[1])
            ref = segs[3]
            path = "/".join(segs[4:])
            return f"https://raw.githubusercontent.com/{owner}/{repo}/refs/heads/{ref}/{path}"
        return None

    def project_name(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 2:
            return strip_git_suffix(segs[1])
        return None
