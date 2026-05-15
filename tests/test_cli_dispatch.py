from __future__ import annotations

from argparse import Namespace
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
        cmd_status=lambda _a: 0,
        cmd_new=lambda _ns, _bd, _cwd: 0,
        cmd_completion=lambda _a: 0,
        cmd_internal_complete=lambda _a, _b, _c: 0,
        cmd_recent=lambda _a: 0,
        cmd_help_actions=lambda _a, _b, _c, _d: 0,
        cmd_setup=lambda _a, _b, _c: 0,
        cmd_cache_warm=lambda: 0,
        cmd_tags_sync=lambda _a, _b, _c: 0,
        cmd_utils=lambda _a, _b: 0,
        cmd_archive_mv=lambda _a, _b: 0,
        cmd_cd=lambda _a, _b: 0,
        cmd_rm=lambda _a, _b: 0,
        cmd_fix=lambda _a: 0,
        cmd_archive_ls=lambda _a, _b: 0,
        cmd_archive_undo=lambda _a, _b: 0,
        cmd_archive_restore_entry=lambda _a, _b: 0,
        cmd_archive_reorganize=lambda _a, _b: 0,
        cmd_tmux_load=lambda _a: 0,
        cmd_tmux_save=lambda _a, _b, _c, _d, _e, _f, _g: 0,
        cmd_benchmark=lambda _a, _b, _c, _d, _e, _f: 0,
        cmd_test_regression=lambda _a, _b, _c, _d: 0,
        cmd_test=lambda _a, _b, _c, _d: 0,
    )
    base.update(overrides)
    return base


def test_dispatch_command_status_path() -> None:
    parser = cli_dispatch.build_cli_parser()
    ns = Namespace(command="status")
    rc = cli_dispatch.dispatch_command(
        ns,
        parser=parser,
        base_dir=Path("."),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(cmd_status=lambda _a: 7),
    )
    assert rc == 7


def test_bare_b_archive_routes_to_mv_cwd() -> None:
    """``b archive`` with no subcommand archives cwd (".") — same as
    ``b a``. The dispatcher must hand off to ``cmd_archive_mv``."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["archive"])
    assert ns.command == "archive"
    assert ns.archive_subcommand is None

    seen: list[tuple[Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        parser=parser,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, path: seen.append((bd, path)) or 0,
        ),
    )
    assert rc == 0
    assert seen == [(Path("/base"), ".")]


def test_b_archive_mv_still_works_with_path() -> None:
    """``b archive mv foo`` continues to route through cmd_archive_mv
    with the explicit path."""
    parser = cli_dispatch.build_cli_parser()
    ns = parser.parse_args(["archive", "mv", "foo"])
    seen: list[tuple[Path, str]] = []
    rc = cli_dispatch.dispatch_command(
        ns,
        parser=parser,
        base_dir=Path("/base"),
        bin_dir=Path("."),
        cwd=Path("."),
        no_arg_flow=lambda _a, _b, _c: 0,
        initial_filter_expr="",
        **_stub_dispatch_kwargs(
            cmd_archive_mv=lambda bd, path: seen.append((bd, path)) or 0,
        ),
    )
    assert rc == 0
    assert seen == [(Path("/base"), "foo")]
