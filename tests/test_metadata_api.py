from __future__ import annotations

from homebase.metadata.api import sync_tag_symlinks


def test_sync_tag_symlinks_does_not_raise_import_error(tmp_path) -> None:
    err = sync_tag_symlinks(tmp_path)
    assert err is None
