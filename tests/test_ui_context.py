from __future__ import annotations

from zoneinfo import ZoneInfo

from homebase.core.models import PropertyDef
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
