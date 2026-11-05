from __future__ import annotations

from homebase.core.config_presets import (
    INTENT_ADD,
    INTENT_KEEP,
    INTENT_REMOVE,
    INTENT_SKIP,
    INTENT_UPDATE,
    STATE_PARTIAL,
    STATE_SET,
    STATE_UNSET,
    ConfigEnv,
    apply_presets,
    build_presets,
    detect_state,
    field_current_value,
    plan_intents,
    preset_is_fully_present,
    preset_is_selected_default,
)


def _catalog() -> list:
    return build_presets(ConfigEnv(platform="darwin"))


def _preset(catalog: list, preset_id: str):
    return next(p for p in catalog if p.id == preset_id)


def test_every_preset_has_tags() -> None:
    # Tags drive the editor's filter (title + tags). Every preset must
    # carry at least one so it stays findable as the catalog grows.
    for preset in _catalog():
        assert preset.tags, preset.id


def test_field_current_value_reads_nested_path() -> None:
    catalog = _catalog()
    tz = _preset(catalog, "archive_timezone").fields[0]
    assert field_current_value(tz, {"archive": {"timezone": "Asia/Tokyo"}}) == (
        "Asia/Tokyo"
    )
    assert field_current_value(tz, {}) is None


def test_detect_state_field_preset() -> None:
    catalog = _catalog()
    preset = _preset(catalog, "archive_timezone")
    assert detect_state(preset, {}) == STATE_UNSET
    assert detect_state(preset, {"archive": {"timezone": "UTC"}}) == STATE_SET


def test_detect_state_fragment_partial() -> None:
    catalog = _catalog()
    preset = _preset(catalog, "saved_filters_starter")
    assert detect_state(preset, {}) == STATE_UNSET
    # only one of the two fragment leaves present and equal
    partial = {"filters": {"saved": ["#wip", ":tags=0", ":modified=@-7d"]}}
    assert detect_state(preset, partial) == STATE_PARTIAL
    full = {
        "filters": {
            "saved": ["#wip", ":tags=0", ":modified=@-7d"],
            "named": {"hot": "#cli OR #api", "stale": ":modified<=@-60d"},
        }
    }
    assert detect_state(preset, full) == STATE_SET


def test_selected_default_uses_state_and_recommendation() -> None:
    catalog = _catalog()
    focus = _preset(catalog, "tmux_focus")
    # unset but recommended on darwin
    assert preset_is_selected_default(focus, {}, ConfigEnv(platform="darwin"))
    assert not preset_is_selected_default(focus, {}, ConfigEnv(platform="linux"))
    # already configured -> selected regardless of platform
    cfg = {"tmux_focus": {"method": "system_events"}}
    assert preset_is_selected_default(focus, cfg, ConfigEnv(platform="linux"))


def test_apply_enable_writes_default_and_override() -> None:
    catalog = _catalog()
    out = apply_presets({}, {"archive_timezone"}, {}, catalog)
    assert out["archive"]["timezone"] == "Europe/Oslo"
    out = apply_presets(
        {}, {"archive_timezone"}, {"archive_timezone": {"timezone": "UTC"}}, catalog
    )
    assert out["archive"]["timezone"] == "UTC"


def test_apply_enable_preserves_existing_value_without_override() -> None:
    catalog = _catalog()
    current = {"archive": {"timezone": "Asia/Tokyo"}}
    out = apply_presets(current, {"archive_timezone"}, {}, catalog)
    assert out["archive"]["timezone"] == "Asia/Tokyo"


def test_apply_disable_removes_owned_field_path() -> None:
    catalog = _catalog()
    # a field path is preset-owned: disable removes it regardless of value
    current = {"archive": {"timezone": "Europe/Oslo"}}
    out = apply_presets(current, set(), {}, catalog)
    assert "archive" not in out
    current = {"archive": {"timezone": "Asia/Tokyo"}}
    out = apply_presets(current, set(), {}, catalog)
    assert "archive" not in out


def test_apply_disable_keeps_unmatched_fragment_leaf() -> None:
    catalog = _catalog()
    # fragment leaves can overlap unrelated config: only remove ones still
    # equal to what the preset wrote (no clobber of hand edits)
    current = {
        "filters": {
            "saved": ["#wip", ":tags=0", ":modified=@-7d"],
            "named": {"hot": "EDITED", "stale": ":modified<=@-60d"},
        }
    }
    out = apply_presets(current, set(), {}, catalog)
    assert out["filters"]["named"] == {"hot": "EDITED"}
    assert "saved" not in out["filters"]


def test_apply_disable_removes_fragment_and_prunes_empty() -> None:
    catalog = _catalog()
    current = {
        "filters": {
            "saved": ["#wip", ":tags=0", ":modified=@-7d"],
            "named": {"hot": "#cli OR #api", "stale": ":modified<=@-60d"},
        }
    }
    out = apply_presets(current, set(), {}, catalog)
    assert "filters" not in out


def test_apply_enable_deep_merges_fragment() -> None:
    catalog = _catalog()
    current = {"properties": {"CUSTOM": {"label": "x"}}}
    out = apply_presets(current, {"property_badges_core"}, {}, catalog)
    assert out["properties"]["CUSTOM"] == {"label": "x"}
    assert out["properties"]["GIT"]["dir-exists"] == [".git"]


def test_plan_intents_add_update_keep_remove_skip() -> None:
    catalog = _catalog()

    # add: enabled, currently unset
    intents = plan_intents({}, {"archive_timezone"}, {}, catalog)
    assert intents["archive_timezone"] == INTENT_ADD

    # keep: enabled, set, no change
    current = {"archive": {"timezone": "UTC"}}
    intents = plan_intents(current, {"archive_timezone"}, {}, catalog)
    assert intents["archive_timezone"] == INTENT_KEEP

    # update: enabled, set, field override differs
    intents = plan_intents(
        current, {"archive_timezone"}, {"archive_timezone": {"timezone": "UTC+1"}}, catalog
    )
    assert intents["archive_timezone"] == INTENT_UPDATE

    # remove: disabled, owned field path present (any value)
    current = {"archive": {"timezone": "Europe/Oslo"}}
    intents = plan_intents(current, set(), {}, catalog)
    assert intents["archive_timezone"] == INTENT_REMOVE

    current = {"archive": {"timezone": "Asia/Tokyo"}}
    intents = plan_intents(current, set(), {}, catalog)
    assert intents["archive_timezone"] == INTENT_REMOVE

    # skip: disabled, unset
    intents = plan_intents({}, set(), {}, catalog)
    assert intents["archive_timezone"] == INTENT_SKIP


def test_list_csv_default_round_trips() -> None:
    catalog = _catalog()
    out = apply_presets({}, {"suffixes"}, {}, catalog)
    assert out["suffixes"] == ["tmp", "fork", "old"]
    out = apply_presets({}, {"suffixes"}, {"suffixes": {"suffixes": ["a", "b"]}}, catalog)
    assert out["suffixes"] == ["a", "b"]


def test_fully_present_requires_every_managed_path() -> None:
    catalog = _catalog()
    preset = _preset(catalog, "saved_filters_starter")
    assert not preset_is_fully_present(preset, {})
    partial = {"filters": {"saved": ["#wip", ":tags=0", ":modified=@-7d"]}}
    assert not preset_is_fully_present(preset, partial)
    full = {
        "filters": {
            "saved": ["#wip", ":tags=0", ":modified=@-7d"],
            "named": {"hot": "EDITED", "stale": ":modified<=@-60d"},
        }
    }
    # present-but-hand-edited still counts as present (enable is non-destructive)
    assert preset_is_fully_present(preset, full)


def test_partial_preset_not_selected_by_default() -> None:
    catalog = _catalog()
    preset = _preset(catalog, "saved_filters_starter")
    partial = {"filters": {"saved": ["#wip", ":tags=0", ":modified=@-7d"]}}
    # partially configured, not recommended -> stays unchecked so its plan
    # defaults to skip, never a forced overwrite/removal
    assert not preset_is_selected_default(preset, partial, ConfigEnv(platform="linux"))


def test_enable_fills_gaps_without_overwriting_present_leaf() -> None:
    catalog = _catalog()
    # one fragment leaf present with a hand-edited value, the rest absent
    current = {"filters": {"saved": ["MINE"]}}
    out = apply_presets(current, {"saved_filters_starter"}, {}, catalog)
    assert out["filters"]["saved"] == ["MINE"]  # not clobbered
    assert "named" in out["filters"]  # gap filled
    # only-adds -> ADD, not UPDATE
    intents = plan_intents(current, {"saved_filters_starter"}, {}, catalog)
    assert intents["saved_filters_starter"] == INTENT_ADD


def test_enable_fully_present_is_keep_and_preserves_edits() -> None:
    catalog = _catalog()
    current = {
        "filters": {
            "saved": ["EDITED"],
            "named": {"hot": "EDITED", "stale": "EDITED"},
        }
    }
    out = apply_presets(current, {"saved_filters_starter"}, {}, catalog)
    assert out["filters"]["saved"] == ["EDITED"]
    assert out["filters"]["named"] == {"hot": "EDITED", "stale": "EDITED"}
    intents = plan_intents(current, {"saved_filters_starter"}, {}, catalog)
    assert intents["saved_filters_starter"] == INTENT_KEEP


def test_removable_ids_gates_disable_to_skip() -> None:
    catalog = _catalog()
    current = {"archive": {"timezone": "Asia/Tokyo"}}
    # disabled + not in the removable baseline -> skip (leave hand-edited config)
    intents = plan_intents(current, set(), {}, catalog, removable_ids=set())
    assert intents["archive_timezone"] == INTENT_SKIP
    out = apply_presets(current, set(), {}, catalog, removable_ids=set())
    assert out["archive"]["timezone"] == "Asia/Tokyo"
    # in the baseline -> removal is allowed again
    intents = plan_intents(
        current, set(), {}, catalog, removable_ids={"archive_timezone"}
    )
    assert intents["archive_timezone"] == INTENT_REMOVE
    out = apply_presets(
        current, set(), {}, catalog, removable_ids={"archive_timezone"}
    )
    assert "archive" not in out
