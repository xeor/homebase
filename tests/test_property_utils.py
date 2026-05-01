from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
