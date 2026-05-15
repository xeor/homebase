from __future__ import annotations

from pathlib import Path

from homebase.cli import completion as cli_completion


def test_completion_script_contains_shell_hooks() -> None:
    assert "complete -F _b_completion b" in cli_completion.completion_script("bash")
    assert "compdef _b_completion b" in cli_completion.completion_script("zsh")
    assert "complete -c b -f -a '(__b_complete)'" in cli_completion.completion_script("fish")


def test_completion_script_passes_double_dash_separator() -> None:
    """Every shell bridge must emit ``--`` between __complete's own
    positionals and the user's typed words. Without it, an in-flight
    option like ``--as`` (or ``--no-tmp``) ends up being parsed at the
    parent level and ``b`` errors out with ``unrecognized arguments``.
    """
    for shell in ("bash", "zsh", "fish"):
        script = cli_completion.completion_script(shell)
        assert "$cword\" --" in script or "$cword --" in script, (
            f"{shell} completion missing -- separator: {script!r}"
        )


def test_internal_complete_parses_option_shaped_words() -> None:
    """Direct check at the parser level: ``b __complete fish 3 -- new --as``
    must parse cleanly (the ``--`` stops parent option parsing) and
    deliver ``--as`` through as a word so the completion machinery can
    react to it."""
    from homebase.cli.parser import build_cli_parser

    parser = build_cli_parser()
    ns = parser.parse_args(["__complete", "fish", "3", "--", "new", "--as"])
    assert ns.command == "__complete"
    # argparse.REMAINDER consumes the leading ``--`` on its own, so
    # words contains only the user-typed tokens.
    assert ns.words == ["new", "--as"]


def test_internal_complete_handles_stale_wrapper_without_dash_dash() -> None:
    """Older shell completion files generated before iter-14 don't
    pass ``--``. Thanks to ``argparse.REMAINDER`` on ``words`` the
    option-shaped tokens (``--as``) still flow through as data
    instead of being re-parsed as parent flags."""
    from homebase.cli.parser import build_cli_parser

    parser = build_cli_parser()
    ns = parser.parse_args(["__complete", "fish", "3", "new", "--as"])
    assert ns.command == "__complete"
    assert ns.words == ["new", "--as"]


def test_completion_candidates_include_top_level_commands() -> None:
    out = cli_completion.completion_candidates(["l"], 1, base_dir=Path("."))
    assert "ls" in out


def test_completion_candidates_new_mode_flags() -> None:
    out = cli_completion.completion_candidates(["new", "--"], 2, base_dir=Path("."))
    assert "--empty" in out
    assert "--local" in out
    assert "--git" in out
    assert "--download" in out
    assert "--downloaded" in out


def test_completion_candidates_new_as_uses_child_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_new_child_source_keys",
        lambda _base_dir: ["scratch", "prj"],
    )
    out = cli_completion.completion_candidates(["new", "--as", "s"], 3, base_dir=Path("."))
    assert out == ["scratch"]


def test_completion_candidates_new_template(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_new_template_keys",
        lambda _base_dir: ["python-uv", "rust"],
    )
    out = cli_completion.completion_candidates(
        ["new", "--template", "r"], 3, base_dir=Path(".")
    )
    assert out == ["rust"]


def test_completion_includes_n_alias() -> None:
    out = cli_completion.completion_candidates([""], 1, base_dir=Path("."))
    assert "n" in out
    assert "new" in out


def test_completion_includes_cd() -> None:
    out = cli_completion.completion_candidates([""], 1, base_dir=Path("."))
    assert "cd" in out


def test_completion_cd_lists_active_projects(tmp_path: Path) -> None:
    """``b cd <tab>`` must show non-archived, non-hidden project
    directories under base — and NOT ``_archive``, ``_tags``, dotfiles,
    or regular files."""
    (tmp_path / "myproj").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "_archive").mkdir()
    (tmp_path / "_tags").mkdir()
    (tmp_path / ".homebase").mkdir()
    (tmp_path / "stray.txt").write_text("ignore me")
    out = cli_completion.completion_candidates(["cd", ""], 2, base_dir=tmp_path)
    assert out == ["myproj", "other"]


def test_completion_cd_prefix_filters(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpine").mkdir()
    (tmp_path / "beta").mkdir()
    out = cli_completion.completion_candidates(["cd", "alp"], 2, base_dir=tmp_path)
    assert out == ["alpha", "alpine"]


def test_completion_rm_offers_projects_and_force(tmp_path: Path) -> None:
    (tmp_path / "foo").mkdir()
    out = cli_completion.completion_candidates(["rm", ""], 2, base_dir=tmp_path)
    assert "foo" in out
    assert "--force" in out
    assert "--force-outside-base" in out


def test_completion_candidates_support_named_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_named_filter_keys",
        lambda _base_dir: ["work", "hot"],
    )
    out = cli_completion.completion_candidates(["--filter", "h"], 2, base_dir=Path("."))
    assert out == ["hot"]


def test_completion_candidates_support_regression_case_values(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_regression_case_names",
        lambda: ["cache_schema", "archive_restore"],
    )
    out = cli_completion.completion_candidates(
        ["test", "regression", "--case", "a"],
        4,
        base_dir=Path("."),
    )
    assert out == ["archive_restore"]
