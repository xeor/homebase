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


def _seed_cache_projects(
    base: Path, entries: list[tuple[str, list[str]]],
) -> None:
    from homebase.cache.api import cache_store_rows
    from homebase.workspace.projects import project_row

    rows = []
    for name, tags in entries:
        project = base / name
        project.mkdir()
        (project / ".base.yaml").write_text(
            "tags: [" + ", ".join(tags) + "]\n", encoding="utf-8",
        )
        rows.append(project_row(project, archived=False))
    cache_store_rows(base, rows, [])


def test_completion_cd_filter_token_narrows_by_tag(tmp_path: Path) -> None:
    """``b cd '#infra' <tab>`` must read the cache, apply the filter
    expression to the cached rows, and return only matching project
    names. Without this, the user can't combine filter syntax with
    tab completion."""
    _seed_cache_projects(tmp_path, [
        ("alpha-infra", ["infra"]),
        ("beta-app", ["app"]),
        ("gamma-infra", ["infra", "wip"]),
    ])
    out = cli_completion.completion_candidates(
        ["cd", "#infra", ""], 3, base_dir=tmp_path,
    )
    assert out == ["alpha-infra", "gamma-infra"]


def test_completion_cd_filter_then_name_prefix(tmp_path: Path) -> None:
    """Filter tokens *plus* a name-prefix on the current token must
    intersect: only names that both match the filter and start with
    the prefix come back."""
    _seed_cache_projects(tmp_path, [
        ("alpha-infra", ["infra"]),
        ("gamma-infra", ["infra"]),
        ("alpha-app", ["app"]),
    ])
    out = cli_completion.completion_candidates(
        ["cd", "#infra", "alp"], 3, base_dir=tmp_path,
    )
    assert out == ["alpha-infra"]


def test_completion_cd_resolves_named_filter_from_prefs(
    tmp_path: Path,
) -> None:
    """``@code`` and other named filters live in user prefs, not in
    the built-in NAMED_FILTERS dict. Completion runs in a fresh
    process whose NAMED_FILTERS starts empty, so the cd helper must
    load prefs before compiling — otherwise @-tokens silently match
    nothing."""
    from homebase.config.prefs import save_filter_query

    _seed_cache_projects(tmp_path, [
        ("alpha-code", ["code"]),
        ("beta-code", ["code"]),
        ("gamma-app", ["app"]),
    ])
    save_filter_query(tmp_path, "#code", name="code")
    out = cli_completion.completion_candidates(
        ["cd", "@code", ""], 3, base_dir=tmp_path,
    )
    assert out == ["alpha-code", "beta-code"]


def test_completion_ls_offers_all_column_flags(tmp_path: Path) -> None:
    """``b ls --<tab>`` must surface every column flag plus the
    long/git/archived knobs. The dash-prefix filter inside
    ``completion_candidates`` narrows to options that actually start
    with ``--``."""
    out = cli_completion.completion_candidates(
        ["ls", "--"], 2, base_dir=tmp_path,
    )
    for flag in (
        "--long", "--git", "--archived",
        "--created", "--active", "--wip", "--worktree-of",
        "--src", "--path", "--description", "--props",
    ):
        assert flag in out, f"missing {flag!r}: {out!r}"


def test_completion_top_level_includes_json(tmp_path: Path) -> None:
    """``b <tab>`` must surface the new ``json`` subcommand
    alongside ``ls`` — otherwise scripted consumers can't discover it
    via tab completion."""
    out = cli_completion.completion_candidates([""], 1, base_dir=tmp_path)
    assert "json" in out and "ls" in out


def test_completion_json_offers_archived_flags(tmp_path: Path) -> None:
    """``b json --<tab>`` lists both archived-set switches."""
    out = cli_completion.completion_candidates(
        ["json", "--"], 2, base_dir=tmp_path,
    )
    assert out == ["--archived", "--archived-only"]


def test_completion_ls_prefix_filters_partial_flag(tmp_path: Path) -> None:
    """``b ls --wo<tab>`` narrows to ``--worktree-of`` (and nothing
    else)."""
    out = cli_completion.completion_candidates(
        ["ls", "--wo"], 2, base_dir=tmp_path,
    )
    assert out == ["--worktree-of"]


def test_completion_cd_filter_falls_back_to_fs_when_cache_cold(
    tmp_path: Path,
) -> None:
    """Cold cache (never warmed) must not break completion — fall
    back to the unfiltered filesystem listing so the user still gets
    suggestions, even though the filter can't be applied."""
    (tmp_path / "myproj").mkdir()
    (tmp_path / "other").mkdir()
    out = cli_completion.completion_candidates(
        ["cd", "#infra", ""], 3, base_dir=tmp_path,
    )
    assert out == ["myproj", "other"]


def test_completion_fix_lists_dirs_and_flags(tmp_path: Path) -> None:
    (tmp_path / "proj").mkdir()
    (tmp_path / "other").mkdir()
    (tmp_path / "notes.txt").write_text("ignore")
    out = cli_completion.completion_candidates(
        ["fix", ""], 2, base_dir=tmp_path, cwd=tmp_path,
    )
    assert "proj/" in out
    assert "other/" in out
    assert "--yes" in out
    assert "--marker" in out
    assert "--no-marker" in out
    assert "--archive-entry" in out
    assert "--no-archive-entry" in out


def test_completion_fix_dir_prefix_filters(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alpine").mkdir()
    (tmp_path / "beta").mkdir()
    out = cli_completion.completion_candidates(
        ["fix", "alp"], 2, base_dir=tmp_path, cwd=tmp_path,
    )
    assert out == ["alpha/", "alpine/"]


def test_completion_fix_nested_dir(tmp_path: Path) -> None:
    inner = tmp_path / "outer" / "child"
    inner.mkdir(parents=True)
    out = cli_completion.completion_candidates(
        ["fix", "outer/"], 2, base_dir=tmp_path, cwd=tmp_path,
    )
    assert "outer/child/" in out


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


def test_completion_includes_example_top_level() -> None:
    out = cli_completion.completion_candidates([""], 1, base_dir=Path("."))
    assert "example" in out


def test_completion_example_lists_generate_subcommand() -> None:
    out = cli_completion.completion_candidates(["example", ""], 2, base_dir=Path("."))
    assert out == ["generate"]


def test_completion_example_generate_lists_flags() -> None:
    out = cli_completion.completion_candidates(
        ["example", "generate", ""], 3, base_dir=Path("."),
    )
    assert out == ["--count", "--path", "--seed"]


def test_completion_example_path_completes_dirs(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "stray.txt").write_text("x")
    out = cli_completion.completion_candidates(
        ["example", "generate", "--path", ""],
        4,
        base_dir=Path("."),
        cwd=tmp_path,
    )
    assert "alpha/" in out
    assert "beta/" in out
    assert not any(c.endswith("stray.txt") for c in out)


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
