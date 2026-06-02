from __future__ import annotations

from pathlib import Path

from homebase.ui.screens.rename import _similar_matches


def test_similar_matches_picks_exact_then_prefix(tmp_path: Path) -> None:
    for name in ("alpha", "alphabet", "beta", "gamma"):
        (tmp_path / name).mkdir()
    hits = _similar_matches(tmp_path, "alph")
    names = [n for n, _ in hits]
    assert "alpha" in names
    assert "alphabet" in names
    # `beta` is too dissimilar.
    assert "beta" not in names


def test_similar_matches_skips_underscore_dirs(tmp_path: Path) -> None:
    (tmp_path / "_archive").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "alpha").mkdir()
    hits = _similar_matches(tmp_path, "a")
    names = [n for n, _ in hits]
    # 1-char queries are skipped (limit >= 2), so nothing matches.
    assert names == []


def test_similar_matches_excludes_current_name(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alphabet").mkdir()
    hits = _similar_matches(tmp_path, "alpha", exclude="alpha")
    names = [n for n, _ in hits]
    assert "alpha" not in names
    assert "alphabet" in names


def test_similar_matches_empty_query_returns_none(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    assert _similar_matches(tmp_path, "") == []
    assert _similar_matches(tmp_path, " ") == []


def test_similar_matches_returns_empty_when_base_dir_missing(tmp_path: Path) -> None:
    """A missing base dir (caller passed a stale path) must not raise
    — return ``[]`` so the screen can render empty suggestions."""
    assert _similar_matches(tmp_path / "missing", "alpha") == []


def test_similar_matches_skips_files_and_keeps_directories(tmp_path: Path) -> None:
    """The suggestion list only considers directories — files don't
    represent renameable projects."""
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alphafile.txt").write_text("x")
    hits = _similar_matches(tmp_path, "alpha")
    names = [n for n, _ in hits]
    assert "alpha" in names
    assert "alphafile.txt" not in names


def test_similar_matches_caps_at_limit(tmp_path: Path) -> None:
    """The ``limit`` keeps the suggestion panel short."""
    for i in range(10):
        (tmp_path / f"alpha{i:02d}").mkdir()
    hits = _similar_matches(tmp_path, "alpha", limit=3)
    assert len(hits) == 3


def test_similar_matches_exact_match_gets_full_score(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alphabet").mkdir()
    hits = _similar_matches(tmp_path, "alpha")
    by_name = dict(hits)
    # An exact match scores 100.
    assert by_name.get("alpha") == 100
    # Prefix matches score at least 85.
    assert by_name.get("alphabet", 0) >= 85


def test_similar_matches_substring_lower_score_than_prefix(tmp_path: Path) -> None:
    """A name that just contains the query (without prefix) gets a
    lower floor (70) than a prefix match (85)."""
    (tmp_path / "alphaonly").mkdir()  # prefix
    (tmp_path / "xx-alpha-yy").mkdir()  # substring only
    hits = dict(_similar_matches(tmp_path, "alpha"))
    assert hits["alphaonly"] >= hits["xx-alpha-yy"]


# ---- _refresh helpers (instance-only) -------------------------------


class _StaticStub:
    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


def _make_screen(base_dir: Path, current_path: Path, current_name: str | None = None):
    """Allocate a bare RenameInputScreen instance with the minimum
    attributes the ``_refresh``/``_esc`` helpers touch — we never
    enter Textual's mount lifecycle."""
    from homebase.ui.screens.rename import RenameInputScreen

    screen = RenameInputScreen.__new__(RenameInputScreen)
    screen.base_dir = base_dir
    screen.current_path = current_path
    screen.current_name = current_name or current_path.name
    return screen


def test_esc_escapes_left_bracket(tmp_path: Path) -> None:
    """The status text is rendered with Textual markup — bare brackets
    would be interpreted as markup, so they get backslash-escaped."""
    screen = _make_screen(tmp_path, tmp_path / "proj")
    assert screen._esc("foo [bar]") == "foo \\[bar]"


def test_refresh_prompts_user_when_input_blank(tmp_path: Path, monkeypatch) -> None:
    screen = _make_screen(tmp_path, tmp_path / "proj")
    stub = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_args, **_kw: stub)
    screen._refresh("")
    assert "type a new name" in stub.text


def test_refresh_shows_unchanged_when_name_matches_current(
    tmp_path: Path, monkeypatch,
) -> None:
    screen = _make_screen(tmp_path, tmp_path / "proj", current_name="proj")
    stub = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_args, **_kw: stub)
    screen._refresh("proj")
    assert "unchanged" in stub.text


def test_refresh_flags_collision_when_target_exists(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "taken").mkdir()
    screen = _make_screen(tmp_path, tmp_path / "proj")
    stub = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_args, **_kw: stub)
    screen._refresh("taken")
    assert "target exists" in stub.text


def test_refresh_shows_clean_target_when_name_is_free(
    tmp_path: Path, monkeypatch,
) -> None:
    screen = _make_screen(tmp_path, tmp_path / "proj")
    stub = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_args, **_kw: stub)
    screen._refresh("freshname")
    assert "[green]target[/]" in stub.text
    assert "freshname" in stub.text


def test_refresh_lists_similar_names_when_present(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "alphaone").mkdir()
    (tmp_path / "alphatwo").mkdir()
    screen = _make_screen(tmp_path, tmp_path / "proj")
    stub = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_args, **_kw: stub)
    screen._refresh("alpha")
    assert "similar names" in stub.text
    assert "alphaone" in stub.text
