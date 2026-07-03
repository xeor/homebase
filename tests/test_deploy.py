import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "deploy", Path(__file__).resolve().parents[1] / "scripts" / "deploy.py"
)
deploy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(deploy)


def test_extract_bullets_strips_commentary():
    raw = (
        "Looking at the commits, only three substantive ones exist. "
        "Here's the entry body:\n\n"
        "- Config editor and settings improvements\n"
        "- Better visibility of pending favorite removals\n\n"
        "That covers the changes."
    )
    assert deploy.extract_bullets(raw) == (
        "- Config editor and settings improvements\n"
        "- Better visibility of pending favorite removals"
    )


def test_extract_bullets_keeps_indented_sub_bullets():
    raw = "- top level\n  - nested detail\n* star bullet"
    assert deploy.extract_bullets(raw) == "- top level\n  - nested detail\n* star bullet"


def test_extract_bullets_returns_none_without_bullets():
    assert deploy.extract_bullets("no bullets here at all") is None
    assert deploy.extract_bullets("") is None
