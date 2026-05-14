from __future__ import annotations

from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, base)


def test_legacy_create_templates_block_is_ignored(tmp_path: Path) -> None:
    """A leftover ``create_templates:`` block in the config must not
    block ``b new`` from running — the block is dead config, not a
    fatal error. (Earlier versions hard-failed with a migration
    pointer; the user explicitly asked for it to be tolerated since
    the tool should never refuse to start over unrelated stale keys.)
    """
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "create_templates:\n  - key: tmp\n",
        encoding="utf-8",
    )
    rc = _run(tmp_path, ["myproj"])
    assert rc == 0
    assert (tmp_path / "myproj").is_dir()


def test_n_alias_works(tmp_path: Path) -> None:
    ns = build_cli_parser().parse_args(["n", "aliased"])
    rc = cmd_new(ns, tmp_path, tmp_path)
    assert rc == 0
    assert (tmp_path / "aliased").is_dir()


def test_child_as_tmp_generates_name(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "new:\n"
        "  sources:\n"
        "    scratch:\n"
        "      parent: empty\n"
        "      ts-name: true\n"
        "      tmp: true\n",
        encoding="utf-8",
    )
    rc = _run(tmp_path, ["--as", "scratch", "--no-open"])
    assert rc == 0
    created = [p for p in tmp_path.iterdir() if p.is_dir() and not p.name.startswith(".")]
    assert len(created) == 1
    assert created[0].name.endswith(".tmp")


def test_child_unknown_parent_fails(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "new:\n  sources:\n    scratch:\n      parent: nonexistent\n",
        encoding="utf-8",
    )
    rc = _run(tmp_path, ["--as", "scratch"])
    assert rc == 2


def test_child_missing_parent_fails(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "new:\n  sources:\n    scratch:\n      tags: [x]\n",
        encoding="utf-8",
    )
    rc = _run(tmp_path, ["--as", "scratch"])
    assert rc == 2


def test_builtin_with_parent_rejected(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "new:\n  sources:\n    empty:\n      parent: local\n",
        encoding="utf-8",
    )
    rc = _run(tmp_path, ["myproj"])
    assert rc == 2
