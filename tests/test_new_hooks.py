from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _ns(args: list[str]) -> Namespace:
    return build_cli_parser().parse_args(["new", *args])


def test_cmd_new_pre_hook_cancel_stops_create(tmp_path: Path) -> None:
    ns = _ns(["proj"])

    def _pre_hook(ns_obj: Namespace, raw_input: str | None, explicit_name: str | None):
        return False, "blocked", ns_obj, raw_input, explicit_name

    rc = cmd_new(ns, tmp_path, tmp_path, pre_create_hook=_pre_hook)
    assert rc == 1
    assert not (tmp_path / "proj").exists()


def test_cmd_new_pre_hook_mutate_tags_applies(tmp_path: Path) -> None:
    ns = _ns(["proj", "--tag", "old"])

    def _pre_hook(ns_obj: Namespace, raw_input: str | None, explicit_name: str | None):
        ns_obj.tag = ["newtag"]
        return True, "", ns_obj, raw_input, explicit_name

    rc = cmd_new(ns, tmp_path, tmp_path, pre_create_hook=_pre_hook)
    assert rc == 0
    text = (tmp_path / "proj" / ".base.yaml").read_text(encoding="utf-8")
    assert "newtag" in text
    assert "old" not in text
