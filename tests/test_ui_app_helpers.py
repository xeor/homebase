"""Module-level / pure helper tests for ``ui/app.py``.

These cover the small functions that live at module scope (``_as_int``,
``_as_float``, ``_build_view_config_default``,
``_collect_hook_refresh_candidates``) plus a few BApp methods that can
be tested with a SimpleNamespace stub instead of booting Textual."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from homebase.core.constants import TABLE_SIDE_WIDTH_PRESETS
from homebase.core.models import HookSpec, ManagedProcess, ProjectRow
from homebase.ui import app as ui_app

# ---- _as_int --------------------------------------------------------


@pytest.mark.parametrize(
    "value,default,expected",
    [
        (3, 0, 3),
        (3.7, 0, 3),
        ("5", 0, 5),
        ("nope", 9, 9),
        (None, 7, 7),
        ([], 4, 4),
        (True, 0, 1),
        (False, 9, 0),
    ],
)
def test_as_int_handles_all_types(value, default, expected) -> None:
    assert ui_app._as_int(value, default) == expected


@pytest.mark.parametrize(
    "value,default,expected",
    [
        (3, 0.0, 3.0),
        ("2.5", 0.0, 2.5),
        ("bogus", 1.5, 1.5),
        (None, 4.0, 4.0),
        (True, 0.0, 1.0),
    ],
)
def test_as_float_handles_all_types(value, default, expected) -> None:
    assert ui_app._as_float(value, default) == expected


# ---- _build_view_config_default -------------------------------------


def test_view_config_default_has_active_and_archive_keys() -> None:
    cfg = ui_app._build_view_config_default()
    assert set(cfg) == {"active", "archive"}
    for mode_cfg in cfg.values():
        assert "actions" in mode_cfg
        # Every entry must be an (id, label) tuple.
        for entry in mode_cfg["actions"]:
            assert isinstance(entry, tuple)
            assert len(entry) == 2


def test_view_config_default_excludes_actions_out_of_view_scope() -> None:
    """An action listed for ``active`` but with view_scope=("archive",)
    must not leak into the active config."""
    cfg = ui_app._build_view_config_default()
    active_ids = [aid for aid, _label in cfg["active"]["actions"]]
    archive_ids = [aid for aid, _label in cfg["archive"]["actions"]]
    # The two view modes must not share any pack/unpack/restore actions.
    assert "restore" not in active_ids
    assert "pack" not in active_ids
    assert "new_worktree" not in archive_ids


# ---- _collect_hook_refresh_candidates -------------------------------


def _row(path: str = "/tmp/p", *, tags=None) -> ProjectRow:
    return ProjectRow(
        path=Path(path),
        name=Path(path).name,
        branch="",
        dirty="",
        last="",
        src="fs",
        created="",
        tags=list(tags or []),
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        packed=False,
        pack_format=None,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        size_bytes=0,
        size_refresh_count=0,
        worktree_of="",
        repo_dir="",
    )


def _spec(
    *,
    name="syncer",
    timing="post",
    event="tag_change",
    enabled=True,
    refresh_enabled=True,
    refresh_min_interval_s=60.0,
    views=(),
) -> HookSpec:
    return HookSpec(
        timing=timing,
        event=event,
        name=name,
        source="bundled",
        enabled=enabled,
        views=tuple(views),
        config={},
        slow_warn_s=1.0,
        refresh_enabled=refresh_enabled,
        refresh_min_interval_s=refresh_min_interval_s,
    )


def test_collect_hook_refresh_candidates_only_post_timing() -> None:
    spec = _spec(timing="pre")
    out = ui_app._collect_hook_refresh_candidates(
        [_row(tags=["x"])],
        now=1000.0,
        hook_specs={("pre", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert out == []


def test_collect_hook_refresh_candidates_skips_disabled() -> None:
    spec = _spec(enabled=False)
    out = ui_app._collect_hook_refresh_candidates(
        [_row(tags=["x"])],
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert out == []


def test_collect_hook_refresh_candidates_skips_when_refresh_off() -> None:
    spec = _spec(refresh_enabled=False)
    out = ui_app._collect_hook_refresh_candidates(
        [_row(tags=["x"])],
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert out == []


def test_collect_hook_refresh_candidates_filters_by_view() -> None:
    """A spec with explicit views must only fire in those views."""
    spec = _spec(views=("archive",))
    out = ui_app._collect_hook_refresh_candidates(
        [_row(tags=["x"])],
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert out == []


def test_collect_hook_refresh_candidates_skips_tag_change_without_tags() -> None:
    """``tag_change`` is only interesting for rows that have at least
    one tag — no tags means there's nothing to re-sync."""
    spec = _spec(event="tag_change")
    out = ui_app._collect_hook_refresh_candidates(
        [_row(tags=[])],
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert out == []


def test_collect_hook_refresh_candidates_respects_min_interval() -> None:
    spec = _spec(refresh_min_interval_s=60.0)
    row = _row(tags=["x"])
    last_ts = {(row.path, spec.name): 950.0}  # 50s ago, < 60s
    out = ui_app._collect_hook_refresh_candidates(
        [row],
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last=last_ts,
    )
    assert out == []

    # After enough time has passed, it surfaces again.
    out = ui_app._collect_hook_refresh_candidates(
        [row],
        now=1011.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last=last_ts,
    )
    assert out == [(row, spec)]


def test_collect_hook_refresh_candidates_returns_row_spec_pairs() -> None:
    spec = _spec()
    rows = [_row("/tmp/a", tags=["x"]), _row("/tmp/b", tags=["y"])]
    out = ui_app._collect_hook_refresh_candidates(
        rows,
        now=1000.0,
        hook_specs={("post", "tag_change"): [spec]},
        view_mode="active",
        hook_refresh_last={},
    )
    assert [(r.path, s.name) for r, s in out] == [
        (Path("/tmp/a"), "syncer"),
        (Path("/tmp/b"), "syncer"),
    ]


# ---- BApp methods: bound-method invocation against a stub ----------


def _bapp_methods(stub: SimpleNamespace, *names: str) -> None:
    """Bind the named ``BApp`` methods onto a stub so they can be
    called without instantiating the full app."""
    for name in names:
        method = getattr(ui_app.BApp, name)
        setattr(stub, name, method.__get__(stub, type(stub)))


def test_table_pin_wip_top_enabled_reads_behavior_flag() -> None:
    stub = SimpleNamespace(table_behavior={"pin_wip_top": True})
    _bapp_methods(stub, "_table_pin_wip_top_enabled")
    assert stub._table_pin_wip_top_enabled() is True

    stub.table_behavior = {}
    assert stub._table_pin_wip_top_enabled() is False


def test_table_side_width_pct_snaps_to_preset() -> None:
    """``side_width_pct`` from config is snapped to the nearest preset
    so the table always renders at one of the supported widths."""
    stub = SimpleNamespace(table_behavior={"side_width_pct": 31})
    _bapp_methods(stub, "_table_side_width_pct")
    assert stub._table_side_width_pct() == 30
    # 23 is closer to 25 than 20.
    stub.table_behavior = {"side_width_pct": 23}
    assert stub._table_side_width_pct() == 25
    # Default value of 33 is itself a preset.
    stub.table_behavior = {}
    assert stub._table_side_width_pct() == 33
    # Garbage value falls back to default (33).
    stub.table_behavior = {"side_width_pct": "bogus"}
    assert stub._table_side_width_pct() == 33


def test_table_side_width_pct_uses_only_supported_presets() -> None:
    stub = SimpleNamespace(table_behavior={"side_width_pct": 999})
    _bapp_methods(stub, "_table_side_width_pct")
    assert stub._table_side_width_pct() in TABLE_SIDE_WIDTH_PRESETS


def test_global_config_button_actions_returns_two_buttons() -> None:
    stub = SimpleNamespace()
    _bapp_methods(stub, "_global_config_button_actions")
    out = stub._global_config_button_actions()
    ids = [aid for aid, _label in out]
    assert ids == ["reload_global_config", "edit_global_config"]


def test_visible_button_actions_routes_to_readme_when_selected_readme_tab() -> None:
    captured: list[str] = []

    stub = SimpleNamespace(
        side_main_tab="selected",
        side_selected_tab="readme",
        _readme_button_actions=lambda: (captured.append("readme") or [("a", "A")]),
        _notes_button_actions=lambda: [],
        _global_config_button_actions=lambda: [],
    )
    _bapp_methods(stub, "_visible_button_actions")
    assert stub._visible_button_actions() == [("a", "A")]
    assert captured == ["readme"]


def test_visible_button_actions_routes_to_notes() -> None:
    captured: list[str] = []
    stub = SimpleNamespace(
        side_main_tab="selected",
        side_selected_tab="notes",
        _readme_button_actions=lambda: [],
        _notes_button_actions=lambda: (captured.append("notes") or [("b", "B")]),
        _global_config_button_actions=lambda: [],
    )
    _bapp_methods(stub, "_visible_button_actions")
    assert stub._visible_button_actions() == [("b", "B")]
    assert captured == ["notes"]


def test_visible_button_actions_empty_for_other_selected_tabs() -> None:
    stub = SimpleNamespace(
        side_main_tab="selected",
        side_selected_tab="overview",
        _readme_button_actions=lambda: [("a", "A")],
        _notes_button_actions=lambda: [("b", "B")],
        _global_config_button_actions=lambda: [],
    )
    _bapp_methods(stub, "_visible_button_actions")
    assert stub._visible_button_actions() == []


def test_visible_button_actions_routes_to_global_config_in_settings() -> None:
    stub = SimpleNamespace(
        side_main_tab="settings",
        side_settings_tab="global",
        _readme_button_actions=lambda: [],
        _notes_button_actions=lambda: [],
        _global_config_button_actions=lambda: [("g", "G")],
    )
    _bapp_methods(stub, "_visible_button_actions")
    assert stub._visible_button_actions() == [("g", "G")]


def test_visible_button_actions_empty_for_unknown_main_tab() -> None:
    stub = SimpleNamespace(
        side_main_tab="info",
        side_selected_tab="overview",
        _readme_button_actions=lambda: [("a", "A")],
        _notes_button_actions=lambda: [("b", "B")],
        _global_config_button_actions=lambda: [("g", "G")],
    )
    _bapp_methods(stub, "_visible_button_actions")
    assert stub._visible_button_actions() == []


# ---- _managed_process_info_lines ------------------------------------


def _proc(
    pid: int,
    label: str = "build",
    *,
    started_ts: float = 1000.0,
    ended_ts: float = 0.0,
    returncode: int | None = None,
) -> ManagedProcess:
    return ManagedProcess(
        pid=pid,
        label=label,
        command=f"cmd-{pid}",
        cwd=Path("/tmp/cwd"),
        started_ts=started_ts,
        wait_mode=False,
        terminate_on_quit=True,
        returncode=returncode,
        ended_ts=ended_ts,
    )


def test_managed_process_info_lines_empty_returns_placeholder() -> None:
    stub = SimpleNamespace(
        managed_processes=[],
        _managed_processes_lock=threading.Lock(),
        _esc=str,
    )
    _bapp_methods(stub, "_managed_process_info_lines")
    assert stub._managed_process_info_lines() == ["[dim]no managed processes[/]"]


def test_managed_process_info_lines_counts_running_and_done() -> None:
    rows = [
        _proc(1, "running-1", started_ts=10.0),
        _proc(2, "done-2", started_ts=20.0, ended_ts=25.0, returncode=0),
    ]
    stub = SimpleNamespace(
        managed_processes=rows,
        _managed_processes_lock=threading.Lock(),
        _esc=str,
    )
    _bapp_methods(stub, "_managed_process_info_lines")
    out = stub._managed_process_info_lines()
    assert out[0] == "running: 1  done: 1"
    # First detail block must be the most recently started process (pid=2).
    assert "[2] done-2 - done rc=0" in out[2]


def test_managed_process_info_lines_caps_at_twenty_entries() -> None:
    rows = [_proc(i, f"p{i}", started_ts=float(i)) for i in range(30)]
    stub = SimpleNamespace(
        managed_processes=rows,
        _managed_processes_lock=threading.Lock(),
        _esc=str,
    )
    _bapp_methods(stub, "_managed_process_info_lines")
    out = stub._managed_process_info_lines()
    # Header (2) + 20 procs * 3 lines each = 62.
    assert len(out) == 2 + 20 * 3
