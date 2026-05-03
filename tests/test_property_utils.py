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
