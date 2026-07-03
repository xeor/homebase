from __future__ import annotations

from typing import Any

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Select, SelectionList

from homebase.core.config_editor import ConfigEditorScreen, ConfigEditorWidget
from homebase.core.config_presets import ConfigEnv, build_presets


class _Host(App[None]):
    def __init__(self, current: dict[str, Any], captured: list) -> None:
        super().__init__()
        self._current = current
        self._captured = captured

    def compose(self) -> ComposeResult:
        yield ConfigEditorWidget(
            build_presets(ConfigEnv(platform="darwin")),
            self._current,
            self._captured.append,
            env=ConfigEnv(platform="darwin"),
        )


@pytest.mark.asyncio
async def test_pre_checks_configured_presets() -> None:
    current = {"archive": {"timezone": "Asia/Tokyo"}}
    app = _Host(current, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        assert "archive_timezone" in widget.enabled
        # recommended on darwin even though unset
        assert "tmux_focus" in widget.enabled
        await pilot.pause()


@pytest.mark.asyncio
async def test_search_filters_list() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        await pilot.press(*"timezone")
        await pilot.pause()
        assert widget._visible_ids == ["archive_timezone"]


@pytest.mark.asyncio
async def test_enter_toggles_highlighted_row() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        sl.focus()
        await pilot.pause()
        top = widget._visible_ids[0]
        was_enabled = top in widget.enabled
        await pilot.press("enter")
        await pilot.pause()
        assert (top in widget.enabled) != was_enabled
        # focus stays on the list across the toggle
        assert app.focused is sl


@pytest.mark.asyncio
async def test_space_is_a_filter_character() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        sl.focus()
        await pilot.pause()
        enabled_before = set(widget.enabled)
        await pilot.press(*"open")
        await pilot.press("space")
        await pilot.press(*"behavior")
        await pilot.pause()
        # space went into the filter, did not toggle anything
        assert sl.filter_text == "open behavior"
        assert widget.enabled == enabled_before
        assert "open_mode" in widget._visible_ids
        assert app.focused is sl


@pytest.mark.asyncio
async def test_filter_is_token_substring_not_loose() -> None:
    # "macos" must only match the preset whose text contains that
    # substring, not unrelated presets via a scattered-letter match.
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        sl.focus()
        await pilot.pause()
        await pilot.press(*"macos")
        await pilot.pause()
        assert widget._visible_ids == ["tmux_focus"]


@pytest.mark.asyncio
async def test_filter_scope_is_title_and_tags_not_description() -> None:
    # "project" appears in file_view_excludes's description but not its
    # title/tags, so it must not match; presets that carry "project" in
    # the title/tags do.
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        sl.focus()
        await pilot.pause()
        await pilot.press(*"project")
        await pilot.pause()
        assert "file_view_excludes" not in widget._visible_ids
        assert "suffixes" in widget._visible_ids


@pytest.mark.asyncio
async def test_row_label_renders_tag_pills() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        await pilot.pause()
        preset = widget._preset_by_id["archive_timezone"]
        label = widget._row_label(preset, "keep")
        # every tag appears in the rendered row
        for tag in preset.tags:
            assert tag in label.plain
        # the tag strip is one continuous chip background (separator
        # included) so the row-highlight colour never shows between tags:
        # every char from the first chip to the last carries an `on #2c2c2c`
        # span, with no unstyled gap.
        chip_spans = [s for s in label.spans if "on #2c2c2c" in str(s.style)]
        start = min(s.start for s in chip_spans)
        end = max(s.end for s in chip_spans)
        covered = [False] * (end - start)
        for s in chip_spans:
            for i in range(s.start, s.end):
                covered[i - start] = True
        assert all(covered)


@pytest.mark.asyncio
async def test_presets_sorted_alphabetically() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        await pilot.pause()
        titles = [widget._preset_by_id[i].title for i in widget._visible_ids]
        assert titles == sorted(titles, key=str.lower)


@pytest.mark.asyncio
async def test_filter_preserves_sort_order() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        full_order = list(widget._visible_ids)
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        await pilot.press(*"e")
        await pilot.pause()
        # filtered subset keeps the sorted ordering, never reshuffles
        assert widget._visible_ids == [i for i in full_order if i in widget._visible_ids]


@pytest.mark.asyncio
async def test_help_text_points_to_kitchen_sink() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        await pilot.pause()
        help_text = app.query_one("#cfg_help", Static).render().plain
        assert "kitchen-sink-config.md" in help_text
        assert "curated" in help_text


@pytest.mark.asyncio
async def test_filter_shows_inline_text() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        await pilot.press(*"tmux")
        await pilot.pause()
        rendered = app.query_one("#cfg_filter", Static).render()
        assert "tmux" in rendered.plain


@pytest.mark.asyncio
async def test_disable_custom_value_field_removes() -> None:
    # the keep/skip no-op is gone: a configured field toggles keep <-> remove
    app = _Host({"archive": {"timezone": "Asia/Tokyo"}}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        assert "archive_timezone" in widget.enabled
        widget.enabled.discard("archive_timezone")
        await pilot.pause()
        assert "archive" not in widget._desired()


@pytest.mark.asyncio
async def test_partial_custom_preset_defaults_to_skip_not_remove() -> None:
    # a preset the user has only partially/custom-configured must not be
    # pre-checked, and its default plan is skip -- never a forced removal of
    # the hand-edited leaf.
    current = {"filters": {"saved": ["MINE"]}}
    app = _Host(current, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        assert "saved_filters_starter" not in widget.enabled
        assert widget._intents()["saved_filters_starter"] == "skip"
        # the custom leaf survives an apply that leaves it unchecked
        assert widget._desired()["filters"]["saved"] == ["MINE"]
        await pilot.pause()


@pytest.mark.asyncio
async def test_enabling_partial_preset_fills_gaps_without_clobber() -> None:
    current = {"filters": {"saved": ["MINE"]}}
    app = _Host(current, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget.enabled.add("saved_filters_starter")
        await pilot.pause()
        assert widget._intents()["saved_filters_starter"] == "add"
        desired = widget._desired()
        assert desired["filters"]["saved"] == ["MINE"]
        assert "named" in desired["filters"]


@pytest.mark.asyncio
async def test_bool_field_renders_checkbox() -> None:
    from textual.widgets import Checkbox

    from homebase.core.config_editor import _FieldCheckbox

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "table_behavior"
        widget._refresh_detail()
        await pilot.pause()
        cb = app.query_one("#cfg_in_pin_wip_top", Checkbox)
        assert isinstance(cb, _FieldCheckbox)
        # conventional checkbox glyphs, not the default toggle block
        assert (cb.BUTTON_LEFT, cb.BUTTON_INNER, cb.BUTTON_RIGHT) == ("[", "x", "]")


@pytest.mark.asyncio
async def test_bool_field_toggles_with_space_when_focused() -> None:
    # Tab moves focus from the list into the fields; space toggles the
    # focused checkbox (the list must not steal the keypress).
    from textual.widgets import Checkbox

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        sl.focus()
        sl.highlighted = widget._visible_ids.index("table_behavior")
        await pilot.pause()
        cb = app.query_one("#cfg_in_pin_wip_top", Checkbox)
        before = cb.value
        await pilot.press("tab")
        await pilot.pause()
        assert app.focused is cb
        await pilot.press("space")
        await pilot.pause()
        assert cb.value is not before
        # the list filter never saw the space
        assert sl.filter_text == ""


@pytest.mark.asyncio
async def test_field_detail_shows_interaction_hint() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "table_behavior"
        widget._refresh_detail()
        await pilot.pause()
        hint = app.query_one("#cfg_detail_hint", Static).render().plain
        assert "tab" in hint and "toggle" in hint


@pytest.mark.asyncio
async def test_tab_toggles_focus_to_field() -> None:
    app = _Host({"archive": {"timezone": "Europe/Oslo"}}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "archive_timezone"
        widget._refresh_detail()
        await pilot.pause()
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        widget.action_toggle_focus(1)
        await pilot.pause()
        assert app.query_one("#cfg_in_timezone", Input).has_focus


@pytest.mark.asyncio
async def test_tabbing_scrolls_focused_field_into_view() -> None:
    from textual.containers import VerticalScroll

    app = _Host({}, [])
    # short viewport so a multi-field preset overflows the detail pane
    async with app.run_test(size=(90, 16)) as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "reconcile_pacing"
        widget._refresh_detail()
        await pilot.pause()
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        detail = app.query_one("#cfg_detail", VerticalScroll)
        assert detail.max_scroll_y > 0  # content really overflows
        inputs = list(widget.query_one("#cfg_fields").query(Input))
        for _ in range(len(inputs)):
            widget.action_toggle_focus(1)
            await pilot.pause()
        last = inputs[-1]
        assert last.has_focus
        # the focused field is within the scrolled viewport, not below the fold
        assert detail.scroll_offset.y > 0
        assert last.region.y >= detail.content_region.y
        assert last.region.bottom <= detail.content_region.bottom


@pytest.mark.asyncio
async def test_toggle_updates_plan_and_diff() -> None:
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        sl = app.query_one("#cfg_list", SelectionList)
        idx = widget._visible_ids.index("suffixes")
        sl.select(sl.get_option_at_index(idx))
        await pilot.pause()
        assert "suffixes" in widget.enabled
        desired = widget._desired()
        assert desired["suffixes"] == ["tmp", "fork", "old"]


@pytest.mark.asyncio
async def test_editing_field_changes_desired_live() -> None:
    # typing into a field reflects in overrides/desired immediately, no blur
    app = _Host({"archive": {"timezone": "Europe/Oslo"}}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "archive_timezone"
        widget._refresh_detail()
        await pilot.pause()
        field_input = app.query_one("#cfg_in_timezone", Input)
        field_input.focus()
        await pilot.pause()
        field_input.value = ""
        await pilot.press(*"UTC")
        await pilot.pause()
        assert widget.overrides["archive_timezone"]["timezone"] == "UTC"
        assert widget._desired()["archive"]["timezone"] == "UTC"


@pytest.mark.asyncio
async def test_diff_defaults_to_selected_scope() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "archive_timezone"
        widget._refresh_diff()
        await pilot.pause()
        header = app.query_one("#cfg_diff_header", Static)
        # default is per-item: only the highlighted preset's contribution
        assert "only:" in header.render().plain
        desired, _, _ = widget._diff_view_data()
        assert set(desired) <= {"archive"}


@pytest.mark.asyncio
async def test_diff_toggle_switches_scope() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "archive_timezone"
        widget._refresh_diff()
        await pilot.pause()
        header = app.query_one("#cfg_diff_header", Static)
        assert "only:" in header.render().plain
        widget.action_toggle_diff()
        await pilot.pause()
        assert "whole config" in header.render().plain


@pytest.mark.asyncio
async def test_diff_updates_live_on_edit() -> None:
    from textual.widgets import Static

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget.enabled = {"archive_timezone"}
        widget._detail_id = "archive_timezone"
        widget._refresh_detail()
        widget._refresh_diff()
        await pilot.pause()
        field_input = app.query_one("#cfg_in_timezone", Input)
        field_input.focus()
        await pilot.pause()
        field_input.value = ""
        await pilot.press(*"UTC")
        await pilot.pause()
        # diff body reflects the typed value immediately, without blurring
        body = app.query_one("#cfg_diff", Static).render().plain
        assert "UTC" in body
        assert "Europe/Oslo" not in body


@pytest.mark.asyncio
async def test_apply_calls_on_apply_with_desired() -> None:
    captured: list = []
    app = _Host({}, captured)
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget.enabled = {"archive_timezone"}
        widget._commit()
        await pilot.pause()
        assert captured
        assert captured[-1]["archive"]["timezone"] == "Europe/Oslo"
        # post-commit: current updated, overrides cleared
        assert widget.current["archive"]["timezone"] == "Europe/Oslo"
        assert widget.overrides == {}


@pytest.mark.asyncio
async def test_ctrl_s_opens_confirm_dialog_with_field_focused() -> None:
    from homebase.core.config_editor import _ConfigConfirmDialog

    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget.enabled = {"archive_timezone"}
        # focus a descendant field, not the widget itself: the priority binding
        # must still fire while an inner Input/SelectionList holds focus.
        app.query_one("#cfg_list", SelectionList).focus()
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert isinstance(app.screen, _ConfigConfirmDialog)


@pytest.mark.asyncio
async def test_rapid_detail_switch_no_duplicate_ids() -> None:
    # Bouncing the highlight across presets that reuse field ids (raycast_sort
    # -> ... -> raycast_sort, "cfg_in_sort") within one tick must not remount
    # an id while its removal is still pending (DuplicateIds crash).
    app = _Host({}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        await pilot.pause()
        for pid in [
            "raycast_sort",
            "open_mode",
            "raycast_sort",
            "table_behavior",
            "raycast_sort",
        ]:
            widget._detail_id = pid
            widget._refresh_detail()
        await pilot.pause()
        # settled on raycast_sort with its Select mounted exactly once
        assert app.query_one("#cfg_in_sort", Select).value in ("name", Select.BLANK)


@pytest.mark.asyncio
async def test_choice_field_renders_select() -> None:
    app = _Host({"open_mode": {"profile": "tmux_tab"}}, [])
    async with app.run_test() as pilot:
        widget = app.query_one(ConfigEditorWidget)
        widget._detail_id = "open_mode"
        widget._refresh_detail()
        await pilot.pause()
        sel = app.query_one("#cfg_in_profile", Select)
        assert sel.value == "tmux_tab"


@pytest.mark.asyncio
async def test_screen_wrapper_mounts_widget() -> None:
    class _ScreenHost(App[None]):
        async def on_mount(self) -> None:
            await self.push_screen(
                ConfigEditorScreen(
                    build_presets(ConfigEnv()), {}, lambda d: None, env=ConfigEnv()
                )
            )

    app = _ScreenHost()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ConfigEditorScreen)
        assert app.screen.query_one(ConfigEditorWidget) is not None


class _ScreenHost(App[None]):
    async def on_mount(self) -> None:
        await self.push_screen(
            ConfigEditorScreen(
                build_presets(ConfigEnv()), {}, lambda d: None, env=ConfigEnv()
            )
        )


def _clear_pending(widget: ConfigEditorWidget) -> None:
    widget.enabled = set()
    widget._initial_enabled = set()
    widget.overrides.clear()


@pytest.mark.asyncio
async def test_close_without_changes_dismisses_immediately() -> None:
    app = _ScreenHost()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ConfigEditorScreen)
        widget = screen.query_one(ConfigEditorWidget)
        _clear_pending(widget)
        assert widget.has_pending_changes() is False
        screen.action_close()
        await pilot.pause()
        assert not isinstance(app.screen, ConfigEditorScreen)


@pytest.mark.asyncio
async def test_close_with_changes_prompts_then_discards() -> None:
    from homebase.core.config_editor import _ConfirmDiscardDialog

    app = _ScreenHost()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        widget = screen.query_one(ConfigEditorWidget)
        _clear_pending(widget)
        widget.enabled = {"archive_timezone"}  # pending ADD
        assert widget.has_pending_changes() is True

        screen.action_close()
        await pilot.pause()
        # editor stays open behind the discard confirmation
        assert isinstance(app.screen, _ConfirmDiscardDialog)

        app.screen.dismiss(True)  # confirm discard
        await pilot.pause()
        assert not isinstance(app.screen, ConfigEditorScreen)


@pytest.mark.asyncio
async def test_discard_cancel_keeps_editor_open() -> None:
    from homebase.core.config_editor import _ConfirmDiscardDialog

    app = _ScreenHost()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        widget = screen.query_one(ConfigEditorWidget)
        _clear_pending(widget)
        widget.enabled = {"archive_timezone"}

        screen.action_close()
        await pilot.pause()
        assert isinstance(app.screen, _ConfirmDiscardDialog)

        app.screen.dismiss(False)  # keep editing
        await pilot.pause()
        assert isinstance(app.screen, ConfigEditorScreen)

        # tidy up so teardown has no modal in flight
        _clear_pending(widget)
        screen.action_close()
        await pilot.pause()
