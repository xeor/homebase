"""URL normalization and tab matching.

Policy-driven so e.g. GitHub fragments can be preserved while tracking params
are stripped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEFAULT_STRIP_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "mc_eid",
        "mc_cid",
        "igshid",
    }
)


@dataclass(frozen=True)
class NormalizePolicy:
    strip_params: frozenset[str] = DEFAULT_STRIP_PARAMS
    keep_fragment: bool = False
    drop_trailing_slash: bool = True
    lowercase_host: bool = True
    keep_fragment_hosts: frozenset[str] = field(default_factory=lambda: frozenset({"github.com"}))


def normalize(url: str, policy: NormalizePolicy | None = None) -> str:
    policy = policy or NormalizePolicy()
    parts = urlsplit(url)

    host = parts.hostname or ""
    if policy.lowercase_host:
        host = host.lower()
    netloc = host
    if parts.port:
        netloc = f"{host}:{parts.port}"

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode([(k, v) for k, v in pairs if k not in policy.strip_params])

    path = parts.path
    if policy.drop_trailing_slash and len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    keep_fragment = policy.keep_fragment or host in policy.keep_fragment_hosts
    fragment = parts.fragment if keep_fragment else ""

    return urlunsplit((parts.scheme.lower(), netloc, path, query, fragment))


def same(a: str, b: str, policy: NormalizePolicy | None = None) -> bool:
    return normalize(a, policy) == normalize(b, policy)
