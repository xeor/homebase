from __future__ import annotations

import pytest

from homebase.core import prompting as prompting


def test_prompt_yes_no_accepts_yes() -> None:
    out = prompting.prompt_yes_no(
        "q?",
        default=False,
        read=lambda *_args, **_kwargs: "y",
    )
    assert out is True


def test_confirm_raises_on_cancel() -> None:
    with pytest.raises(KeyboardInterrupt):
        prompting.confirm(lambda *_args, **_kwargs: None)
