from __future__ import annotations

import pytest

from homebase.config.hooks import HookConfigError
from homebase.core.models import HookSpec
from homebase.hooks.loader import resolve_hook_module, verify_all_specs


def _spec(*, name: str, source: str = "custom", event: str = "rename", timing: str = "post") -> HookSpec:
    return HookSpec(
        timing=timing,
        event=event,
        name=name,
        source=source,
        enabled=True,
        views=(),
        config={},
        slow_warn_s=30.0,
    )


def test_resolve_hook_module_loads_custom_with_run(tmp_path) -> None:
    hook_path = tmp_path / ".homebase" / "hooks" / "post" / "rename" / "foo.py"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("def run(ctx):\n    return None\n", encoding="utf-8")
    module = resolve_hook_module(_spec(name="foo"), tmp_path)
    assert callable(getattr(module, "run", None))


def test_resolve_hook_module_custom_missing_file_raises(tmp_path) -> None:
    with pytest.raises(HookConfigError, match="custom hook file not found"):
        resolve_hook_module(_spec(name="missing"), tmp_path)


def test_resolve_hook_module_custom_syntax_error_raises(tmp_path) -> None:
    hook_path = tmp_path / ".homebase" / "hooks" / "post" / "rename" / "broken.py"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("def run(ctx):\n    if True print('x')\n", encoding="utf-8")
    with pytest.raises(HookConfigError, match="failed to load"):
        resolve_hook_module(_spec(name="broken"), tmp_path)


def test_resolve_hook_module_custom_without_run_raises(tmp_path) -> None:
    hook_path = tmp_path / ".homebase" / "hooks" / "post" / "rename" / "norun.py"
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(HookConfigError, match="missing `run` function"):
        resolve_hook_module(_spec(name="norun"), tmp_path)


def test_resolve_hook_module_missing_bundled_raises(tmp_path) -> None:
    with pytest.raises(HookConfigError, match="bundled hook not found"):
        resolve_hook_module(_spec(name="does_not_exist", source="bundled"), tmp_path)


def test_verify_all_specs_raises_on_first_bad_entry(tmp_path) -> None:
    specs = {
        ("post", "rename"): [_spec(name="bad_missing")],
        ("post", "tag_change"): [_spec(name="other", event="tag_change")],
    }
    with pytest.raises(HookConfigError, match="custom hook file not found"):
        verify_all_specs(specs, tmp_path)
