"""Tests for ``ui/actions/favorites.py``."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import Action
from homebase.ui.actions import favorites

# ---- parse_style_rule(s) --------------------------------------------


def test_parse_style_rule_returns_none_for_non_dict() -> None:
    assert favorites.parse_style_rule("nope") is None
    assert favorites.parse_style_rule(None) is None


def test_parse_style_rule_requires_when() -> None:
    assert favorites.parse_style_rule({"bg_color": "#fff"}) is None


def test_parse_style_rule_requires_visible_change() -> None:
    """A rule with only ``when`` set must drop — there's nothing for it
    to style."""
    assert favorites.parse_style_rule({"when": "tag:wip"}) is None


def test_parse_style_rule_keeps_colors_and_flags() -> None:
    rule = favorites.parse_style_rule(
        {
            "when": "tag:wip",
            "bg_color": "#101010",
            "fg_color": "#fafafa",
            "bold": True,
            "italic": True,
            "underline": False,
        }
    )
    assert rule == {
        "when": "tag:wip",
        "bg_color": "#101010",
        "fg_color": "#fafafa",
        "bold": True,
        "italic": True,
    }


def test_parse_style_rule_accepts_flag_only_rule() -> None:
    rule = favorites.parse_style_rule({"when": "x", "underline": True})
    assert rule == {"when": "x", "underline": True}


def test_parse_style_rules_skips_invalid_entries() -> None:
    out = favorites.parse_style_rules(
        [
            "not-a-dict",
            {"when": "x", "bg_color": "#fff"},
            {"when": ""},  # dropped — no when
        ]
    )
    assert out == [{"when": "x", "bg_color": "#fff"}]


def test_parse_style_rules_empty_returns_empty() -> None:
    assert favorites.parse_style_rules([]) == []
    assert favorites.parse_style_rules("not-a-list") == []


# ---- favorite_surface ----------------------------------------------


def _target_action() -> Action:
    return Action(
        id="archive",
        label="Archive",
        kind="builtin",
        scope="target",
        multi="joined",
    )


def _workspace_action() -> Action:
    return Action(
        id="full_reconcile",
        label="Full reconcile",
        kind="shell",
        scope="workspace",
        multi="joined",
    )


def test_favorite_surface_tab_target_is_nav() -> None:
    assert favorites.favorite_surface("tab:projects/log", {}) == "nav"
    assert favorites.favorite_surface("tab.info.events", {}) == "nav"


def test_favorite_surface_target_action_is_hotbar() -> None:
    actions = {"archive": _target_action()}
    assert favorites.favorite_surface("archive", actions) == "hotbar"
    assert favorites.favorite_surface("action:archive", actions) == "hotbar"


def test_favorite_surface_workspace_action_is_global() -> None:
    actions = {"full_reconcile": _workspace_action()}
    assert favorites.favorite_surface("full_reconcile", actions) == "global"


def test_favorite_surface_unknown_target_falls_back_to_nav() -> None:
    assert favorites.favorite_surface("does_not_exist", {}) == "nav"


# ---- bindings_from_ctx ----------------------------------------------


def _ctx(*, favs=None) -> SimpleNamespace:
    return SimpleNamespace(favorites=list(favs or []))


def test_bindings_from_ctx_returns_independent_copies() -> None:
    ctx = _ctx(favs=[{"id": "x", "target": "build", "favorite": True}])
    out = favorites.bindings_from_ctx(ctx)
    assert out == [{"id": "x", "target": "build", "favorite": True}]
    out[0]["target"] = "mutated"
    assert ctx.favorites[0]["target"] == "build"


# ---- save_bindings --------------------------------------------------


def test_save_bindings_writes_favorites_yaml(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    bindings = [
        {"target": "build", "favorite": True, "label": "Build"},
        {"target": "lint", "hotkey": "F5"},
        {"target": "", "favorite": True},  # dropped, no target
    ]
    favorites.save_bindings(tmp_path, bindings)
    from homebase.config.prefs import load_global_config_dict
    cfg = load_global_config_dict(tmp_path)
    assert cfg["favorites"] == [
        {"id": "fav_1", "target": "build", "favorite": True, "label": "Build"},
        {"id": "fav_2", "target": "lint", "hotkey": "f5"},
    ]


def test_save_bindings_serialises_style_rules(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    bindings = [
        {
            "target": "build",
            "favorite": True,
            "style": [{"when": "tag:wip", "bg_color": "#000"}],
        }
    ]
    favorites.save_bindings(tmp_path, bindings)
    from homebase.config.prefs import load_global_config_dict
    cfg = load_global_config_dict(tmp_path)
    assert cfg["favorites"][0]["style"] == [
        {"when": "tag:wip", "bg_color": "#000"}
    ]


# ---- hotbar bar (slot) index / cycle --------------------------------


def _make_app(
    *,
    targets: list[str] | None = None,
    hotbar_idx: int = 0,
    custom_hotkeys: list[dict[str, object]] | None = None,
    actions: dict[str, Action] | None = None,
) -> SimpleNamespace:
    app = SimpleNamespace()
    app._targets = targets or []
    app.hotbar_selected_index = hotbar_idx
    app.custom_hotkeys = list(custom_hotkeys or [])
    app.actions = dict(actions or {})
    app.base_dir = Path("/tmp/fake")
    app.logs: list[tuple[str, str]] = []
    app.runtime_errors: list[tuple[str, Exception]] = []
    app.mark_state_dirty_calls = 0
    app.refresh_calls = 0
    app._log = lambda msg, level="info": app.logs.append((msg, level))
    app._show_runtime_error = lambda ctx, exc: app.runtime_errors.append((ctx, exc))
    app._mark_state_dirty = lambda: setattr(
        app, "mark_state_dirty_calls", app.mark_state_dirty_calls + 1
    )
    app._refresh_search_display = lambda: setattr(
        app, "refresh_calls", app.refresh_calls + 1
    )
    return app


def _patch_slot_targets(monkeypatch, app) -> None:
    monkeypatch.setattr(favorites, "hotbar_slot_targets", lambda a: a._targets)


def test_hotbar_visible_reflects_slot_targets(monkeypatch) -> None:
    app = _make_app(targets=["a", "b"])
    _patch_slot_targets(monkeypatch, app)
    assert favorites.hotbar_visible(app) is True

    app2 = _make_app(targets=[])
    _patch_slot_targets(monkeypatch, app2)
    assert favorites.hotbar_visible(app2) is False


def test_normalize_hotbar_index_resets_when_empty(monkeypatch) -> None:
    app = _make_app(targets=[], hotbar_idx=42)
    _patch_slot_targets(monkeypatch, app)
    favorites.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 0


def test_normalize_hotbar_index_clamps_to_last(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=99)
    _patch_slot_targets(monkeypatch, app)
    favorites.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 2


def test_normalize_hotbar_index_clamps_negative(monkeypatch) -> None:
    app = _make_app(targets=["a", "b"], hotbar_idx=-5)
    _patch_slot_targets(monkeypatch, app)
    favorites.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 0


def test_selected_hotbar_slot_target_empty_returns_blank(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_slot_targets(monkeypatch, app)
    assert favorites.selected_hotbar_slot_target(app) == ""


def test_selected_hotbar_slot_target_returns_current(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=1)
    _patch_slot_targets(monkeypatch, app)
    assert favorites.selected_hotbar_slot_target(app) == "b"


def test_cycle_hotbar_slot_noop_when_empty(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_slot_targets(monkeypatch, app)
    assert favorites.cycle_hotbar_slot(app, 1) is False
    assert app.mark_state_dirty_calls == 0
    assert app.refresh_calls == 0


def test_cycle_hotbar_slot_wraps_forward(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=2)
    _patch_slot_targets(monkeypatch, app)
    assert favorites.cycle_hotbar_slot(app, 1) is True
    assert app.hotbar_selected_index == 0
    assert app.mark_state_dirty_calls == 1
    assert app.refresh_calls == 1


def test_cycle_hotbar_slot_wraps_backward(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=0)
    _patch_slot_targets(monkeypatch, app)
    assert favorites.cycle_hotbar_slot(app, -1) is True
    assert app.hotbar_selected_index == 2


# ---- toggle_favorite_target ---------------------------------------


def test_toggle_rejects_blank_target() -> None:
    app = _make_app()
    assert favorites.toggle_favorite_target(app, "") is False


def test_toggle_accepts_workspace_scope_action(monkeypatch) -> None:
    """The unified toggle has no scope gate: workspace-scope actions
    become favorites that render in the Favorites list (not on the bar)."""
    workspace_action = Action(
        id="full_reconcile",
        label="Full reconcile",
        kind="shell",
        scope="workspace",
        multi="joined",
    )
    app = _make_app(actions={"full_reconcile": workspace_action})
    _patch_slot_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = favorites.toggle_favorite_target(
        app, "full_reconcile", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[-1] == [
        {"id": "fav_1", "target": "full_reconcile", "favorite": True}
    ]


def test_toggle_accepts_tab_target(monkeypatch) -> None:
    """tab:... targets become favorites that render as nav jumps."""
    app = _make_app()
    _patch_slot_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = favorites.toggle_favorite_target(
        app, "tab.projects.log", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[-1][0]["target"] == "tab.projects.log"
    assert captured[-1][0]["favorite"] is True


def test_toggle_adds_new_target(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_slot_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []

    out = favorites.toggle_favorite_target(
        app, "build", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[0] == [{"id": "fav_1", "target": "build", "favorite": True}]
    assert app.custom_hotkeys == captured[0]
    assert app.mark_state_dirty_calls == 1
    assert app.refresh_calls == 1


def test_toggle_removes_target_with_no_hotkey(monkeypatch) -> None:
    """If the entry only existed as a favorite, toggling off deletes
    the binding entirely (no orphan rows)."""
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[{"id": "fav_1", "target": "build", "favorite": True}],
    )
    _patch_slot_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = favorites.toggle_favorite_target(
        app, "build", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[-1] == []
    assert app.custom_hotkeys == []


def test_toggle_removes_only_favorite_flag_when_hotkey_still_bound(monkeypatch) -> None:
    """A binding that also has a hotkey must lose only the favorite
    flag, keeping the hotkey assignment intact."""
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[
            {"id": "k1", "target": "build", "hotkey": "f5", "favorite": True}
        ],
    )
    _patch_slot_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = favorites.toggle_favorite_target(
        app, "build", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[-1] == [{"id": "k1", "target": "build", "hotkey": "f5"}]


def test_toggle_surfaces_save_errors(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_slot_targets(monkeypatch, app)

    def _boom(_bindings):
        raise OSError("disk full")

    out = favorites.toggle_favorite_target(
        app, "build", save_bindings_fn=_boom
    )
    assert out is False
    assert app.runtime_errors and isinstance(app.runtime_errors[0][1], OSError)


def test_toggle_remove_path_surfaces_save_errors(monkeypatch) -> None:
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[{"id": "fav_1", "target": "build", "favorite": True}],
    )
    _patch_slot_targets(monkeypatch, app)

    def _boom(_bindings):
        raise OSError("disk full")

    out = favorites.toggle_favorite_target(
        app, "build", save_bindings_fn=_boom
    )
    assert out is False
    assert app.runtime_errors
    assert app.custom_hotkeys == [
        {"id": "fav_1", "target": "build", "favorite": True}
    ]


# ---- target_is_favorite --------------------------------------------


def test_target_is_favorite_handles_action_prefix() -> None:
    """The palette passes ``action:build`` but the favorites store
    ``build`` — normalisation must make these match."""
    app = _make_app(
        custom_hotkeys=[{"id": "fav_1", "target": "build", "favorite": True}],
    )
    assert favorites.target_is_favorite(app, "action:build") is True


def test_target_is_favorite_blank_returns_false() -> None:
    app = _make_app()
    assert favorites.target_is_favorite(app, "") is False


def test_target_is_favorite_not_starred() -> None:
    app = _make_app(
        custom_hotkeys=[{"id": "fav_1", "target": "lint", "favorite": True}],
    )
    assert favorites.target_is_favorite(app, "build") is False


# ---- favorite_target_label ----------------------------------------


def _label_app(
    *,
    custom_labels: dict[str, str] | None = None,
    valid_items: list[tuple[str, str]] | None = None,
    actions: dict[str, Action] | None = None,
) -> SimpleNamespace:
    app = SimpleNamespace()
    app._favorite_target_custom_label_map = lambda: custom_labels or {}
    app._valid_action_items = lambda: valid_items or []
    app._label_plain = lambda label: label.replace("[bold]", "").replace("[/]", "")
    app.actions = dict(actions or {})
    return app


def test_favorite_target_label_blank_returns_blank() -> None:
    app = _label_app()
    assert favorites.favorite_target_label(app, "") == ""


def test_favorite_target_label_user_override_wins() -> None:
    app = _label_app(custom_labels={"build": "My Build"})
    assert favorites.favorite_target_label(app, "build") == "My Build"


def test_favorite_target_label_tab_colon_form() -> None:
    app = _label_app()
    assert favorites.favorite_target_label(app, "tab:settings") == "settings"


def test_favorite_target_label_tab_dot_form() -> None:
    app = _label_app()
    assert favorites.favorite_target_label(app, "tab.info") == "info"


def test_favorite_target_label_strips_action_prefix_and_uses_valid_item() -> None:
    app = _label_app(valid_items=[("build", "[bold]Build[/]")])
    assert favorites.favorite_target_label(app, "action:build") == "Build"


def test_favorite_target_label_falls_back_to_action_label() -> None:
    action = Action(
        id="build",
        label="Build it",
        kind="shell",
        scope="target",
        multi="joined",
    )
    app = _label_app(actions={"build": action})
    assert favorites.favorite_target_label(app, "build") == "Build it"


def test_favorite_target_label_unknown_target_returns_self() -> None:
    app = _label_app()
    assert favorites.favorite_target_label(app, "mystery") == "mystery"
