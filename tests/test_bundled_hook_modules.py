from __future__ import annotations

import importlib


def _import(dotted: str) -> object:
    return importlib.import_module(dotted)


def test_bundled_post_delete_tag_symlink_sync_reexports_run() -> None:
    mod = _import("homebase.hooks.bundled.post.delete.tag_symlink_sync")
    common = _import("homebase.hooks.bundled.post._tag_symlink_sync_common")
    assert mod.run is common.run_tag_symlink_sync


def test_bundled_post_new_project_tag_symlink_sync_reexports_run() -> None:
    mod = _import("homebase.hooks.bundled.post.new_project.tag_symlink_sync")
    common = _import("homebase.hooks.bundled.post._tag_symlink_sync_common")
    assert mod.run is common.run_tag_symlink_sync


def test_bundled_post_rename_tag_symlink_sync_reexports_run() -> None:
    mod = _import("homebase.hooks.bundled.post.rename.tag_symlink_sync")
    common = _import("homebase.hooks.bundled.post._tag_symlink_sync_common")
    assert mod.run is common.run_tag_symlink_sync


def test_bundled_post_tag_change_tag_symlink_sync_reexports_run() -> None:
    mod = _import("homebase.hooks.bundled.post.tag_change.tag_symlink_sync")
    common = _import("homebase.hooks.bundled.post._tag_symlink_sync_common")
    assert mod.run is common.run_tag_symlink_sync


def test_bundled_pre_new_project_package_imports_cleanly() -> None:
    mod = _import("homebase.hooks.bundled.pre.new_project")
    assert hasattr(mod, "__name__")


def test_bundled_pre_rename_package_imports_cleanly() -> None:
    mod = _import("homebase.hooks.bundled.pre.rename")
    assert hasattr(mod, "__name__")


def test_bundled_pre_tag_change_package_imports_cleanly() -> None:
    mod = _import("homebase.hooks.bundled.pre.tag_change")
    assert hasattr(mod, "__name__")


def test_main_entry_point_module_imports_cleanly() -> None:
    mod = _import("homebase.__main__")
    assert hasattr(mod, "__name__")
