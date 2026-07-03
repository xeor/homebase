from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    Select,
    SelectionList,
    Static,
)
from textual.widgets.selection_list import Selection

from .config_presets import (
    INTENT_ADD,
    INTENT_KEEP,
    INTENT_REMOVE,
    INTENT_SKIP,
    INTENT_UPDATE,
    ConfigField,
    ConfigPreset,
    apply_presets,
    field_current_value,
    plan_intents,
    preset_is_selected_default,
)
from .constants import COLOR_PENDING_HEX
from .diff import color_diff_lines, diff_counts

# Muted chip style for the per-row tag strip: anonymous grey text on a
# subtle dark background so tags read as chips without competing with the
# intent word or title. The strip is rendered as one continuous styled run
# (separator included) so the row-highlight colour never leaks between tags.
_TAG_PILL_STYLE = f"{COLOR_PENDING_HEX} on #2c2c2c"
_TAG_SEP_STYLE = "#5a5a5a on #2c2c2c"

# Shown beside the Apply button: this editor only surfaces a curated
# handful of settings; the kitchen-sink doc documents the full config.
_HELP_MARKUP = (
    "[dim]This view exposes a small curated set of settings.\n"
    "For the full config surface, see [/][b]docs/kitchen-sink-config.md[/]"
)

_INTENT_STYLE: dict[str, tuple[str, str]] = {
    INTENT_ADD: ("add", "bright_green"),
    INTENT_UPDATE: ("update", "bright_yellow"),
    INTENT_REMOVE: ("remove", "bright_red"),
    INTENT_KEEP: ("keep", "bright_cyan"),
    INTENT_SKIP: ("skip", "grey50"),
}


def _yaml_lines(data: dict[str, Any]) -> list[str]:
    if not data:
        return ["{}"]
    return yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True
    ).splitlines()


class PresetList(SelectionList):
    """SelectionList with an embedded type-to-filter, mirroring the
    pickers in ``b``: typing while the list is focused filters it
    in place (no separate text box).

    Enter toggles the highlighted row (OptionList default); space is freed
    up and treated as a filter character. The filter is delivered through a
    synchronous sink callback rather than a message so each keystroke
    repaints without an event-loop round-trip."""

    BINDINGS = [Binding("space", "filter_space", "Filter space", show=False)]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.filter_text = ""
        self._filter_sink: Callable[[str], None] | None = None

    def set_filter_sink(self, sink: Callable[[str], None]) -> None:
        self._filter_sink = sink

    def _emit_filter(self) -> None:
        if self._filter_sink is not None:
            self._filter_sink(self.filter_text)

    def action_filter_space(self) -> None:
        self.filter_text += " "
        self._emit_filter()

    def on_key(self, event: events.Key) -> None:
        if event.key == "backspace":
            if self.filter_text:
                self.filter_text = self.filter_text[:-1]
                self._emit_filter()
            event.stop()
            event.prevent_default()
            return
        char = event.character
        if char is not None and char.isprintable() and char != " ":
            self.filter_text += char
            self._emit_filter()
            event.stop()
            event.prevent_default()


class _FieldCheckbox(Checkbox):
    """Checkbox drawn with conventional ``[x]`` / ``[ ]`` glyphs so a
    boolean field reads clearly as a checkbox rather than the default
    toggle-button block, which is easily mistaken for a select box."""

    BUTTON_LEFT = "["
    BUTTON_INNER = "x"
    BUTTON_RIGHT = "]"


class ConfigEditorWidget(Vertical):
    """Searchable preset checklist + inline field editor + apply plan.

    Self-contained and embeddable: the caller injects the current config
    dict and an ``on_apply(desired)`` callback, so this widget performs
    no config I/O of its own. Hosted as a ``b setup`` tab now and as a
    ``ConfigEditorScreen`` modal inside ``b`` later."""

    BINDINGS = [
        Binding("tab", "toggle_focus(1)", "Next field", show=False),
        Binding("shift+tab", "toggle_focus(-1)", "Prev field", show=False),
        Binding("ctrl+t", "toggle_diff", "Diff scope", show=False),
        Binding("ctrl+s", "apply", "Apply", show=False, priority=True),
    ]

    DIFF_ALL = "all"
    DIFF_SELECTED = "selected"

    DEFAULT_CSS = """
    ConfigEditorWidget { height: 1fr; }
    ConfigEditorWidget #cfg_grid {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 2fr 3fr;
        grid-rows: 1fr 2fr;
        grid-gutter: 1 1;
        padding: 1 1 0 1;
    }
    ConfigEditorWidget #cfg_list_cell { height: 1fr; }
    ConfigEditorWidget #cfg_filter { height: 1; padding: 0 1; color: $text-muted; }
    ConfigEditorWidget #cfg_list {
        height: 1fr;
        border: round $panel;
        padding: 0 1;
    }
    ConfigEditorWidget #cfg_list:focus { border: round $accent; }
    ConfigEditorWidget #cfg_right {
        row-span: 2;
        height: 1fr;
    }
    ConfigEditorWidget #cfg_diff_box {
        height: 1fr;
        border: round $accent;
        padding: 0 1;
    }
    ConfigEditorWidget #cfg_detail {
        border: round $panel;
        padding: 0 1;
    }
    ConfigEditorWidget #cfg_detail_title { text-style: bold; padding: 0 0 1 0; }
    ConfigEditorWidget #cfg_detail_desc { padding: 0 0 1 0; color: $text-muted; }
    ConfigEditorWidget #cfg_detail_hint { height: auto; padding: 1 0 0 0; color: $text-muted; }
    /* auto height so the fields grow the scroll's virtual size; a default
       1fr Vertical would clip and leave lower fields unreachable by scroll. */
    ConfigEditorWidget #cfg_fields { height: auto; }
    ConfigEditorWidget .cfg_field_label { padding: 1 0 0 0; text-style: bold; }
    ConfigEditorWidget #cfg_fields Checkbox {
        border: none;
        height: auto;
        padding: 0 1;
        background: $boost;
    }
    ConfigEditorWidget #cfg_fields Checkbox:focus {
        background: $accent 25%;
        text-style: bold;
    }
    ConfigEditorWidget #cfg_fields Input:focus { border: tall $accent; }
    ConfigEditorWidget #cfg_fields Select:focus > SelectCurrent { border: tall $accent; }
    ConfigEditorWidget #cfg_plan_title { text-style: bold; padding: 0 0 1 0; }
    ConfigEditorWidget #cfg_plan_summary { padding: 0 0 1 0; height: auto; }
    ConfigEditorWidget #cfg_diff_header { height: auto; padding: 0 0 1 0; }
    ConfigEditorWidget #cfg_controls {
        layout: horizontal;
        height: auto;
        align: left middle;
        padding: 1 1 0 1;
    }
    ConfigEditorWidget #cfg_apply { width: auto; min-width: 18; margin: 0 2 0 0; }
    ConfigEditorWidget #cfg_help { width: 1fr; height: auto; color: $text-muted; }
    ConfigEditorWidget #cfg_status { height: 1; color: $text-muted; padding: 0 1; }
    """

    def __init__(
        self,
        presets: list[ConfigPreset],
        current_config: dict[str, Any],
        on_apply: Callable[[dict[str, Any]], None],
        *,
        env: Any = None,
    ) -> None:
        super().__init__()
        self._presets = sorted(presets, key=lambda p: p.title.lower())
        self._preset_by_id = {p.id: p for p in presets}
        self.current = dict(current_config)
        self._on_apply = on_apply
        self._env = env
        self.enabled: set[str] = {
            p.id
            for p in presets
            if env is not None and preset_is_selected_default(p, self.current, env)
        }
        # Only presets that were active at load (or after the last apply) may be
        # removed on disable. A preset that starts unchecked defaults to skip,
        # never to a destructive removal of the user's hand-edited config.
        self._initial_enabled: set[str] = set(self.enabled)
        self.overrides: dict[str, dict[str, Any]] = {}
        self._search = ""
        self._visible_ids: list[str] = []
        self._detail_id: str | None = None
        self._rendered_detail_id: str | None = None
        self._detail_render_token = 0
        self._rebuilding = False
        self._diff_view = self.DIFF_SELECTED

    # --- compose ----------------------------------------------------

    def compose(self) -> ComposeResult:
        with Container(id="cfg_grid"):
            with Vertical(id="cfg_list_cell"):
                yield Static("", id="cfg_filter")
                preset_list = PresetList(id="cfg_list")
                preset_list.set_filter_sink(self._on_filter_changed)
                yield preset_list
            with Vertical(id="cfg_right"):
                with VerticalScroll(id="cfg_diff_box"):
                    yield Static("Apply plan", id="cfg_plan_title")
                    yield Static("", id="cfg_plan_summary")
                    yield Static("", id="cfg_diff_header")
                    yield Static("", id="cfg_diff")
                with Horizontal(id="cfg_controls"):
                    yield Button("Apply (Ctrl+S)", id="cfg_apply", variant="success")
                    yield Static(Text.from_markup(_HELP_MARKUP), id="cfg_help")
                yield Static("", id="cfg_status")
            with VerticalScroll(id="cfg_detail"):
                yield Static("", id="cfg_detail_title")
                yield Static("", id="cfg_detail_desc")
                yield Vertical(id="cfg_fields")
                yield Static("", id="cfg_detail_hint")

    def on_mount(self) -> None:
        self._rebuild_list()
        self._refresh_outputs()
        self.query_one("#cfg_list", PresetList).focus()

    # --- list / search ----------------------------------------------

    def _search_text(self, preset: ConfigPreset) -> str:
        # Title + tags only. Descriptions are prose and match too loosely
        # (e.g. "project" appearing in an unrelated preset's blurb), so
        # they are deliberately excluded from the filter scope.
        return " ".join((preset.title, *preset.tags)).lower()

    def _filtered_presets(self) -> list[ConfigPreset]:
        # ``self._presets`` is sorted alphabetically by title in __init__, so
        # the list reads A->Z and the filter only hides non-matching rows
        # (it never reshuffles while typing). Every
        # whitespace-separated token must appear as a substring of the
        # preset's search text — predictable and instant for a small
        # curated catalog (a loose subsequence scorer matched scattered
        # letters across unrelated presets, e.g. "macos").
        tokens = self._search.lower().split()
        if not tokens:
            return list(self._presets)
        return [
            p
            for p in self._presets
            if all(tok in self._search_text(p) for tok in tokens)
        ]

    def _row_label(self, preset: ConfigPreset, intent: str) -> Text:
        word, color = _INTENT_STYLE[intent]
        label = Text.from_markup(f"[{color}]{word:<6}[/] {preset.title}")
        if preset.tags:
            label.append("  ")
            label.append(" ", style=_TAG_PILL_STYLE)
            for i, tag in enumerate(preset.tags):
                if i:
                    label.append(" · ", style=_TAG_SEP_STYLE)
                label.append(tag, style=_TAG_PILL_STYLE)
            label.append(" ", style=_TAG_PILL_STYLE)
        return label

    def _rebuild_list(self) -> None:
        sl = self.query_one("#cfg_list", PresetList)
        prev_detail = self._detail_id
        intents = self._intents()
        presets = self._filtered_presets()
        self._visible_ids = [p.id for p in presets]
        self._rebuilding = True
        try:
            sl.clear_options()
            if presets:
                sl.add_options(
                    [
                        Selection(
                            self._row_label(p, intents[p.id]),
                            p.id,
                            p.id in self.enabled,
                            id=f"sel_{p.id}",
                        )
                        for p in presets
                    ]
                )
        finally:
            self._rebuilding = False
        filt = sl.filter_text
        sl.border_title = f"presets ({len(presets)}/{len(self._presets)})"
        cfg_filter = self.query_one("#cfg_filter", Static)
        if filt:
            cfg_filter.update(
                Text.from_markup(f"[dim]filter:[/] {filt}[reverse] [/]")
            )
        else:
            cfg_filter.update(Text.from_markup("[dim]type to filter[/]"))
        if not presets:
            self._detail_id = None
        elif self._detail_id not in self._visible_ids:
            self._detail_id = self._visible_ids[0]
        if self._detail_id is not None:
            # Keep a row highlighted so Enter has a target immediately (the
            # list never auto-highlights on focus) and so filtering parks the
            # cursor on the top match.
            sl.highlighted = self._visible_ids.index(self._detail_id)
        self._refresh_detail()
        if self._detail_id != prev_detail and self._diff_view == self.DIFF_SELECTED:
            self._refresh_diff()

    def _refresh_row_labels(self) -> None:
        sl = self.query_one("#cfg_list", PresetList)
        intents = self._intents()
        for idx, pid in enumerate(self._visible_ids):
            preset = self._preset_by_id[pid]
            sl.replace_option_prompt_at_index(
                idx, self._row_label(preset, intents[pid])
            )

    def _on_filter_changed(self, value: str) -> None:
        # Synchronous hot path: only rebuild the (small) option list. The
        # whole-config diff is unaffected by filtering, and the selected
        # scope is refreshed by the highlight handler when the cursor lands
        # on a different preset, so no yaml/diff work happens per keystroke.
        self._search = value
        self._rebuild_list()

    def on_selection_list_selected_changed(
        self, event: SelectionList.SelectedChanged
    ) -> None:
        event.stop()
        if self._rebuilding:
            return
        self._sync_enabled_from_visible()
        self._refresh_row_labels()
        self._refresh_outputs()

    def on_selection_list_selection_highlighted(
        self, event: SelectionList.SelectionHighlighted
    ) -> None:
        event.stop()
        value = getattr(event.selection, "value", None)
        if isinstance(value, str) and value != self._detail_id:
            self._detail_id = value
            self._refresh_detail()
            if self._diff_view == self.DIFF_SELECTED:
                self._refresh_diff()

    def _sync_enabled_from_visible(self) -> None:
        sl = self.query_one("#cfg_list", PresetList)
        selected_now = {str(v) for v in sl.selected}
        for pid in self._visible_ids:
            if pid in selected_now:
                self.enabled.add(pid)
            else:
                self.enabled.discard(pid)

    # --- focus ring (Tab toggles list <-> fields) -------------------

    def _focus_ring(self) -> list[Any]:
        ring: list[Any] = [self.query_one("#cfg_list", PresetList)]
        ring.extend(self.query_one("#cfg_fields", Vertical).query("Input, Select, Checkbox"))
        return ring

    def action_toggle_focus(self, step: int) -> None:
        ring = self._focus_ring()
        if len(ring) < 2:
            return
        idx = next((i for i, w in enumerate(ring) if w.has_focus), -1)
        target = ring[(idx + step) % len(ring)] if idx >= 0 else ring[0]
        target.focus()
        # Bring the newly focused field into view: tall presets overflow the
        # detail pane, and a field mounted below the fold would otherwise take
        # focus while staying invisible. Include the field's heading label so
        # the focused row reads with its caption.
        self._scroll_field_into_view(target)

    def _scroll_field_into_view(self, target: Any) -> None:
        detail = self.query_one("#cfg_detail", VerticalScroll)
        if target not in detail.walk_children():
            return
        label = self._field_heading_for(target)
        detail.scroll_to_widget(label or target, animate=False, top=bool(label))

    def _field_heading_for(self, target: Any) -> Any | None:
        # The heading Label sits immediately before its input widget in the
        # fields box; scroll to it so the caption is visible above the field.
        fields_box = self.query_one("#cfg_fields", Vertical)
        children = list(fields_box.children)
        try:
            pos = children.index(target)
        except ValueError:
            return None
        prev = children[pos - 1] if pos > 0 else None
        if prev is not None and "cfg_field_label" in prev.classes:
            return prev
        return None

    # --- detail / inline fields -------------------------------------

    def _field_display_value(self, preset: ConfigPreset, field_def: ConfigField) -> Any:
        ov = self.overrides.get(preset.id, {})
        if field_def.key in ov:
            return ov[field_def.key]
        cur = field_current_value(field_def, self.current)
        return cur if cur is not None else field_def.default

    def _field_widget(self, preset: ConfigPreset, field_def: ConfigField):
        wid = f"cfg_in_{field_def.key}"
        value = self._field_display_value(preset, field_def)
        if field_def.kind == "bool":
            return _FieldCheckbox(field_def.label, value=bool(value), id=wid)
        if field_def.kind == "choice":
            options = [(c, c) for c in field_def.choices]
            sel = value if value in field_def.choices else Select.BLANK
            return Select(options, value=sel, allow_blank=True, id=wid)
        if field_def.kind == "list_csv":
            text = ",".join(str(x) for x in value) if isinstance(value, list) else str(value)
            return Input(value=text, id=wid)
        return Input(value="" if value is None else str(value), id=wid)

    def _refresh_detail(self) -> None:
        # Rebuild only when the highlighted preset changes.
        if self._detail_id == self._rendered_detail_id:
            return
        self._rendered_detail_id = self._detail_id
        title = self.query_one("#cfg_detail_title", Static)
        desc = self.query_one("#cfg_detail_desc", Static)
        fields_box = self.query_one("#cfg_fields", Vertical)
        hint = self.query_one("#cfg_detail_hint", Static)
        # Drop the previous preset's field widgets. Removal is deferred, so
        # the replacements (which reuse the same ``cfg_in_<key>`` ids) must
        # not be mounted in this tick — a rapid highlight bounce would remount
        # an id while its removal is still pending and raise DuplicateIds. The
        # mount is deferred and token-gated so only the most recent switch
        # mounts, and only once the field box has actually emptied.
        fields_box.remove_children()
        self._detail_render_token += 1
        token = self._detail_render_token
        if self._detail_id is None:
            title.update("")
            desc.update("")
            hint.update("")
            return
        preset = self._preset_by_id[self._detail_id]
        title.update(preset.title)
        desc.update(preset.description)
        widgets: list[Any] = []
        for field_def in preset.fields:
            # A Checkbox already renders its own caption; a separate Label
            # would duplicate it. Other field kinds get a heading Label.
            if field_def.kind != "bool":
                widgets.append(Label(field_def.label, classes="cfg_field_label"))
            widgets.append(self._field_widget(preset, field_def))
            if field_def.help:
                widgets.append(Static(f"[dim]{field_def.help}[/]"))
        if widgets:
            hint.update(
                Text.from_markup(
                    "[dim]tab: list ↔ fields · "
                    "space/enter: toggle · type: edit[/]"
                )
            )
            self.call_after_refresh(self._mount_fields, token, widgets)
        else:
            hint.update("")

    def _mount_fields(self, token: int, widgets: list[Any]) -> None:
        if token != self._detail_render_token:
            return  # superseded by a newer switch
        fields_box = self.query_one("#cfg_fields", Vertical)
        if fields_box.children:
            # The previous preset's widgets are still being removed; retry on
            # the next refresh so the reused ids are free before we mount.
            self.call_after_refresh(self._mount_fields, token, widgets)
            return
        fields_box.mount(*widgets)

    def _coerce_field(self, field_def: ConfigField, raw: Any) -> Any | None:
        if field_def.kind == "int":
            try:
                return int(str(raw).strip())
            except ValueError:
                return None
        if field_def.kind == "list_csv":
            return [p.strip() for p in str(raw).split(",") if p.strip()]
        if field_def.kind == "bool":
            return bool(raw)
        return str(raw)

    def _store_override(self, key: str, raw: Any) -> None:
        if self._detail_id is None:
            return
        preset = self._preset_by_id[self._detail_id]
        field_def = next((f for f in preset.fields if f.key == key), None)
        if field_def is None:
            return
        value = self._coerce_field(field_def, raw)
        if value is None:
            return
        self.overrides.setdefault(preset.id, {})[key] = value
        self._refresh_row_labels()
        self._refresh_outputs()

    def on_input_changed(self, event: Input.Changed) -> None:
        # Live: reflect every keystroke in the plan and diff, no blur needed.
        if event.input.id and event.input.id.startswith("cfg_in_"):
            event.stop()
            self._store_override(event.input.id[len("cfg_in_") :], event.value)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id and event.select.id.startswith("cfg_in_"):
            event.stop()
            if event.value is not Select.BLANK:
                self._store_override(event.select.id[len("cfg_in_") :], event.value)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id and event.checkbox.id.startswith("cfg_in_"):
            event.stop()
            self._store_override(event.checkbox.id[len("cfg_in_") :], event.value)

    # --- plan / diff ------------------------------------------------

    def _intents(self) -> dict[str, str]:
        return plan_intents(
            self.current,
            self.enabled,
            self.overrides,
            self._presets,
            removable_ids=self._initial_enabled,
        )

    def _desired(self) -> dict[str, Any]:
        return apply_presets(
            self.current,
            self.enabled,
            self.overrides,
            self._presets,
            removable_ids=self._initial_enabled,
        )

    def _refresh_outputs(self) -> None:
        self._refresh_plan()
        self._refresh_diff()

    def _refresh_plan(self) -> None:
        intents = self._intents()
        counts: dict[str, int] = {}
        for value in intents.values():
            counts[value] = counts.get(value, 0) + 1
        parts = []
        for intent in (INTENT_ADD, INTENT_UPDATE, INTENT_REMOVE, INTENT_KEEP, INTENT_SKIP):
            word, color = _INTENT_STYLE[intent]
            parts.append(f"[{color}]{word} {counts.get(intent, 0)}[/]")
        summary = self.query_one("#cfg_plan_summary", Static)
        summary.update(Text.from_markup("  ".join(parts)))

    def _diff_view_data(self) -> tuple[dict[str, Any], str, str]:
        """Return ``(desired, label, other_label)`` for the active scope.

        ``all`` diffs the whole pending config; ``selected`` diffs only the
        highlighted preset's contribution so its effect can be read in
        isolation."""
        if self._diff_view == self.DIFF_SELECTED and self._detail_id is not None:
            preset = self._preset_by_id[self._detail_id]
            enabled = {preset.id} if preset.id in self.enabled else set()
            desired = apply_presets(
                self.current,
                enabled,
                self.overrides,
                [preset],
                removable_ids=self._initial_enabled,
            )
            return desired, f"only: {preset.title}", "whole config"
        return self._desired(), "whole config", "selected preset only"

    def _refresh_diff(self) -> None:
        desired, label, other = self._diff_view_data()
        cur_lines = _yaml_lines(self.current)
        des_lines = _yaml_lines(desired)
        removed, added = diff_counts(cur_lines, des_lines)
        self.query_one("#cfg_diff_header", Static).update(
            Text.from_markup(
                f"[b]{label}[/] "
                f"[bright_red]-{removed}[/] [bright_green]+{added}[/]"
                f"   [dim]ctrl+t -> {other}[/]"
            )
        )
        lines = color_diff_lines(cur_lines, des_lines)
        self.query_one("#cfg_diff", Static).update(Text.from_markup("\n".join(lines)))

    def action_toggle_diff(self) -> None:
        self._diff_view = (
            self.DIFF_SELECTED if self._diff_view == self.DIFF_ALL else self.DIFF_ALL
        )
        self._refresh_diff()

    # --- apply ------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg_apply":
            event.stop()
            self.action_apply()

    def _pending_changes(self) -> tuple[list[str], list[str]]:
        """Return ``(changes, removes)`` preset titles for the pending plan."""
        intents = self._intents()
        changes = [
            self._preset_by_id[pid].title
            for pid, intent in intents.items()
            if intent in (INTENT_ADD, INTENT_UPDATE)
        ]
        removes = [
            self._preset_by_id[pid].title
            for pid, intent in intents.items()
            if intent == INTENT_REMOVE
        ]
        return changes, removes

    def has_pending_changes(self) -> bool:
        changes, removes = self._pending_changes()
        return bool(changes or removes)

    def action_apply(self) -> None:
        changes, removes = self._pending_changes()
        if not changes and not removes:
            self._set_status("Nothing to apply.")
            return

        def _done(confirmed: bool | None) -> None:
            if confirmed:
                self._commit()

        self.app.push_screen(_ConfigConfirmDialog(changes, removes), _done)

    def _commit(self) -> None:
        desired = self._desired()
        self._on_apply(desired)
        self.current = desired
        self.overrides.clear()
        # Whatever is enabled after apply becomes the new removable baseline,
        # so a later uncheck of a just-applied preset can remove it again.
        self._initial_enabled = set(self.enabled)
        self._refresh_row_labels()
        self._refresh_outputs()
        self._set_status("Applied.")

    def _set_status(self, text: str) -> None:
        self.query_one("#cfg_status", Static).update(text)


class _ConfigConfirmDialog(ModalScreen[bool]):
    DEFAULT_CSS = """
    _ConfigConfirmDialog { align: center middle; }
    _ConfigConfirmDialog #cfg_dialog_box {
        width: 70%;
        height: 60%;
        background: $boost;
        padding: 1 2;
        border: round $accent;
    }
    _ConfigConfirmDialog #cfg_dialog_box.-destructive { border: round $error; }
    _ConfigConfirmDialog #cfg_dialog_body {
        height: 1fr;
        border: round $panel;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    _ConfigConfirmDialog #cfg_dialog_buttons { height: 3; align-horizontal: right; }
    _ConfigConfirmDialog #cfg_dialog_buttons Button { margin: 0 0 0 1; min-width: 18; }
    """

    def __init__(self, changes: list[str], removes: list[str]) -> None:
        super().__init__()
        self._changes = changes
        self._removes = removes

    def compose(self) -> ComposeResult:
        destructive = bool(self._removes)
        box_class = "-destructive" if destructive else ""
        with Vertical(id="cfg_dialog_box", classes=box_class):
            color = "bright_red" if destructive else "bright_cyan"
            yield Static(Text.from_markup(f"[bold {color}]Confirm config changes[/]"))
            lines: list[str] = []
            if self._removes:
                lines.append(f"[bold bright_red]REMOVE {len(self._removes)} preset(s):[/]")
                lines.extend(f"  [bright_red]- {t}[/]" for t in self._removes)
                if self._changes:
                    lines.append("")
            if self._changes:
                lines.append(
                    f"[bold bright_green]WRITE {len(self._changes)} preset(s):[/]"
                )
                lines.extend(f"  [bright_green]+ {t}[/]" for t in self._changes)
            lines.append("")
            lines.append("[bold]Enter to apply, Esc to cancel.[/]")
            yield Static(Text.from_markup("\n".join(lines)), id="cfg_dialog_body")
            with Horizontal(id="cfg_dialog_buttons"):
                yield Button("Cancel (Esc)", id="cfg_dialog_cancel")
                yield Button(
                    "Apply",
                    id="cfg_dialog_ok",
                    variant="error" if destructive else "success",
                )

    def on_mount(self) -> None:
        self.query_one("#cfg_dialog_ok", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg_dialog_ok":
            self.dismiss(True)
        elif event.button.id == "cfg_dialog_cancel":
            self.dismiss(False)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(False)


class _ConfirmDiscardDialog(ModalScreen[bool]):
    """Guard closing the editor while an unsaved apply-plan is pending."""

    DEFAULT_CSS = """
    _ConfirmDiscardDialog { align: center middle; }
    _ConfirmDiscardDialog #cfg_discard_box {
        width: 60%;
        height: auto;
        background: $boost;
        padding: 1 2;
        border: round $error;
    }
    _ConfirmDiscardDialog #cfg_discard_buttons { height: 3; align-horizontal: right; }
    _ConfirmDiscardDialog #cfg_discard_buttons Button { margin: 0 0 0 1; min-width: 18; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="cfg_discard_box"):
            yield Static(
                Text.from_markup(
                    "[bold bright_red]Unsaved changes[/]\n\n"
                    "You have edits that have not been applied.\n"
                    "Close the editor and discard them?\n\n"
                    "[bold]Enter to discard, Esc to keep editing.[/]"
                )
            )
            with Horizontal(id="cfg_discard_buttons"):
                yield Button("Keep editing (Esc)", id="cfg_discard_cancel")
                yield Button("Discard", id="cfg_discard_ok", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cfg_discard_ok", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg_discard_ok":
            self.dismiss(True)
        elif event.button.id == "cfg_discard_cancel":
            self.dismiss(False)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss(False)


class ConfigEditorScreen(ModalScreen[None]):
    """Big-modal host for the editor (the future in-``b`` entry point)."""

    DEFAULT_CSS = """
    ConfigEditorScreen { align: center middle; }
    ConfigEditorScreen #cfg_screen_box {
        width: 90%;
        height: 90%;
        background: $surface;
        border: round $accent;
        padding: 0 1;
    }
    """

    BINDINGS = [("escape", "close", "Close")]

    def __init__(
        self,
        presets: list[ConfigPreset],
        current_config: dict[str, Any],
        on_apply: Callable[[dict[str, Any]], None],
        *,
        env: Any = None,
    ) -> None:
        super().__init__()
        self._presets = presets
        self._current = current_config
        self._on_apply = on_apply
        self._env = env

    def compose(self) -> ComposeResult:
        with Vertical(id="cfg_screen_box"):
            yield ConfigEditorWidget(
                self._presets, self._current, self._on_apply, env=self._env
            )

    def action_close(self) -> None:
        widget = self.query_one(ConfigEditorWidget)
        if not widget.has_pending_changes():
            self.dismiss(None)
            return

        def _done(discard: bool | None) -> None:
            if discard:
                self.dismiss(None)

        self.app.push_screen(_ConfirmDiscardDialog(), _done)


__all__ = ["ConfigEditorScreen", "ConfigEditorWidget"]
