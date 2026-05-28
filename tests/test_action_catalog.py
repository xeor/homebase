from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.core.constants import BUILTIN_ACTIONS
from homebase.core.models import ProjectRow
from homebase.ui.actions import catalog


def _row(path: Path, **kwargs) -> ProjectRow:
    defaults = dict(
        path=path,
        name=path.name,
        branch="main",
        dirty="",
        last="-",
        src="fs",
        created="-",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        worktree_of="",
        repo_dir="",
    )
    defaults.update(kwargs)
    return ProjectRow(**defaults)


def _make_app(
    *,
    rows: list[ProjectRow] | None = None,
    worktree_issues: list[dict] | None = None,
    worktree_dismissed: bool = False,
    button_actions: list[tuple[str, str]] | None = None,
    valid_items: list[tuple[str, str]] | None = None,
    view_mode: str = "active",
) -> SimpleNamespace:
    rows = rows or []
    return SimpleNamespace(
        ctx=SimpleNamespace(actions={}),
        view_mode=view_mode,
        worktree_health_issues=worktree_issues or [],
        worktree_health_dismissed=worktree_dismissed,
        _visible_button_actions=lambda: button_actions or [],
        _valid_action_items=lambda: valid_items or [],
        _target_rows=lambda: rows,
    )


def test_notification_actions_empty_when_no_issues() -> None:
    app = _make_app()
    assert catalog.notification_actions(app) == []


def test_notification_actions_surfaces_fix_worktrees_when_unhealthy() -> None:
    app = _make_app(
        worktree_issues=[
            {"kind": "orphan_admin", "path": "/a", "detail": "..."},
            {"kind": "orphan_admin", "path": "/b", "detail": "..."},
            {"kind": "stale_gitdir", "path": "/c", "detail": "..."},
        ],
    )
    out = catalog.notification_actions(app)
    assert len(out) == 1
    action_id, label = out[0]
    assert action_id == "fix_worktrees"
    assert "3 issue" in label
    assert "orphan_admin:2" in label
    assert "stale_gitdir:1" in label


def test_notification_actions_silent_when_dismissed() -> None:
    app = _make_app(
        worktree_issues=[{"kind": "orphan_admin", "path": "/a", "detail": ""}],
        worktree_dismissed=True,
    )
    assert catalog.notification_actions(app) == []


def test_scope_for_action_classifies_builtins_by_meta_scope() -> None:
    app = _make_app()
    # workspace-scope builtin → global category
    assert catalog.scope_for_action(app, "fix_worktrees") == catalog.CATEGORY_GLOBAL
    assert catalog.scope_for_action(app, "refresh_cache") == catalog.CATEGORY_GLOBAL
    # target-scope builtin → target category
    assert catalog.scope_for_action(app, "archive") == catalog.CATEGORY_TARGET
    assert catalog.scope_for_action(app, "tags_set") == catalog.CATEGORY_TARGET


def test_scope_for_action_classifies_custom_actions(tmp_path: Path) -> None:
    custom_target = SimpleNamespace(
        id="cust_t", scope="target", source="config", kind="shell"
    )
    custom_global = SimpleNamespace(
        id="cust_g", scope="workspace", source="config", kind="shell"
    )
    app = SimpleNamespace(
        ctx=SimpleNamespace(actions={"cust_t": custom_target, "cust_g": custom_global}),
    )
    assert catalog.scope_for_action(app, "cust_t") == catalog.CATEGORY_TARGET
    assert catalog.scope_for_action(app, "cust_g") == catalog.CATEGORY_GLOBAL


def test_build_picker_catalog_categorizes_known_actions() -> None:
    valid = [
        ("archive", "[white]archive target[/]"),
        ("delete", "[white]delete target[/]"),
        ("refresh_cache", "[white]Refresh cache[/]"),
        ("full_reconcile", "[white]Full reconcile[/]"),
    ]
    app = _make_app(valid_items=valid)
    cat = catalog.build_picker_catalog(app)
    target_ids = {aid for aid, _ in cat[catalog.CATEGORY_TARGET]}
    global_ids = {aid for aid, _ in cat[catalog.CATEGORY_GLOBAL]}
    assert {"archive", "delete"} <= target_ids
    assert {"refresh_cache", "full_reconcile"} <= global_ids
    assert cat[catalog.CATEGORY_NOTIFICATIONS] == []
    assert cat[catalog.CATEGORY_BUTTONS] == []


def test_build_picker_catalog_notifications_appear_first() -> None:
    app = _make_app(
        worktree_issues=[{"kind": "orphan_admin", "path": "/a", "detail": ""}],
        valid_items=[("fix_worktrees", "[white]Fix worktree health[/]")],
    )
    cat = catalog.build_picker_catalog(app)
    notif = cat[catalog.CATEGORY_NOTIFICATIONS]
    assert len(notif) == 1
    assert notif[0][0] == "fix_worktrees"
    # Still also surfaced under Global since it's a workspace action.
    global_ids = {aid for aid, _ in cat[catalog.CATEGORY_GLOBAL]}
    assert "fix_worktrees" in global_ids


def test_build_picker_catalog_excludes_palette_only_actions() -> None:
    valid = [
        ("hooks_refresh", "[white]Refresh hooks on target[/]"),
        ("hooks_refresh_view", "[white]Refresh hooks for current view[/]"),
        ("refresh_cache", "[white]Refresh cache[/]"),
    ]
    app = _make_app(valid_items=valid)
    cat = catalog.build_picker_catalog(app)
    all_ids = {
        aid
        for items in cat.values()
        for aid, _ in items
    }
    assert "hooks_refresh" not in all_ids
    assert "hooks_refresh_view" not in all_ids
    assert "refresh_cache" in all_ids


def test_palette_only_extras_emits_workspace_action_always(tmp_path: Path) -> None:
    app = _make_app()
    extras = catalog.palette_only_extras(app)
    ids = {aid for aid, _label, _cat in extras}
    # workspace-scope: available without targets
    assert "hooks_refresh_view" in ids
    # target-scope: needs targets
    assert "hooks_refresh" not in ids


def test_palette_only_extras_emits_target_action_when_target_present(tmp_path: Path) -> None:
    app = _make_app(rows=[_row(tmp_path / "p")])
    extras = catalog.palette_only_extras(app)
    ids = {aid for aid, _label, _cat in extras}
    assert "hooks_refresh" in ids
    assert "hooks_refresh_view" in ids


def test_no_orphan_builtin_actions() -> None:
    """Every non-tab builtin action must be reachable from either the
    picker catalog or the palette-only extras list. This prevents the
    'action defined but not visible anywhere' regression that the
    Notifications/catalog refactor was built to solve.
    """
    # Statically reachable: actions emitted by valid_action_items in
    # any state, plus actions surfaced by notifications.
    reachable_from_picker = {
        # Buttons (side-panel)
        "readme_create",
        "readme_edit",
        "notes_create",
        "notes_open",
        # Target actions
        "open_selected",
        "tags_set",
        "reconcile_selection_cache",
        "suffix_set",
        "archive",
        "restore",
        "pack",
        "unpack",
        "toggle_pack",
        "delete",
        "set_desc",
        "rename_item",
        "new_worktree",
        "deworktree",
        "review_meta",
        "rename_meta_ext",
        # Global / workspace actions
        "fix_worktrees",
        "refresh_cache",
        "full_reconcile",
        "reconcile_all_cache",
        "edit_global_config",
        "reload_global_config",
    }
    declared = {
        aid for aid, meta in BUILTIN_ACTIONS.items() if meta.scope != "tab"
    }
    missing = declared - reachable_from_picker - catalog.PALETTE_ONLY_ACTION_IDS
    assert not missing, (
        f"Builtin action(s) declared but not surfaced anywhere: {sorted(missing)}. "
        f"Either add to valid_action_items, mark PALETTE_ONLY_ACTION_IDS in catalog.py, "
        f"or remove from BUILTIN_ACTIONS."
    )
