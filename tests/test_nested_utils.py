from __future__ import annotations

from pathlib import Path

from homebase.core import nested as nested_utils


def test_suggest_flat_name_nested(tmp_path: Path) -> None:
    base = tmp_path / "base"
    path = base / "grp" / "sub"
    path.mkdir(parents=True)
    assert nested_utils.suggest_flat_name(base, path) == "grp-sub"


def test_cmd_utils_unknown_subcommand(capsys) -> None:
    rc = nested_utils.cmd_utils(
        Path("."),
        "unknown",
        cmd_utils_opt_in_nested_discovery=lambda _b: 0,
    )
    err = capsys.readouterr().err
    assert rc == 1
    assert "unknown utils subcommand" in err
