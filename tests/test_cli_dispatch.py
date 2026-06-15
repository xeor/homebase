from __future__ import annotations

from pathlib import Path

from homebase.cli import dispatch as cli_dispatch
from homebase.cli import parser as cli_parser

cli_dispatch.build_cli_parser = cli_parser.build_cli_parser
cli_dispatch.parse_ignore_featureset_values = cli_parser.parse_ignore_featureset_values


def test_parse_ignore_featureset_values_splits_csv() -> None:
    out = cli_dispatch.parse_ignore_featureset_values(["a,b", " c "])
    assert out == {"a", "b", "c"}


def _stub_dispatch_kwargs(**overrides: object) -> dict[str, object]:
    """Default stub callables for ``dispatch_command``. Tests can
    override specific entries to assert routing behavior."""
    base = dict(
        cmd_ls=lambda _a, **_kw: 0,
        cmd_json=lambda _a, **_kw: 0,
        cmd_new=lambda _ns, _bd, _cwd: 0,
        cmd_completion=lambda _a: 0,
        cmd_internal_complete=lambda _a, _b, _c: 0,
        cmd_recent=lambda _a: 0,
        cmd_help=lambda _ns: 0,
        cmd_setup=lambda _a, _b, _c: 0,
        cmd_cache_warm=lambda: 0,
        cmd_tags_sync=lambda _a, _b, _c: 0,
        cmd_tags_ls=lambda _a: 0,
        cmd_hooks_refresh=lambda _bd, **_kw: 0,
        cmd_utils=lambda _a, _b: 0,
        cmd_archive_mv=lambda _a, _b, **_kw: 0,
        cmd_cd=lambda _a, _b: 0,
        cmd_open=lambda _a, _b: 0,
        cmd_raycast=lambda _a, _b, _c, _d: 0,
        cmd_rm=lambda _a, _b: 0,
        cmd_fix=lambda _a: 0,
        cmd_deworktree=lambda _bd, _path: 0,
        cmd_fix_worktrees=lambda _bd, _apply: 0,
        cmd_archive_ls=lambda _a, _b: 0,
        cmd_archive_undo=lambda _a, _b: 0,
        cmd_archive_restore_entry=lambda _a, _b: 0,
        cmd_tmux_load=lambda _a: 0,
        cmd_tmux_save=lambda _a, _b, _c, _d, _e, _f, _g: 0,
        cmd_benchmark=lambda _a, _b, _c, _d, _e, _f: 0,
        cmd_test_regression=lambda _a, _b, _c, _d: 0,
        cmd_test=lambda _a, _b, _c, _d: 0,
        cmd_example_generate=lambda _a, _b, _c: 0,
    )
    base.update(overrides)
    return base


def test_dispatch_command_ls_path() -> None:
    """``b ls`` routes through ``cmd_ls`` with the parsed flags."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["ls", "tag:work", "-l", "--archived"])
    seen: list[dict[str, object]] = []
    def _capture(_base, **kw):
        seen.append(kw)
        return 7
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("."),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_ls=_capture),
    )
    assert rc == 7
    assert seen == [
        {
            "filter_expr": "tag:work",
            "long_format": True,
            "with_git": False,
            "show_archived": True,
            "with_created": False,
            "with_active": False,
            "with_wip": False,
            "with_worktree_of": False,
            "with_src": False,
            "with_path": False,
            "with_description": False,
            "with_props": False,
        }
    ]


def test_dispatch_command_json_routes_through_cmd_json() -> None:
    """``b json '#infra' --archived`` parses cleanly and reaches
    ``cmd_json`` with the joined filter expression and the archived
    flags forwarded."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["json", "#infra", "--archived"])
    seen: list[dict[str, object]] = []
    def _capture(_base, **kw):
        seen.append(kw)
        return 9
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("."),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_json=_capture),
    )
    assert rc == 9
    assert seen == [{
        "filter_expr": "#infra",
        "include_archived": True,
        "archived_only": False,
    }]


def test_dispatch_command_json_archived_only_is_mutually_exclusive() -> None:
    """``--archived`` and ``--archived-only`` are mutually exclusive
    at the parser level — using both must fail at parse time, so
    consumers can't accidentally combine them."""
    import pytest
    parser = cli_dispatch.build_cli_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["json", "--archived", "--archived-only"])


def test_bare_b_archive_routes_to_mv_cwd() -> None:
    """``b archive`` with no subcommand archives cwd (".") — same as
    ``b a``. The dispatcher must hand off to ``cmd_archive_mv``."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["archive"])
    assert ns.command == "archive"
    assert ns.archive_subcommand is None

    seen: list[dict] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, paths, **kw: (
                seen.append({"bd": bd, "paths": list(paths), **kw}) or 0
            ),
        ),
    )
    assert rc == 0
    assert seen == [{"bd": Path("/base"), "paths": ["."], "yes": False}]


def test_b_archive_mv_still_works_with_path() -> None:
    """``b archive mv foo`` continues to route through cmd_archive_mv
    with the explicit path."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["archive", "mv", "foo"])
    seen: list[dict] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, paths, **kw: (
                seen.append({"bd": bd, "paths": list(paths), **kw}) or 0
            ),
        ),
    )
    assert rc == 0
    assert seen == [{"bd": Path("/base"), "paths": ["foo"], "yes": False}]


def test_b_archive_mv_multi_path_and_yes() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["archive", "mv", "foo", "bar", "--yes"])
    seen: list[dict] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, paths, **kw: (
                seen.append({"bd": bd, "paths": list(paths), **kw}) or 0
            ),
        ),
    )
    assert rc == 0
    assert seen == [
        {"bd": Path("/base"), "paths": ["foo", "bar"], "yes": True},
    ]


def test_b_a_alias_multi_path() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["a", "foo", "bar"])
    seen: list[dict] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, paths, **kw: (
                seen.append({"bd": bd, "paths": list(paths), **kw}) or 0
            ),
        ),
    )
    assert rc == 0
    assert seen[0]["paths"] == ["foo", "bar"]


def _dispatch(ns_args: list[str], **overrides: object) -> tuple[int, dict[str, object]]:
    """Build CLI parser, parse args, dispatch through stubs."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(ns_args)
    captured: dict[str, object] = {}
    base_overrides = {}
    for key, value in overrides.items():
        if callable(value):
            base_overrides[key] = value
        else:
            base_overrides[key] = lambda *_a, _value=value, **_k: _value
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: captured.setdefault("no_arg", True) and 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(**base_overrides),
    )
    return rc, captured


def test_dispatch_no_command_calls_no_arg_flow() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args([])
    seen: list[tuple[Path, Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda b, c, q: (seen.append((b, c, q)) or 5),
        initial_filter_expr="initial",
        **_stub_dispatch_kwargs(),
    )
    assert rc == 5
    assert seen[0][2] == "initial"


def test_dispatch_help_routes_through_cmd_help() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["help"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_help=lambda _ns: 99),
    )
    assert rc == 99


def test_dispatch_new_routes_through_cmd_new() -> None:
    seen: list[Path] = []
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["new"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_new=lambda _ns, bd, _cwd: (seen.append(bd) or 4),
        ),
    )
    assert rc == 4
    assert seen == [Path("/base")]


def test_dispatch_recent_routes_through_cmd_recent() -> None:
    seen: list[Path] = []
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["recent"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_recent=lambda bd: (seen.append(bd) or 11)),
    )
    assert rc == 11
    assert seen == [Path("/base")]


def test_dispatch_setup_passes_dry_run_and_json() -> None:
    seen: list[tuple[Path, Path, bool, dict[str, object]]] = []
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["setup", "--dry-run", "--json"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_setup=lambda bd, bin_dir, dry, **kw: (
                seen.append((bd, bin_dir, dry, kw)) or 13
            ),
        ),
    )
    assert rc == 13
    assert seen[0][2] is True
    assert seen[0][3] == {"json_output": True}


def test_dispatch_cache_warm_returns_1_for_unknown_subcommand() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["cache", "warm"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_cache_warm=lambda: 21),
    )
    assert rc == 21


def test_dispatch_tags_ls_and_sync() -> None:
    parser = cli_dispatch.build_cli_parser()

    ns = parser.parse_args(["tags", "ls"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_tags_ls=lambda _bd: 33),
    )
    assert rc == 33

    ns2 = parser.parse_args(["tags", "sync-_tags", "--debug"])
    rc2 = cli_dispatch.dispatch_command(
        ns2,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_tags_sync=lambda _bd, _sync, _debug: 44),
    )
    assert rc2 == 44


def test_dispatch_hooks_refresh_passes_filters() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(
        ["hooks", "refresh", "--all", "--dry-run", "--archived"]
    )
    seen: list[dict[str, object]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_hooks_refresh=lambda bd, **kw: (
                seen.append({"base": bd, **kw}) or 50
            ),
        ),
    )
    assert rc == 50
    assert seen[0]["dry_run"] is True
    assert seen[0]["select_all"] is True
    assert seen[0]["show_archived"] is True


def test_dispatch_cd_uses_last_name_arg() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["cd", "alpha"])
    seen: list[tuple[Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_cd=lambda bd, name: (seen.append((bd, name)), 60)[1]),
    )
    assert rc == 60
    assert seen == [(Path("/base"), "alpha")]


def test_dispatch_open_uses_last_name_arg() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["open", "#infra", "alpha"])
    seen: list[tuple[Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_open=lambda bd, name: (seen.append((bd, name)), 61)[1]),
    )
    assert rc == 61
    assert seen == [(Path("/base"), "alpha")]


def test_dispatch_raycast_actions_forwards_project() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["integration", "raycast", "actions", "alpha"])
    seen: list[tuple[Path, str, str, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_raycast=lambda bd, sub, project, action: (
                seen.append((bd, sub, project, action)),
                62,
            )[1]
        ),
    )
    assert rc == 62
    assert seen == [(Path("/base"), "actions", "alpha", "")]


def test_dispatch_raycast_run_forwards_action_and_project() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["integration", "raycast", "run", "open_item", "alpha"])
    seen: list[tuple[Path, str, str, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_raycast=lambda bd, sub, project, action: (
                seen.append((bd, sub, project, action)),
                63,
            )[1]
        ),
    )
    assert rc == 63
    assert seen == [(Path("/base"), "run", "alpha", "open_item")]


def test_dispatch_rm_forwards_flags() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["rm", "p", "--force-outside-base", "--force"])
    seen: list[dict[str, object]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_rm=lambda path, outside, **kw: (
                seen.append({"path": path, "outside": outside, **kw}) or 70
            ),
        ),
    )
    assert rc == 70
    assert seen[0] == {"path": "p", "outside": True, "force": True}


def test_dispatch_deworktree_and_fix_worktrees() -> None:
    parser = cli_dispatch.build_cli_parser()

    ns = parser.parse_args(["deworktree", "proj"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_deworktree=lambda bd, path: 80),
    )
    assert rc == 80

    ns2 = parser.parse_args(["fix-worktrees", "--apply"])
    rc2 = cli_dispatch.dispatch_command(
        ns2,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_fix_worktrees=lambda bd, apply: (apply, 81)[1],
        ),
    )
    assert rc2 == 81


def test_dispatch_archive_subcommands_ls_undo_restore() -> None:
    parser = cli_dispatch.build_cli_parser()

    rc_ls = cli_dispatch.dispatch_command(
        parser.parse_args(["archive", "ls", "."]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_archive_ls=lambda _bd, _path: 90),
    )
    assert rc_ls == 90

    rc_undo = cli_dispatch.dispatch_command(
        parser.parse_args(["archive", "undo", "."]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_archive_undo=lambda _bd, _path: 91),
    )
    assert rc_undo == 91

    rc_restore = cli_dispatch.dispatch_command(
        parser.parse_args(["archive", "restore", "."]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_archive_restore_entry=lambda _bd, _path: 92),
    )
    assert rc_restore == 92


def test_dispatch_tmux_load_and_save() -> None:
    parser = cli_dispatch.build_cli_parser()

    rc_load = cli_dispatch.dispatch_command(
        parser.parse_args(["tmux", "load", "/proj"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_tmux_load=lambda _dir: 100),
    )
    assert rc_load == 100

    rc_save = cli_dispatch.dispatch_command(
        parser.parse_args(["tmux", "save"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_tmux_save=lambda *_a, **_k: 101,
        ),
    )
    assert rc_save == 101


def test_dispatch_benchmark_subcommands() -> None:
    parser = cli_dispatch.build_cli_parser()

    rc_run = cli_dispatch.dispatch_command(
        parser.parse_args(["benchmark", "run"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_benchmark=lambda *_a: 110),
    )
    assert rc_run == 110

    rc_res = cli_dispatch.dispatch_command(
        parser.parse_args(
            ["benchmark", "results", "--ignore-featureset", "git,archive"]
        ),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_benchmark=lambda *_a: 111),
    )
    assert rc_res == 111


def test_dispatch_test_subcommands() -> None:
    parser = cli_dispatch.build_cli_parser()

    rc_reg = cli_dispatch.dispatch_command(
        parser.parse_args(["test", "regression", "--list"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_test_regression=lambda *_a: 120),
    )
    assert rc_reg == 120

    rc_default = cli_dispatch.dispatch_command(
        parser.parse_args(["test"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_test=lambda *_a: 121),
    )
    assert rc_default == 121


def test_dispatch_example_generate() -> None:
    parser = cli_dispatch.build_cli_parser()
    rc = cli_dispatch.dispatch_command(
        parser.parse_args(["example", "generate", "--path", ".", "--count", "5", "--seed", "7"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_example_generate=lambda _p, _c, _s: 130,
        ),
    )
    assert rc == 130


def test_dispatch_utils_routes() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["utils", "opt-in-nested-discovery"])
    seen: list[tuple[Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_utils=lambda bd, sub: (seen.append((bd, sub)) or 140),
        ),
    )
    assert rc == 140
    assert seen == [(Path("/base"), "opt-in-nested-discovery")]


def test_dispatch_fix_conflict_returns_2(capsys) -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["fix", "--marker", "--no-marker"])
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_fix=lambda *_a, **_kw: 0),
    )
    assert rc == 2
    assert "cannot combine" in capsys.readouterr().err


def test_dispatch_fix_runs_with_default_selection() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["fix", "--yes"])
    seen: list[dict[str, object]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_fix=lambda paths, **kw: (
                seen.append({"paths": list(paths), **kw}) or 150
            ),
        ),
    )
    assert rc == 150
    assert seen[0]["yes"] is True


def test_dispatch_completion_and_internal() -> None:
    parser = cli_dispatch.build_cli_parser()
    rc_compl = cli_dispatch.dispatch_command(
        parser.parse_args(["completion", "fish"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_completion=lambda _shell: 160),
    )
    assert rc_compl == 160

    rc_int = cli_dispatch.dispatch_command(
        parser.parse_args(["__complete", "fish", "2", "b", "ls"]),
        base_dir=Path("/base"),
        bin_dir=Path("/bin"),
        cwd=Path("/cwd"),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_internal_complete=lambda *_a: 161),
    )
    assert rc_int == 161
