from __future__ import annotations

import re
from abc import ABC
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlparse

_SSH_RE = re.compile(r"^(?P<user>[a-zA-Z0-9_.\-]+)@(?P<host>[a-zA-Z0-9_.\-]+):(?P<path>.+)$")


@dataclass(frozen=True)
class ParsedUrl:
    raw: str
    scheme: str        # "" for SSH form
    host: str
    path: str          # leading "/" stripped, no trailing "/"
    is_ssh: bool

    @property
    def segments(self) -> list[str]:
        return [s for s in self.path.split("/") if s]


def parse_url(value: str) -> ParsedUrl | None:
    if not value:
        return None
    m = _SSH_RE.match(value)
    if m:
        return ParsedUrl(
            raw=value,
            scheme="",
            host=m.group("host"),
            path=m.group("path").strip("/"),
            is_ssh=True,
        )
    if "://" not in value:
        return None
    parsed = urlparse(value)
    if not parsed.netloc:
        return None
    path = (parsed.path or "").strip("/")
    return ParsedUrl(
        raw=value,
        scheme=parsed.scheme,
        host=parsed.netloc,
        path=path,
        is_ssh=False,
    )


def strip_git_suffix(name: str) -> str:
    if name.endswith(".git"):
        return name[:-4]
    return name


class UrlAdapter(ABC):
    """Forge URL adapter. Built-in adapters auto-register on their
    canonical host(s) via the registry; the user can extend the mapping
    via `git.config.hosts`."""

    key: ClassVar[str] = ""
    canonical_hosts: ClassVar[tuple[str, ...]] = ()

    def to_clone_url(self, parsed: ParsedUrl) -> str | None:
        """Return the canonical clone URL for the input, or None if the
        URL doesn't point at a cloneable thing."""
        return None

    def to_download_url(self, parsed: ParsedUrl) -> str | None:
        """Return the raw download URL for the input, or None if the
        URL isn't a file-fetch shape."""
        return None

    def project_name(self, parsed: ParsedUrl) -> str | None:
        """Best-effort repository / project name for the URL."""
        return None
