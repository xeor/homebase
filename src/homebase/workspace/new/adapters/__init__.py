from __future__ import annotations

from typing import Mapping

from .base import ParsedUrl, UrlAdapter, parse_url, strip_git_suffix
from .bitbucket import BitbucketAdapter
from .gitea import CodebergAdapter, GiteaAdapter
from .github import GithubAdapter
from .gitlab import GitlabAdapter
from .sourcehut import SourcehutAdapter

_BY_KEY: dict[str, UrlAdapter] = {}
_BY_CANONICAL_HOST: dict[str, UrlAdapter] = {}


def _register(adapter_cls: type[UrlAdapter]) -> None:
    instance = adapter_cls()
    if not instance.key:
        raise ValueError(f"adapter {adapter_cls.__name__} missing key")
    if instance.key in _BY_KEY:
        raise ValueError(f"adapter key already registered: {instance.key}")
    _BY_KEY[instance.key] = instance
    for host in instance.canonical_hosts:
        _BY_CANONICAL_HOST[host] = instance


for _cls in (
    GithubAdapter,
    GitlabAdapter,
    BitbucketAdapter,
    GiteaAdapter,
    CodebergAdapter,
    SourcehutAdapter,
):
    _register(_cls)


def adapter_for_key(key: str) -> UrlAdapter | None:
    return _BY_KEY.get(key)


def adapter_for_host(
    host: str,
    user_hosts: Mapping[str, str] | None = None,
) -> UrlAdapter | None:
    """Resolve a hostname (or 'host/subpath') to an adapter.

    Precedence: longest-prefix match in `user_hosts` first, then the
    built-in canonical hosts. Allows users to remap e.g. github.com to
    a different adapter if they really want.
    """
    if user_hosts:
        candidates = sorted(user_hosts.keys(), key=len, reverse=True)
        for prefix in candidates:
            if host == prefix or host.startswith(prefix + "/"):
                key = user_hosts[prefix]
                hit = _BY_KEY.get(key)
                if hit is not None:
                    return hit
    return _BY_CANONICAL_HOST.get(host)


def all_adapters() -> list[UrlAdapter]:
    return list(_BY_KEY.values())


__all__ = [
    "ParsedUrl",
    "UrlAdapter",
    "adapter_for_host",
    "adapter_for_key",
    "all_adapters",
    "parse_url",
    "strip_git_suffix",
]
