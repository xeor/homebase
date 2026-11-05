from __future__ import annotations

import pytest
import yaml

from homebase.core import yaml_io


def test_yaml_safe_load_matches_pure_python_loader() -> None:
    text = "a: 1\nb: [x, y]\nc:\n  d: 2026-01-02\n"
    assert yaml_io.yaml_safe_load(text) == yaml.load(text, Loader=yaml.SafeLoader)


def test_yaml_safe_load_rejects_python_tags() -> None:
    with pytest.raises(yaml.YAMLError):
        yaml_io.yaml_safe_load("!!python/object/apply:os.system ['true']")


def test_yaml_safe_load_uses_libyaml_when_available() -> None:
    expected = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader
    assert yaml_io._SAFE_LOADER is expected
