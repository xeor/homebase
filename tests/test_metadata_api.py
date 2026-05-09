from __future__ import annotations

from homebase.metadata import api as metadata_api
from homebase.metadata.api import property_tokens, sync_tag_symlinks


def test_sync_tag_symlinks_does_not_raise_import_error(tmp_path) -> None:
    err = sync_tag_symlinks(tmp_path)
    assert err is None


def test_property_tokens_memoizes_repeated_calls(monkeypatch) -> None:
    metadata_api._PROPERTY_TOKENS_CACHE.clear()
    calls = {"count": 0}
    real_tokens = metadata_api.property_utils.property_tokens

    def counting_tokens(*args, **kwargs):
        calls["count"] += 1
        return real_tokens(*args, **kwargs)

    monkeypatch.setattr(metadata_api.property_utils, "property_tokens", counting_tokens)

    property_tokens(["act"])
    property_tokens(["act"])
    assert calls["count"] == 1

    property_tokens(["doc"])
    assert calls["count"] == 2

    property_tokens(["act"])
    assert calls["count"] == 2
