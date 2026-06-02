from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homebase.core.models import PropertyDef
from homebase.metadata import property as property_utils


@dataclass
class PDef:
    key: str
    label: str
    token: str

    def matches(self, _path: Path) -> bool:
        return self.key == "a"


def test_normalize_property_keys_orders_dynamic_before_static() -> None:
    out = property_utils.normalize_property_keys(
        ["x", "a", "b", "x"],
        dynamic_property_defs=[PDef("a", "A", "A")],
        property_defs=[PDef("b", "B", "B")],
    )
    assert out == ["a", "b", "x"]


def test_property_tokens_and_alias_set() -> None:
    defs = [PDef("a", "Alpha", "ALP")]
    tokens = property_utils.property_tokens(
        ["a"],
        all_defs=defs,
        normalize_keys=lambda keys: keys,
    )
    assert tokens == "ALP"
    aliases = property_utils.property_alias_set("a", all_defs=defs)
    assert "alpha" in aliases


def test_detect_properties_supports_template_file_exists(tmp_path: Path) -> None:
    project = tmp_path / "my-proj"
    project.mkdir()
    readme = project / "README.md"
    readme.write_text("x")
    notes_root = tmp_path / "notes"
    notes_root.mkdir()
    note = notes_root / "my-proj.md"
    note.write_text("n")

    defs = [
        PropertyDef(key="rm", label="README", token="RM", file_exists=("README.md",)),
        PropertyDef(
            key="n",
            label="Notes",
            token="N",
            file_exists=(str(notes_root / "{{ NAME_WITH_ARCHIVE_PREFIX }}.md"),),
        ),
    ]
    out = property_utils.detect_properties(
        project,
        property_defs=defs,
        normalize_keys=lambda keys: keys,
        template_context={"NAME_WITH_ARCHIVE_PREFIX": project.name},
    )
    assert out == ["rm", "n"]


def test_render_template_substitutes_known_keys_and_blanks_unknowns() -> None:
    out = property_utils._render_template(
        "/notes/{{NAME}}/{{MISSING}}.md", {"NAME": "proj"}
    )
    assert out == "/notes/proj/.md"


def test_strip_wrapping_quotes() -> None:
    assert property_utils._strip_wrapping_quotes('"path"') == "path"
    assert property_utils._strip_wrapping_quotes("'path'") == "path"
    assert property_utils._strip_wrapping_quotes("path") == "path"
    assert property_utils._strip_wrapping_quotes("") == ""


def test_resolve_check_path_handles_absolute_and_envvar(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DEMO_ROOT", str(tmp_path))
    abs_path = property_utils._resolve_check_path(
        "$DEMO_ROOT/data", root=tmp_path / "ignored", template_context=None
    )
    assert abs_path == Path(tmp_path / "data")

    rel = property_utils._resolve_check_path(
        "sub/file.txt", root=tmp_path, template_context=None
    )
    assert rel == tmp_path / "sub" / "file.txt"


def test_detect_properties_matches_dir_and_path_exists(tmp_path: Path) -> None:
    project = tmp_path / "p"
    (project / "subdir").mkdir(parents=True)
    (project / "any.thing").write_text("x")

    defs = [
        PropertyDef(key="d", label="Dir", token="D", dir_exists=("subdir",)),
        PropertyDef(key="p", label="Path", token="P", path_exists=("any.thing",)),
        PropertyDef(key="missing", label="None", token="?", file_exists=("none.txt",)),
    ]
    out = property_utils.detect_properties(
        project,
        property_defs=defs,
        normalize_keys=lambda keys: keys,
        template_context={},
    )
    assert "d" in out and "p" in out
    assert "missing" not in out


def test_detect_properties_matcher_short_circuits(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()

    class HitDef:
        key = "a"
        label = "A"
        token = "A"
        matcher = object()
        file_exists: tuple[str, ...] = ()
        dir_exists: tuple[str, ...] = ()
        path_exists: tuple[str, ...] = ()

        def matches(self, _path: Path) -> bool:
            return True

    out = property_utils.detect_properties(
        project,
        property_defs=[HitDef()],
        normalize_keys=lambda keys: keys,
    )
    assert out == ["a"]


def test_detect_properties_swallows_matcher_exception(tmp_path: Path) -> None:
    project = tmp_path / "p"
    project.mkdir()

    class BoomDef:
        key = "a"
        label = "A"
        token = "A"
        matcher = object()
        file_exists: tuple[str, ...] = ()
        dir_exists: tuple[str, ...] = ()
        path_exists: tuple[str, ...] = ()

        def matches(self, _path: Path) -> bool:
            raise OSError("nope")

    out = property_utils.detect_properties(
        project,
        property_defs=[BoomDef()],
        normalize_keys=lambda keys: keys,
    )
    assert out == []


def test_all_property_defs_dedupes_by_key() -> None:
    dyn = [PDef("a", "A", "A"), PDef("b", "B", "B")]
    static = [PDef("a", "A2", "A2"), PDef("c", "C", "C")]
    out = property_utils.all_property_defs(dyn, static)
    keys = [d.key for d in out]
    assert keys == ["a", "b", "c"]


def test_property_tokens_text_renders_styled_tokens() -> None:
    class StyledDef:
        key = "a"
        label = "A"
        token = "A"
        color = "red"

    class PlainDef:
        key = "b"
        label = "B"
        token = "B"
        color = ""

    defs = [StyledDef(), PlainDef()]
    text = property_utils.property_tokens_text(
        ["a", "b"],
        all_defs=defs,
        normalize_keys=lambda keys: keys,
    )
    assert "A" in text.plain
    assert "B" in text.plain


def test_property_tokens_text_returns_dash_when_empty() -> None:
    text = property_utils.property_tokens_text(
        [],
        all_defs=[],
        normalize_keys=lambda keys: keys,
    )
    assert text.plain == "-"


def test_property_display_lines_combines_label_and_token() -> None:
    class StyledDef:
        key = "a"
        label = "Alpha"
        token = "ALP"
        color = "magenta"

    class PlainDef:
        key = "b"
        label = "Beta"
        token = "BET"
        color = ""

    lines = property_utils.property_display_lines(
        ["a", "b", "unknown"],
        all_defs=[StyledDef(), PlainDef()],
        normalize_keys=lambda keys: keys,
    )
    assert lines[0] == "[magenta]ALP[/] (Alpha)"
    assert lines[1] == "BET (Beta)"


def test_property_alias_set_returns_only_key_when_def_missing() -> None:
    out = property_utils.property_alias_set("ghost", all_defs=[])
    assert out == {"ghost"}


def test_normalize_property_keys_skips_blank_and_dupes() -> None:
    out = property_utils.normalize_property_keys(
        ["", "  ", "x", "x", "a"],
        dynamic_property_defs=[],
        property_defs=[],
    )
    assert out == sorted(["x", "a"])
