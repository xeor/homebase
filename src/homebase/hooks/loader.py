from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from ..config.hooks import HookConfigError
from ..core.constants import HOMEBASE_DIR_NAME, HOOK_EVENTS
from ..core.models import HookSpec

_BUNDLED_REGISTRY: dict[tuple[str, str, str], ModuleType] = {}


def resolve_hook_module(spec: HookSpec, base_dir: Path) -> ModuleType:
    if spec.source == "bundled":
        return _load_bundled(spec)
    return _load_custom(spec, base_dir)


def _load_bundled(spec: HookSpec) -> ModuleType:
    key = (spec.timing, spec.event, spec.name)
    cached = _BUNDLED_REGISTRY.get(key)
    if cached is not None:
        return cached
    module_path = f"homebase.hooks.bundled.{spec.timing}.{spec.event}.{spec.name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise HookConfigError(
            f"bundled hook not found: {spec.timing}/{spec.event}/{spec.name} ({exc})"
        ) from exc
    if not hasattr(module, "run"):
        raise HookConfigError(
            f"bundled hook {spec.timing}/{spec.event}/{spec.name} missing `run` function"
        )
    _BUNDLED_REGISTRY[key] = module
    return module


def _load_custom(spec: HookSpec, base_dir: Path) -> ModuleType:
    file_path = (
        base_dir / HOMEBASE_DIR_NAME / "hooks" / spec.timing / spec.event / f"{spec.name}.py"
    )
    if not file_path.is_file():
        raise HookConfigError(f"custom hook file not found: {file_path}")
    module_name = f"_homebase_custom_hook_{spec.timing}_{spec.event}_{spec.name}"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    module_spec = importlib.util.spec_from_file_location(module_name, file_path)
    if module_spec is None or module_spec.loader is None:
        raise HookConfigError(f"could not load custom hook: {file_path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = module
    try:
        module_spec.loader.exec_module(module)
    except (SyntaxError, ImportError) as exc:
        sys.modules.pop(module_name, None)
        raise HookConfigError(f"custom hook {file_path} failed to load: {exc}") from exc
    if not hasattr(module, "run"):
        sys.modules.pop(module_name, None)
        raise HookConfigError(f"custom hook {file_path} missing `run` function")
    return module


def verify_all_specs(specs: dict[tuple[str, str], list[HookSpec]], base_dir: Path) -> None:
    for spec_list in specs.values():
        for spec in spec_list:
            if not spec.enabled:
                continue
            resolve_hook_module(spec, base_dir)


def ignored_custom_pre_hook_files(base_dir: Path) -> list[Path]:
    root = base_dir / HOMEBASE_DIR_NAME / "hooks" / "pre"
    out: list[Path] = []
    for event in HOOK_EVENTS:
        event_dir = root / event
        if not event_dir.is_dir():
            continue
        for file_path in sorted(event_dir.glob("*.py")):
            if file_path.is_file():
                out.append(file_path)
    return out
