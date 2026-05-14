from __future__ import annotations

from .base import ParsedUrl, UrlAdapter, strip_git_suffix


class SourcehutAdapter(UrlAdapter):
    key = "sourcehut"
    canonical_hosts = ("git.sr.ht",)

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) < 2 or not segs[0].startswith("~"):
            return None
        user, repo = segs[0], strip_git_suffix(segs[1])
        # /~user/repo                  → clone the repo root.
        if len(segs) == 2:
            return f"https://git.sr.ht/{user}/{repo}"
        # /~user/repo/tree/<ref>       → tree at branch root.
        if len(segs) == 4 and segs[2] == "tree":
            return f"https://git.sr.ht/{user}/{repo}"
        return None

    def project_name(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if len(segs) >= 2 and segs[0].startswith("~"):
            return strip_git_suffix(segs[1])
        return None
