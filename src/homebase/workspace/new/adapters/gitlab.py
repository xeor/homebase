from __future__ import annotations

from .base import ParsedUrl, UrlAdapter, strip_git_suffix


class GitlabAdapter(UrlAdapter):
    key = "gitlab"
    canonical_hosts = ("gitlab.com",)

    def _host(self, parsed: ParsedUrl) -> str:
        return parsed.host or "gitlab.com"

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        # GitLab project paths can be nested: <group>/<subgroup>/<repo>
        # On the UI: /<group...>/<repo>            (project root)
        #             /<group...>/<repo>/-/tree/<ref>     (branch tree)
        # We deliberately do NOT treat /-/blob/, /-/raw/, /-/edit/ … as
        # clone targets — those URLs point at a single file and should
        # route to ``download`` (via ``to_download_url``).
        segs = parsed.segments
        if not segs:
            return None
        if "-" in segs:
            idx = segs.index("-")
            project_segs = segs[:idx]
            post = segs[idx + 1:]
            # After "/-/" only a tree-at-branch URL (no extra path) is
            # a clone target.
            if not post or post[0] != "tree":
                return None
            # /-/tree/<ref> or /-/tree exactly — clone the repo. With a
            # path after the ref (`/-/tree/<ref>/<path>`) the URL is
            # ambiguous (dir vs file); we conservatively decline so the
            # router can fall through to download (if the adapter
            # recognises it) or the user can shorten the URL.
            if len(post) > 2:
                return None
        else:
            project_segs = segs
        if len(project_segs) < 2:
            return None
        project = "/".join(strip_git_suffix(s) for s in project_segs)
        return f"https://{self._host(parsed)}/{project}.git"

    def to_download_url(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if "-" not in segs:
            return None
        idx = segs.index("-")
        if idx + 2 >= len(segs):
            return None
        kind = segs[idx + 1]
        if kind not in {"blob", "raw"}:
            return None
        project = "/".join(strip_git_suffix(s) for s in segs[:idx])
        ref = segs[idx + 2]
        path = "/".join(segs[idx + 3:])
        if not path:
            return None
        # /-/raw/ URLs are already raw — return as-is. /-/blob/ URLs
        # get rewritten to their raw counterpart.
        return f"https://{self._host(parsed)}/{project}/-/raw/{ref}/{path}"

    def project_name(self, parsed: ParsedUrl) -> str | None:
        segs = parsed.segments
        if "-" in segs:
            segs = segs[: segs.index("-")]
        if not segs:
            return None
        return strip_git_suffix(segs[-1])
