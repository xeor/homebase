from __future__ import annotations

import argparse


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="b")
    parser.add_argument("--base-folder", dest="base_folder", default=None)
    parser.add_argument("--filter", dest="initial_filter", default="")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("help")
    sub.add_parser("status")
    sub.add_parser("new")
    sub.add_parser("recent")
    p_setup = sub.add_parser("setup")
    p_setup.add_argument("--yes", action="store_true")
    p_setup.add_argument("--no-tmux-binding", action="store_true")

    p_cache = sub.add_parser("cache")
    cache_sub = p_cache.add_subparsers(dest="cache_subcommand", required=True)
    cache_sub.add_parser("warm")

    p_tags = sub.add_parser("tags")
    tags_sub = p_tags.add_subparsers(dest="tags_subcommand", required=True)
    p_tags_sync = tags_sub.add_parser("sync-_tags")
    p_tags_sync.add_argument("--debug", action="store_true")

    p_utils = sub.add_parser("utils")
    utils_sub = p_utils.add_subparsers(dest="utils_subcommand", required=True)
    utils_sub.add_parser("opt-in-nested-discovery")

    p_a = sub.add_parser("a")
    p_a.add_argument("path", nargs="?", default=".")

    p_rm = sub.add_parser("rm")
    p_rm.add_argument("path", nargs="?", default=".")
    p_rm.add_argument("--force-outside-base", action="store_true")

    p_migrate = sub.add_parser("migrate")
    p_migrate.add_argument("--archive", action="store_true")
    p_migrate.add_argument("--flat", action="store_true")
    p_migrate.add_argument("paths", nargs="+")

    p_fix = sub.add_parser("fix")
    p_fix.add_argument("path", nargs="?", default=".")

    p_archive = sub.add_parser("archive")
    archive_sub = p_archive.add_subparsers(dest="archive_subcommand", required=True)
    p_archive_mv = archive_sub.add_parser("mv")
    p_archive_mv.add_argument("path", nargs="?", default=".")
    p_archive_ls = archive_sub.add_parser("ls")
    p_archive_ls.add_argument("path", nargs="?", default=".")
    p_archive_undo = archive_sub.add_parser("undo")
    p_archive_undo.add_argument("path", nargs="?", default=".")
    p_archive_restore = archive_sub.add_parser("restore")
    p_archive_restore.add_argument("archived_path")

    p_tmux = sub.add_parser("tmux")
    tmux_sub = p_tmux.add_subparsers(dest="tmux_subcommand", required=True)
    p_tmux_load = tmux_sub.add_parser("load")
    p_tmux_load.add_argument("dir", nargs="?", default=".")
    p_tmux_save = tmux_sub.add_parser("save")
    p_tmux_save.add_argument("dir", nargs="?", default=".")
    p_tmux_save.add_argument("--output", default="")
    p_tmux_save.add_argument("--stdout", action="store_true")
    p_tmux_save.add_argument("--debug", action="store_true")
    p_tmux_save.add_argument("--pane-id", default="")
    p_tmux_save.add_argument("--session-id", default="")

    p_bench = sub.add_parser("benchmark")
    bench_sub = p_bench.add_subparsers(dest="benchmark_subcommand", required=True)
    p_bench_run = bench_sub.add_parser("run")
    p_bench_run.add_argument("--comment", default="")
    p_bench_run.add_argument("--keep-basefolder", action="store_true")
    p_bench_results = bench_sub.add_parser("results")
    p_bench_results.add_argument("--ignore-featureset", action="append", default=[])

    p_test = sub.add_parser("test")
    p_test.add_argument("--comment", default="")
    p_test.add_argument("--keep-basefolder", action="store_true")
    test_sub = p_test.add_subparsers(dest="test_subcommand")
    p_test_reg = test_sub.add_parser("regression")
    p_test_reg.add_argument("--list", action="store_true")
    p_test_reg.add_argument("--case", action="append", default=[])

    return parser


def parse_ignore_featureset_values(values: list[str]) -> set[str]:
    out: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            val = part.strip()
            if val:
                out.add(val)
    return out
