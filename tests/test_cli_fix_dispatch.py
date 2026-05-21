from __future__ import annotations

from pathlib import Path

from homebase.cli import dispatch as cli_dispatch
from homebase.cli import parser as cli_parser

cli_dispatch.build_cli_parser = cli_parser.build_cli_parser
cli_dispatch.parse_ignore_featureset_values = cli_parser.parse_ignore_featureset_values


def _stub_kwargs(**overrides):
    base = dict(
        cmd_ls=lambda _a, **_kw: 0,
        cmd_new=lambda _ns, _bd, _cwd: 0,
        cmd_completion=lambda _a: 0,
        cmd_internal_complete=lambda _a, _b, _c: 0,
        cmd_recent=lambda _a: 0,
        cmd_help_actions=lambda _a, _b, _c, _d: 0,
        cmd_setup=lambda _a, _b, _c: 0,
        cmd_cache_warm=lambda: 0,
        cmd_tags_sync=lambda _a, _b, _c: 0,
        cmd_tags_ls=lambda _a: 0,
        cmd_hooks_refresh=lambda _bd, **_kw: 0,
        cmd_utils=lambda _a, _b: 0,
        cmd_archive_mv=lambda _a, _b, **_kw: 0,
        cmd_cd=lambda _a, _b: 0,
        cmd_rm=lambda _a, _b: 0,
        cmd_fix=lambda _paths, **_kw: 0,
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
    )
    base.update(overrides)
    return base


def _run(args, capture):
    parser = cli_parser.build_cli_parser()
    ns = parser.parse_args(args)
    return cli_dispatch.dispatch_command(
        ns,
        parser=parser,
        base_dir=Path("."),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_kwargs(cmd_fix=capture),
    )


def test_fix_default_passes_all_kinds() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["paths"] = list(paths)
        seen["include"] = set(include)
        seen["yes"] = yes
        return 0

    rc = _run(["fix", "."], _capture)
    assert rc == 0
    assert seen["paths"] == ["."]
    assert seen["include"] == {"marker", "archive-entry"}
    assert seen["yes"] is False


def test_fix_yes_flag_propagates() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["yes"] = yes
        return 0

    rc = _run(["fix", "--yes", "."], _capture)
    assert rc == 0
    assert seen["yes"] is True


def test_fix_marker_whitelist() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["include"] = set(include)
        return 0

    rc = _run(["fix", "--marker", "."], _capture)
    assert rc == 0
    assert seen["include"] == {"marker"}


def test_fix_no_marker_blacklist() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["include"] = set(include)
        return 0

    rc = _run(["fix", "--no-marker", "."], _capture)
    assert rc == 0
    assert seen["include"] == {"archive-entry"}


def test_fix_conflicting_flags_error(capsys) -> None:
    def _capture(*_a, **_kw):
        raise AssertionError("cmd_fix should not run on conflict")

    rc = _run(["fix", "--marker", "--no-marker", "."], _capture)
    assert rc == 2
    assert "cannot combine" in capsys.readouterr().err


def test_fix_all_flag_propagates() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["all_targets"] = all_targets
        return 0

    rc = _run(["fix", "--all"], _capture)
    assert rc == 0
    assert seen["all_targets"] is True


def test_fix_multi_path_passes_all() -> None:
    seen: dict = {}

    def _capture(paths, *, include, yes, all_targets=False):
        seen["paths"] = list(paths)
        return 0

    rc = _run(["fix", "a", "b", "c"], _capture)
    assert rc == 0
    assert seen["paths"] == ["a", "b", "c"]
