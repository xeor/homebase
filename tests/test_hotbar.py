"""Tests for ``ui/actions/hotbar.py``."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import Action
from homebase.ui.actions import hotbar

# ---- parse_style_rule(s) --------------------------------------------


def test_parse_style_rule_returns_none_for_non_dict() -> None:
    assert hotbar.parse_style_rule("nope") is None
    assert hotbar.parse_style_rule(None) is None


def test_parse_style_rule_requires_when() -> None:
    assert hotbar.parse_style_rule({"bg_color": "#fff"}) is None


def test_parse_style_rule_requires_visible_change() -> None:
    """A rule with only ``when`` set must drop — there's nothing for it
    to style."""
    assert hotbar.parse_style_rule({"when": "tag:wip"}) is None


def test_parse_style_rule_keeps_colors_and_flags() -> None:
    rule = hotbar.parse_style_rule(
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
    rule = hotbar.parse_style_rule({"when": "x", "underline": True})
    assert rule == {"when": "x", "underline": True}


def test_parse_style_rules_skips_invalid_entries() -> None:
    out = hotbar.parse_style_rules(
        [
            "not-a-dict",
            {"when": "x", "bg_color": "#fff"},
            {"when": ""},  # dropped — no when
        ]
    )
    assert out == [{"when": "x", "bg_color": "#fff"}]


def test_parse_style_rules_empty_returns_empty() -> None:
    assert hotbar.parse_style_rules([]) == []
    assert hotbar.parse_style_rules("not-a-list") == []


# ---- bindings_from_ctx ----------------------------------------------


def _ctx(*, hotbar=None, keys=None, custom_hotkeys=None) -> SimpleNamespace:
    return SimpleNamespace(
        hotbar=hotbar or [],
        keys=keys or {},
        custom_hotkeys=custom_hotkeys or [],
    )


def test_bindings_from_ctx_uses_legacy_custom_when_others_empty() -> None:
    """If the user already migrated to the unified ``custom_hotkeys``
    shape, the loader must copy through verbatim."""
    ctx = _ctx(custom_hotkeys=[{"id": "x", "target": "build", "hotbar": True}])
    out = hotbar.bindings_from_ctx(ctx)
    assert out == [{"id": "x", "target": "build", "hotbar": True}]
    # Copies are independent (mutating must not bleed back into ctx).
    out[0]["target"] = "mutated"
    assert ctx.custom_hotkeys[0]["target"] == "build"


def test_bindings_from_ctx_renumbers_hotbar_entries() -> None:
    ctx = _ctx(
        hotbar=[{"action": "build"}, {"action": "lint", "label": "Lint"}],
    )
    out = hotbar.bindings_from_ctx(ctx)
    assert out[0]["id"] == "hotbar_1"
    assert out[0]["target"] == "build"
    assert out[0]["hotbar"] is True
    assert "label" not in out[0]
    assert out[1] == {
        "id": "hotbar_2",
        "target": "lint",
        "hotbar": True,
        "label": "Lint",
    }


def test_bindings_from_ctx_skips_hotbar_entries_with_no_action() -> None:
    ctx = _ctx(hotbar=[{"action": ""}, {"action": "build"}])
    out = hotbar.bindings_from_ctx(ctx)
    assert [row["target"] for row in out] == ["build"]


def test_bindings_from_ctx_normalises_hotkeys_lowercase() -> None:
    ctx = _ctx(keys={"Ctrl+B": {"action": "build"}})
    out = hotbar.bindings_from_ctx(ctx)
    assert out == [
        {"id": "key_1", "target": "build", "hotkey": "ctrl+b"},
    ]


def test_bindings_from_ctx_keeps_label_for_keys() -> None:
    ctx = _ctx(keys={"f5": {"action": "build", "label": "Build"}})
    out = hotbar.bindings_from_ctx(ctx)
    assert out[0]["label"] == "Build"


def test_bindings_from_ctx_attaches_style_rules() -> None:
    ctx = _ctx(
        hotbar=[
            {
                "action": "build",
                "style": [{"when": "tag:wip", "bg_color": "#fff"}],
            }
        ],
    )
    out = hotbar.bindings_from_ctx(ctx)
    assert out[0]["style"] == [{"when": "tag:wip", "bg_color": "#fff"}]


# ---- save_bindings --------------------------------------------------


def test_save_bindings_round_trips_hotbar_and_keys(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    bindings = [
        {"target": "build", "hotbar": True, "label": "Build"},
        {"target": "lint", "hotkey": "F5"},
        {"target": "", "hotbar": True},  # dropped, no target
    ]
    hotbar.save_bindings(tmp_path, bindings)
    # Read it back from the global config.
    from homebase.config.prefs import load_global_config_dict
    cfg = load_global_config_dict(tmp_path)
    assert cfg["hotbar"] == [{"action": "build", "label": "Build"}]
    assert cfg["keys"] == {"f5": {"action": "lint"}}


def test_save_bindings_serialises_style_rules(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    bindings = [
        {
            "target": "build",
            "hotbar": True,
            "style": [{"when": "tag:wip", "bg_color": "#000"}],
        }
    ]
    hotbar.save_bindings(tmp_path, bindings)
    from homebase.config.prefs import load_global_config_dict
    cfg = load_global_config_dict(tmp_path)
    assert cfg["hotbar"][0]["style"] == [
        {"when": "tag:wip", "bg_color": "#000"}
    ]


# ---- hotbar index / cycle ------------------------------------------


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


def _patch_hotbar_targets(monkeypatch, app) -> None:
    monkeypatch.setattr(hotbar, "hotbar_targets", lambda a: a._targets)


def test_hotbar_visible_reflects_targets(monkeypatch) -> None:
    app = _make_app(targets=["a", "b"])
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.hotbar_visible(app) is True

    app2 = _make_app(targets=[])
    _patch_hotbar_targets(monkeypatch, app2)
    assert hotbar.hotbar_visible(app2) is False


def test_normalize_hotbar_index_resets_when_empty(monkeypatch) -> None:
    app = _make_app(targets=[], hotbar_idx=42)
    _patch_hotbar_targets(monkeypatch, app)
    hotbar.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 0


def test_normalize_hotbar_index_clamps_to_last(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=99)
    _patch_hotbar_targets(monkeypatch, app)
    hotbar.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 2


def test_normalize_hotbar_index_clamps_negative(monkeypatch) -> None:
    app = _make_app(targets=["a", "b"], hotbar_idx=-5)
    _patch_hotbar_targets(monkeypatch, app)
    hotbar.normalize_hotbar_index(app)
    assert app.hotbar_selected_index == 0


def test_selected_hotbar_target_empty_returns_blank(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.selected_hotbar_target(app) == ""


def test_selected_hotbar_target_returns_current(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=1)
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.selected_hotbar_target(app) == "b"


def test_cycle_hotbar_noop_when_empty(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.cycle_hotbar(app, 1) is False
    assert app.mark_state_dirty_calls == 0
    assert app.refresh_calls == 0


def test_cycle_hotbar_wraps_forward(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=2)
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.cycle_hotbar(app, 1) is True
    assert app.hotbar_selected_index == 0
    assert app.mark_state_dirty_calls == 1
    assert app.refresh_calls == 1


def test_cycle_hotbar_wraps_backward(monkeypatch) -> None:
    app = _make_app(targets=["a", "b", "c"], hotbar_idx=0)
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.cycle_hotbar(app, -1) is True
    assert app.hotbar_selected_index == 2


# ---- toggle_hotbar_target_from_palette -------------------------------


def test_toggle_rejects_blank_target() -> None:
    app = _make_app()
    assert hotbar.toggle_hotbar_target_from_palette(app, "") is False


def test_toggle_rejects_non_target_scope_actions() -> None:
    """Workspace-scope actions cannot live on the hotbar — the hotbar
    is per-row only."""
    workspace_action = Action(
        id="full_reconcile",
        label="Full reconcile",
        kind="shell",
        scope="workspace",
        multi="joined",
        command=None,
    )
    app = _make_app(actions={"full_reconcile": workspace_action})
    out = hotbar.toggle_hotbar_target_from_palette(app, "full_reconcile")
    assert out is False
    assert app.logs[0][1] == "warn"
    assert "only target-scope" in app.logs[0][0]


def test_toggle_adds_new_target_to_hotbar(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_hotbar_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []

    def _save(bindings):
        captured.append(bindings)

    out = hotbar.toggle_hotbar_target_from_palette(
        app, "build", save_bindings_fn=_save
    )
    assert out is True
    assert captured[0] == [{"id": "hotbar_1", "target": "build", "hotbar": True}]
    assert app.custom_hotkeys == captured[0]
    assert app.mark_state_dirty_calls == 1
    assert app.refresh_calls == 1


def test_toggle_removes_target_with_no_hotkey(monkeypatch) -> None:
    """If the entry only existed for its hotbar pin, toggling off
    deletes the binding entirely (no orphan rows)."""
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[{"id": "hotbar_1", "target": "build", "hotbar": True}],
    )
    _patch_hotbar_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = hotbar.toggle_hotbar_target_from_palette(
        app, "build", save_bindings_fn=captured.append
    )
    assert out is True
    assert captured[-1] == []
    assert app.custom_hotkeys == []


def test_toggle_removes_only_hotbar_flag_when_hotkey_still_bound(monkeypatch) -> None:
    """A binding that also has a hotkey must lose only the hotbar
    flag, keeping the hotkey assignment intact."""
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[
            {"id": "k1", "target": "build", "hotkey": "f5", "hotbar": True}
        ],
    )
    _patch_hotbar_targets(monkeypatch, app)
    captured: list[list[dict[str, object]]] = []
    out = hotbar.toggle_hotbar_target_from_palette(
        app, "build", save_bindings_fn=captured.append
    )
    assert out is True
    # Hotkey survives; hotbar flag is gone.
    assert captured[-1] == [{"id": "k1", "target": "build", "hotkey": "f5"}]


def test_toggle_surfaces_save_errors(monkeypatch) -> None:
    app = _make_app(targets=[])
    _patch_hotbar_targets(monkeypatch, app)

    def _boom(_bindings):
        raise OSError("disk full")

    out = hotbar.toggle_hotbar_target_from_palette(
        app, "build", save_bindings_fn=_boom
    )
    assert out is False
    assert app.runtime_errors and isinstance(app.runtime_errors[0][1], OSError)


def test_toggle_remove_path_surfaces_save_errors(monkeypatch) -> None:
    """The remove-and-delete path has its own try/except — make sure
    OSError from save still surfaces and does not corrupt state."""
    app = _make_app(
        targets=["build"],
        custom_hotkeys=[{"id": "hotbar_1", "target": "build", "hotbar": True}],
    )
    _patch_hotbar_targets(monkeypatch, app)

    def _boom(_bindings):
        raise OSError("disk full")

    out = hotbar.toggle_hotbar_target_from_palette(
        app, "build", save_bindings_fn=_boom
    )
    assert out is False
    assert app.runtime_errors
    # custom_hotkeys must remain untouched on failure.
    assert app.custom_hotkeys == [
        {"id": "hotbar_1", "target": "build", "hotbar": True}
    ]


# ---- target_is_hotbar ------------------------------------------------


def test_target_is_hotbar_handles_action_prefix(monkeypatch) -> None:
    """The palette passes ``action:build`` but the hotbar stores
    ``build`` — normalisation must make these match."""
    app = _make_app(targets=["build"])
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.target_is_hotbar(app, "action:build") is True


def test_target_is_hotbar_blank_returns_false() -> None:
    app = _make_app()
    assert hotbar.target_is_hotbar(app, "") is False


def test_target_is_hotbar_not_on_bar(monkeypatch) -> None:
    app = _make_app(targets=["lint"])
    _patch_hotbar_targets(monkeypatch, app)
    assert hotbar.target_is_hotbar(app, "build") is False


# ---- hotbar_target_label --------------------------------------------


def _label_app(
    *,
    custom_labels: dict[str, str] | None = None,
    valid_items: list[tuple[str, str]] | None = None,
    actions: dict[str, Action] | None = None,
) -> SimpleNamespace:
    app = SimpleNamespace()
    app._hotbar_target_custom_label_map = lambda: custom_labels or {}
    app._valid_action_items = lambda: valid_items or []
    app._label_plain = lambda label: label.replace("[bold]", "").replace("[/]", "")
    app.actions = dict(actions or {})
    return app


def test_hotbar_target_label_blank_returns_blank() -> None:
    app = _label_app()
    assert hotbar.hotbar_target_label(app, "") == ""


def test_hotbar_target_label_user_override_wins() -> None:
    app = _label_app(custom_labels={"build": "My Build"})
    assert hotbar.hotbar_target_label(app, "build") == "My Build"


def test_hotbar_target_label_tab_colon_form() -> None:
    app = _label_app()
    assert hotbar.hotbar_target_label(app, "tab:settings") == "settings"


def test_hotbar_target_label_tab_dot_form() -> None:
    app = _label_app()
    assert hotbar.hotbar_target_label(app, "tab.info") == "info"


def test_hotbar_target_label_strips_action_prefix_and_uses_valid_item() -> None:
    app = _label_app(valid_items=[("build", "[bold]Build[/]")])
    assert hotbar.hotbar_target_label(app, "action:build") == "Build"


def test_hotbar_target_label_falls_back_to_action_label() -> None:
    action = Action(
        id="build",
        label="Build it",
        kind="shell",
        scope="target",
        multi="joined",
    )
    app = _label_app(actions={"build": action})
    assert hotbar.hotbar_target_label(app, "build") == "Build it"


def test_hotbar_target_label_unknown_target_returns_self() -> None:
    app = _label_app()
    assert hotbar.hotbar_target_label(app, "mystery") == "mystery"
