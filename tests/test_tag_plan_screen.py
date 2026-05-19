from __future__ import annotations

from pathlib import Path

import yaml

from homebase.config import tag_rules
from homebase.config.store import clear_global_config_cache
from homebase.core.constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME
from homebase.ui.screens.tag_plan import TagPlanScreen


def _setup_base(tmp_path: Path, rules: list[dict] | None = None) -> Path:
    base = tmp_path / "base"
    (base / HOMEBASE_DIR_NAME).mkdir(parents=True)
    cfg = base / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    if rules is None:
        cfg.write_text("")
    else:
        cfg.write_text(yaml.safe_dump({"tag_rules": rules}))
    clear_global_config_cache()
    tag_rules.clear_tag_rules_cache()
    return base


def _make_screen(
    tmp_path: Path,
    tags: list[str],
    rules: list[dict] | None = None,
    *,
    presence: dict[str, str] | None = None,
    other_counts: dict[str, int] | None = None,
    monkeypatch=None,
) -> TagPlanScreen:
    base = _setup_base(tmp_path, rules)
    screen = TagPlanScreen(
        tags=tags,
        presence=presence or {t: "none" for t in tags},
        other_counts=other_counts or {t: 0 for t in tags},
        base_dir=base,
    )
    # _refresh_body queries Textual widgets that don't exist outside a
    # mounted app — stub it for unit-level testing.
    if monkeypatch is not None:
        monkeypatch.setattr(screen, "_refresh_body", lambda: None)
    return screen


def test_screen_without_base_dir_falls_back_to_flat_list(tmp_path: Path) -> None:
    """Defensive fallback: no base_dir → no tree → flat list. The
    screen must still work (just without hierarchy)."""
    screen = TagPlanScreen(
        tags=["work", "home"],
        presence={"work": "none", "home": "none"},
        other_counts={"work": 0, "home": 0},
        base_dir=None,
    )
    rows = screen._visible_rows()
    assert [r.name for r in rows] == ["work", "home"]
    assert all(r.depth == 0 for r in rows)
    assert all(r.group_only is False for r in rows)


def test_screen_with_base_dir_renders_hierarchy(tmp_path: Path) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True},
        ],
    )
    rows = screen._visible_rows()
    names = [r.name for r in rows]
    assert names == ["priority", "prio:p0"]
    assert rows[0].group_only is True
    assert rows[0].depth == 0
    assert rows[1].group_only is False
    assert rows[1].depth == 1


def test_cursor_snaps_to_first_selectable_row(tmp_path: Path) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True},
        ],
    )
    # rows[0] = priority (group-only). The cursor must not land on it.
    assert screen._current_row().name == "prio:p0"


def test_move_down_skips_group_only(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0", "prio:p1"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True},
        ],
        monkeypatch=monkeypatch,
    )
    # Cursor starts on prio:p0; moving down skips priority and lands
    # on prio:p1.
    screen.action_move_down()
    assert screen._current_row().name == "prio:p1"
    # Wrapping continues skipping group-only entries.
    screen.action_move_down()
    assert screen._current_row().name == "prio:p0"


def test_cycle_plan_ignores_group_only(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True},
        ],
        monkeypatch=monkeypatch,
    )
    # Force the cursor onto the group-only row.
    rows = screen._visible_rows()
    screen.index = next(i for i, r in enumerate(rows) if r.group_only)
    screen.action_cycle_plan()
    # The group-only tag's plan must remain "keep" — either via
    # explicit value or by being absent (defaults to keep semantically).
    assert screen.plan.get("priority", "keep") == "keep"


def test_cycle_plan_cycles_for_selectable(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["work"],
        rules=[{"tags": ["work"], "color": "#88ccff"}],
        monkeypatch=monkeypatch,
    )
    assert screen.plan["work"] == "keep"
    screen.action_cycle_plan()
    assert screen.plan["work"] == "add"
    screen.action_cycle_plan()
    assert screen.plan["work"] == "keep"


def test_filter_preserves_tree_structure(tmp_path: Path) -> None:
    """Searching for a leaf must keep the parent visible so the
    hierarchy stays readable."""
    screen = _make_screen(
        tmp_path,
        tags=["python", "rust", "home"],
        rules=[
            {"tags": ["python", "rust"], "parents": ["programming"]},
            {"tags": ["programming"], "group_only": True},
        ],
    )
    screen.filter_text = "python"
    screen._invalidate_rows_cache()
    rows = screen._visible_rows()
    names = [r.name for r in rows]
    assert names == ["programming", "python"]
    # home is unrelated, must not appear.
    assert "home" not in names


def test_filter_on_parent_shows_descendants(tmp_path: Path) -> None:
    """Searching for a group surfaces every descendant for
    drill-down."""
    screen = _make_screen(
        tmp_path,
        tags=["python", "rust", "home"],
        rules=[
            {"tags": ["python", "rust"], "parents": ["programming"]},
            {"tags": ["programming"], "group_only": True},
        ],
    )
    screen.filter_text = "programming"
    screen._invalidate_rows_cache()
    rows = screen._visible_rows()
    names = [r.name for r in rows]
    assert "programming" in names
    assert "python" in names
    assert "rust" in names
    assert "home" not in names


def test_accept_drops_group_only_from_plan(tmp_path: Path) -> None:
    """Accept's returned plan must never include group-only tags."""
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0", "priority"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True},
        ],
    )
    # Force a non-keep state on the group-only tag (shouldn't be
    # possible via the UI, but the filter must still strip it).
    screen.plan["priority"] = "add"
    screen.plan["prio:p0"] = "add"
    captured: dict = {}
    screen.dismiss = lambda result: captured.update({"result": result})  # type: ignore
    screen.action_accept()
    result = captured["result"]
    assert "priority" not in result
    assert result["prio:p0"] == "add"


def test_add_tags_inserts_at_top_level(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["work"],
        rules=[{"tags": ["work"], "color": "#88ccff"}],
        monkeypatch=monkeypatch,
    )
    screen._on_add_tags("newtag1, newtag2")
    assert "newtag1" in screen.tags
    assert "newtag2" in screen.tags
    # New tags marked as add.
    assert screen.plan["newtag1"] == "add"
    assert screen.plan["newtag2"] == "add"
    # Tree rebuilt — new tags appear as orphans.
    rows = screen._visible_rows()
    names = [r.name for r in rows]
    assert "newtag1" in names
    assert "newtag2" in names


def test_clear_filter_resets_state(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["python", "rust"],
        rules=[
            {"tags": ["python", "rust"], "parents": ["programming"]},
        ],
        monkeypatch=monkeypatch,
    )
    screen.filter_text = "python"
    screen._invalidate_rows_cache()
    assert len(screen._visible_rows()) == 2  # programming + python
    screen.action_clear_filter()
    assert screen.filter_text == ""
    # Now all three are visible (programming, python, rust).
    assert len(screen._visible_rows()) == 3


def test_format_row_applies_configured_style(tmp_path: Path) -> None:
    """The tag's configured color/bold/prefix/suffix must appear in
    the rendered row. The checkbox keeps its presence-based color
    so it stays distinct from the styled name."""
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0"],
        rules=[
            {
                "match": "^prio:",
                "parents": ["priority"],
                "color": "#ff5555",
                "bold": True,
                "prefix": "⚡ ",
            },
            {"tags": ["priority"], "group_only": True},
        ],
    )
    rows = screen._visible_rows()
    target = next(r for r in rows if r.name == "prio:p0")
    rendered = screen._format_row(target, is_cursor=True)
    # Configured style + display string come through.
    assert "bold #ff5555" in rendered
    assert "⚡ prio:p0" in rendered
    # Default checkbox color stays "white" since presence is "none".
    assert "[white]\\[+]" in rendered or "[white]\\[ ]" in rendered


def test_format_row_group_only_uses_dim_with_display(tmp_path: Path) -> None:
    """Group-only rows render dim but still show any configured
    prefix/suffix on the name."""
    screen = _make_screen(
        tmp_path,
        tags=["prio:p0"],
        rules=[
            {"match": "^prio:", "parents": ["priority"]},
            {"tags": ["priority"], "group_only": True, "prefix": "★ "},
        ],
    )
    rows = screen._visible_rows()
    target = next(r for r in rows if r.name == "priority")
    rendered = screen._format_row(target, is_cursor=False)
    assert "(group-only)" in rendered
    assert "★ priority" in rendered
    assert "[dim]" in rendered


def test_typing_filter_jumps_cursor_to_first_match(
    tmp_path: Path, monkeypatch,
) -> None:
    """User types "python" — the cursor must land on python directly,
    not on the first row of the visible tree (which would be the
    group-only parent)."""
    screen = _make_screen(
        tmp_path,
        tags=["python", "rust", "home"],
        rules=[
            {"tags": ["python", "rust"], "parents": ["programming"]},
            {"tags": ["programming"], "group_only": True},
        ],
        monkeypatch=monkeypatch,
    )
    # Simulate the user typing "python" one char at a time.
    for ch in "python":
        screen.filter_text += ch
        screen._jump_to_first_match()
    current = screen._current_row()
    assert current is not None
    assert current.name == "python"


def test_filter_to_group_falls_back_to_first_selectable_child(
    tmp_path: Path, monkeypatch,
) -> None:
    """Typing the name of a group_only tag → no matched selectable
    rows. The cursor falls back to the first selectable, which is
    the first child of the group."""
    screen = _make_screen(
        tmp_path,
        tags=["python", "rust"],
        rules=[
            {"tags": ["python", "rust"], "parents": ["programming"]},
            {"tags": ["programming"], "group_only": True},
        ],
        monkeypatch=monkeypatch,
    )
    screen.filter_text = "programming"
    screen._jump_to_first_match()
    current = screen._current_row()
    assert current is not None
    assert current.group_only is False
    # First selectable child of programming.
    assert current.name in {"python", "rust"}


def test_backspace_repositions_cursor_to_new_first_match(
    tmp_path: Path, monkeypatch,
) -> None:
    """Editing the filter (backspace) re-jumps the cursor each time
    so users can refine without arrow-key bookkeeping."""
    screen = _make_screen(
        tmp_path,
        tags=["python", "pytest", "rust"],
        rules=[
            {"tags": ["python", "pytest", "rust"], "parents": ["programming"]},
            {"tags": ["programming"], "group_only": True},
        ],
        monkeypatch=monkeypatch,
    )
    screen.filter_text = "pyt"
    screen._jump_to_first_match()
    first = screen._current_row()
    assert first is not None
    # Both python and pytest match; the first (alphabetical) wins.
    assert first.name == "pytest"

    screen.filter_text = "py"
    screen._jump_to_first_match()
    second = screen._current_row()
    # Same first hit (python/pytest both match "py", pytest comes
    # first alphabetically inside the programming group).
    assert second.name == "pytest"

    screen.filter_text = ""
    screen._jump_to_first_match()
    cleared = screen._current_row()
    assert cleared is not None
    # No matches → fall back to first selectable.
    assert cleared.group_only is False


def test_jump_to_first_match_handles_no_matches(
    tmp_path: Path, monkeypatch,
) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["python"],
        rules=[{"tags": ["python"], "parents": ["programming"]}],
        monkeypatch=monkeypatch,
    )
    screen.filter_text = "nothing-matches"
    screen._jump_to_first_match()
    # Visible rows are empty; index reset to 0 (and _current_row is None).
    assert screen._current_row() is None
    assert screen.index == 0


def test_no_visible_rows_when_filter_misses(tmp_path: Path) -> None:
    screen = _make_screen(
        tmp_path,
        tags=["python"],
        rules=[{"tags": ["python"], "parents": ["programming"]}],
    )
    screen.filter_text = "nothing-here"
    screen._invalidate_rows_cache()
    assert screen._visible_rows() == []
