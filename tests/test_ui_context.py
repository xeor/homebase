from __future__ import annotations

from zoneinfo import ZoneInfo

from homebase.core.models import PaneRef, ProjectRow, PropertyDef
from homebase.ui.app import BApp
from homebase.ui.context import UIContext


def test_bapp_uses_passed_ui_context_for_runtime_config(tmp_path) -> None:
    ctx = UIContext(
        base_dir=tmp_path,
        archive_tz=ZoneInfo("UTC"),
        archive_tz_name="UTC",
        property_defs=[PropertyDef(key="x", label="X", token="X")],
        wip_open_symbol_map={"x": 9},
        named_filters={"mine": "#me"},
        saved_filter_queries=["#me"],
        suffixes=[".x"],
        file_view_exclude_patterns=["*.lock"],
        custom_actions=[{"id": "cx", "label": "Custom", "command": "true"}],
        open_mode_config={"profile": "terminal"},
        notes_config={"enabled": "yes"},
        reconcile_config={
            "active": {"enabled": False, "interval_s": 11.0},
            "archive": {"enabled": True, "interval_s": 22.0},
        },
    )

    app = BApp(tmp_path, ctx=ctx)

    assert app.ctx is ctx
    assert app.custom_actions == ctx.custom_actions
    assert app.open_mode == ctx.open_mode_config
    assert app.notes_config == ctx.notes_config
    assert app.reconcile_config["active"]["interval_s"] == 11.0
    assert app.reconcile_config["archive"]["interval_s"] == 22.0
    assert app.ctx.suffixes == [".x"]
    assert app.ctx.wip_open_symbol_map == {"x": 9}


def test_bapp_adds_dynamic_properties_from_query_specs(tmp_path) -> None:
    ctx = UIContext(
        base_dir=tmp_path,
        archive_tz=ZoneInfo("UTC"),
        archive_tz_name="UTC",
        property_defs=[
            PropertyDef(
                key="act",
                label="active",
                token="ACT",
                queries=({"type": "tmux_open_panes"},),
            ),
            PropertyDef(
                key="edt",
                label="editor",
                token="EDT",
                queries=(
                    {
                        "type": "tmux_editor_commands",
                        "commands": ["nvim"],
                    },
                ),
            ),
        ],
    )
    app = BApp(tmp_path, ctx=ctx)
    row = ProjectRow(
        path=tmp_path / "demo",
        name="demo",
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
    )
    app.open_panes_by_project[row.path] = [
        PaneRef(
            pane_id="%1",
            target="s:1.1",
            window_name="w",
            command="nvim",
            cwd=row.path,
            active=True,
        )
    ]
    app.open_pane_count_by_project[row.path] = 1
    app._apply_dynamic_properties_to_row(row)
    assert "act" in row.properties
    assert "edt" in row.properties


def test_bapp_editor_query_matches_command(tmp_path) -> None:
    ctx = UIContext(
        base_dir=tmp_path,
        archive_tz=ZoneInfo("UTC"),
        archive_tz_name="UTC",
        property_defs=[
            PropertyDef(
                key="edt",
                label="editor",
                token="EDT",
                queries=(
                    {
                        "type": "tmux_editor_commands",
                        "commands": ["code-insiders"],
                    },
                ),
            ),
        ],
    )
    app = BApp(tmp_path, ctx=ctx)
    row = ProjectRow(
        path=tmp_path / "demo2",
        name="demo2",
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
    )
    app.open_panes_by_project[row.path] = [
        PaneRef(
            pane_id="%2",
            target="s:1.2",
            window_name="w",
            command="code-insiders",
            cwd=row.path,
            active=True,
        )
    ]
    app._apply_dynamic_properties_to_row(row)
    assert "edt" in row.properties
