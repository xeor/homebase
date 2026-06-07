from pathlib import Path

import pytest
from pydantic import ValidationError

from homebase_bts.models import Profile

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "vacation.json"


def test_example_profile_parses():
    p = Profile.model_validate_json(EXAMPLE.read_text())
    assert p.id == "vacation"
    assert p.schema_version == 1
    assert [t.url for t in p.tabs] == [
        "https://maps.google.com/",
        "https://www.google.com/travel/flights",
    ]


def test_defaults_applied():
    p = Profile.model_validate({"schema": 1, "id": "x", "tabs": [{"url": "https://a.b"}]})
    assert p.sync.mode.value == "two-way"
    assert p.sync.delete_missing is False
    assert p.browser.strategy.value == "tab-group"


def test_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Profile.model_validate({"schema": 1, "id": "x", "tabs": [], "bogus": 1})


def test_rejects_bad_id():
    with pytest.raises(ValidationError):
        Profile.model_validate({"schema": 1, "id": "Bad ID", "tabs": []})


@pytest.mark.parametrize("url", ["notaurl", "ftp://example.com", "file:///tmp/x", "https:///x"])
def test_rejects_bad_tab_url(url: str):
    with pytest.raises(ValidationError):
        Profile.model_validate({"schema": 1, "id": "x", "tabs": [{"url": url}]})
