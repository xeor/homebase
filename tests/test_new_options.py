from __future__ import annotations

from argparse import Namespace

import homebase.workspace.new  # noqa: F401  (register sources)
from homebase.workspace.new.options import resolve_options


def _ns(**overrides) -> Namespace:
    defaults = dict(
        tmp=None,
        timestamp=None,
        open=None,
        cd=None,
        confirm=None,
        ts_name=False,
        alpha_name=False,
        ask_name=False,
        ask_source=False,
        archive=False,
        dry_run=False,
        yes=False,
        multi=False,
        template="",
        tag=[],
        post=[],
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def test_defaults_only() -> None:
    opts = resolve_options("empty", _ns())
    assert opts.tmp is False
    assert opts.timestamp is False
    # `open` defaults to True so `b new` drops the user into the new
    # project by default. `--no-open` / `--no-cd` opts out.
    assert opts.open is True


def test_no_open_overrides_default() -> None:
    opts = resolve_options("empty", _ns(open=False))
    assert opts.open is False


def test_no_cd_overrides_default() -> None:
    opts = resolve_options("empty", _ns(cd=False))
    assert opts.open is False


def test_cli_overrides_defaults() -> None:
    opts = resolve_options("empty", _ns(tmp=True, timestamp=True))
    assert opts.tmp is True
    assert opts.timestamp is True


def test_no_tmp_overrides_config_true() -> None:
    opts = resolve_options("empty", _ns(tmp=False), source_cfg={"tmp": True})
    assert opts.tmp is False


def test_cd_aliases_open() -> None:
    opts = resolve_options("empty", _ns(cd=True))
    assert opts.open is True


def test_tag_and_post_lists() -> None:
    opts = resolve_options(
        "empty",
        _ns(tag=["a", "b"], post=["echo hi"]),
        source_cfg={"tags": ["base"], "post": ["init"]},
    )
    assert opts.tags == ("base", "a", "b")
    assert opts.post == ("init", "echo hi")
