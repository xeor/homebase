"""Tests for the pure helpers in ``workspace/new/sources/download.py``."""
from __future__ import annotations

from typing import Any

from homebase.workspace.new.sources import download as dl

# ---- _apply_url_rewrites --------------------------------------------


def test_apply_url_rewrites_no_rules_returns_input() -> None:
    assert dl._apply_url_rewrites("https://example.com/x", []) == "https://example.com/x"


def test_apply_url_rewrites_first_match_wins() -> None:
    rewrites = [
        {"match": r"https://a/", "rewrite": "https://A/"},
        {"match": r"https://a/", "rewrite": "https://NEVER/"},
    ]
    assert dl._apply_url_rewrites("https://a/repo", rewrites) == "https://A/repo"


def test_apply_url_rewrites_only_replaces_one_occurrence() -> None:
    """``re.subn`` is invoked with ``count=1`` so a URL containing
    multiple matches only has its first rewritten."""
    rewrites = [{"match": r"abc", "rewrite": "XYZ"}]
    out = dl._apply_url_rewrites("abc-abc-abc", rewrites)
    assert out == "XYZ-abc-abc"


def test_apply_url_rewrites_skips_non_string_entries() -> None:
    rewrites: list[dict] = [
        {"match": 1, "rewrite": "foo"},
        {"match": "x", "rewrite": 2},
        {"match": "x", "rewrite": "Y"},
    ]
    assert dl._apply_url_rewrites("x marks the spot", rewrites) == "Y marks the spot"


def test_apply_url_rewrites_skips_invalid_regex() -> None:
    """A malformed regex (unmatched ``(``) must not blow up — the
    helper just skips that rule."""
    rewrites = [
        {"match": r"(", "rewrite": "x"},
        {"match": r"foo", "rewrite": "FOO"},
    ]
    assert dl._apply_url_rewrites("foo bar", rewrites) == "FOO bar"


def test_apply_url_rewrites_unchanged_when_nothing_matches() -> None:
    rewrites = [{"match": r"nope", "rewrite": "x"}]
    assert dl._apply_url_rewrites("foo", rewrites) == "foo"


# ---- resolve_download_url -------------------------------------------


def test_resolve_download_url_falls_through_for_non_url() -> None:
    """A bare string that doesn't parse as a URL goes through the
    rewrites untouched (rewrites can still rewrite anything)."""
    out = dl.resolve_download_url(
        "not-a-url",
        user_hosts={},
        rewrites=[{"match": r"not-a-url", "rewrite": "REWRITTEN"}],
    )
    assert out == "REWRITTEN"


def test_resolve_download_url_uses_github_adapter() -> None:
    """A GitHub blob URL gets canonicalised by the GitHub adapter into
    the corresponding raw-content URL."""
    out = dl.resolve_download_url(
        "https://github.com/owner/repo/blob/main/README.md",
        user_hosts={},
        rewrites=[],
    )
    assert "raw.githubusercontent.com" in out or "raw=true" in out or out.endswith("README.md")


def test_resolve_download_url_falls_back_to_rewrites_when_adapter_yields_none(
    monkeypatch,
) -> None:
    """If the adapter returns nothing the helper still applies any
    user rewrites to the original URL."""
    class _ParsedStub:
        host = "example.com"

    class _AdapterStub:
        def to_download_url(self, _parsed: object) -> str | None:
            return None

    monkeypatch.setattr(dl, "parse_url", lambda _u: _ParsedStub())
    monkeypatch.setattr(dl, "adapter_for_host", lambda _h, _hosts: _AdapterStub())
    out = dl.resolve_download_url(
        "https://example.com/x",
        user_hosts={},
        rewrites=[{"match": r"example", "rewrite": "EXAMPLE"}],
    )
    assert out == "https://EXAMPLE.com/x"


# ---- _filename_from -------------------------------------------------


class _Headers:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, key, default=""):
        return self.mapping.get(key, default)


class _Resp:
    def __init__(self, headers):
        self.headers = headers


def test_filename_from_uses_content_disposition() -> None:
    resp = _Resp(_Headers({"Content-Disposition": 'attachment; filename="kitten.png"'}))
    assert dl._filename_from("https://example.com/p", resp) == "kitten.png"


def test_filename_from_uses_url_tail_when_no_disposition() -> None:
    resp = _Resp(_Headers({}))
    assert dl._filename_from("https://example.com/dir/file.txt", resp) == "file.txt"


def test_filename_from_strips_trailing_slash() -> None:
    resp = _Resp(_Headers({}))
    assert dl._filename_from("https://example.com/dir/", resp) == "dir"


def test_filename_from_uses_host_when_no_path_segment() -> None:
    """``https://example.com/`` has no path tail — the rstrip+split
    falls back to ``example.com`` (better than an empty string)."""
    resp = _Resp(_Headers({}))
    assert dl._filename_from("https://example.com/", resp) == "example.com"


def test_filename_from_falls_back_to_download_for_empty_input() -> None:
    resp = _Resp(_Headers({}))
    assert dl._filename_from("", resp) == "download"


def test_filename_from_strips_query_string() -> None:
    resp = _Resp(_Headers({}))
    assert dl._filename_from("https://example.com/file.zip?token=abc", resp) == "file.zip"


def test_filename_from_handles_response_without_headers() -> None:
    """Some test responses don't expose ``.headers`` — the helper
    falls straight through to URL parsing."""
    class _Bare:
        pass

    assert dl._filename_from("https://example.com/x.bin", _Bare()) == "x.bin"


def test_filename_from_handles_disposition_without_quotes() -> None:
    """``Content-Disposition`` filenames can be unquoted — the regex
    accepts both forms."""
    resp = _Resp(_Headers({"Content-Disposition": "attachment; filename=plain.zip"}))
    assert dl._filename_from("https://example.com/x", resp) == "plain.zip"


# ---- DownloadSource._user_hosts / _rewrites -------------------------


def _make_source(config: dict) -> Any:
    from homebase.workspace.new.sources.download import DownloadSource

    return DownloadSource(config=config)


def test_user_hosts_returns_empty_when_no_config() -> None:
    src = _make_source({})
    assert src._user_hosts() == {}


def test_user_hosts_coerces_values_to_str() -> None:
    src = _make_source({"hosts": {"my.gitlab": "gitlab", 42: "github"}})
    out = src._user_hosts()
    assert out == {"my.gitlab": "gitlab", "42": "github"}


def test_user_hosts_returns_empty_when_not_dict() -> None:
    src = _make_source({"hosts": ["nope"]})
    assert src._user_hosts() == {}


def test_rewrites_returns_empty_when_unset() -> None:
    src = _make_source({})
    assert src._rewrites() == []


def test_rewrites_returns_empty_when_not_list() -> None:
    src = _make_source({"url_rewrites": "bad"})
    assert src._rewrites() == []


def test_rewrites_filters_non_dict_entries() -> None:
    src = _make_source({
        "url_rewrites": [
            {"match": "a", "rewrite": "A"},
            "not-a-dict",
            None,
            {"match": "b", "rewrite": "B"},
        ],
    })
    out = src._rewrites()
    assert out == [{"match": "a", "rewrite": "A"}, {"match": "b", "rewrite": "B"}]


# ---- DownloadSource.detects / infer_name ----------------------------


def test_detects_true_for_url() -> None:
    src = _make_source({})
    assert src.detects("https://example.com/p", None) is True


def test_detects_false_for_bare_name() -> None:
    src = _make_source({})
    assert src.detects("bare-name", None) is False


def test_detects_false_for_empty_input() -> None:
    src = _make_source({})
    assert src.detects("", None) is False
    assert src.detects(None, None) is False


def test_infer_name_returns_none_for_empty_input() -> None:
    src = _make_source({})
    assert src.infer_name("", None) is None
    assert src.infer_name(None, None) is None


def test_infer_name_uses_tail_stem_for_plain_url() -> None:
    src = _make_source({})
    # No adapter-specific routing for example.com → fall back to the
    # final path segment's stem.
    out = src.infer_name("https://example.com/p/q/report.tar.gz", None)
    assert out is not None
    assert out in {"report.tar", "report.tar.gz", "report"}


def test_infer_name_for_non_url_uses_tail_segment() -> None:
    src = _make_source({})
    out = src.infer_name("path/to/blob.bin", None)
    assert out == "blob"
