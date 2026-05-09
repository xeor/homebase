from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "homebase"


ALLOWED_IMPORTS: dict[str, set[str]] = {
    "core": {"core"},
    "config": {"core", "config"},
    "cache": {"core", "config", "cache"},
    "metadata": {"core", "config", "metadata"},
    "archive": {"core", "config", "archive"},
    "tmux": {"core", "config", "tmux"},
    "filter": {"core", "config", "filter"},
    "notes": {"core", "notes"},
    "workspace": {
        "core",
        "config",
        "cache",
        "metadata",
        "archive",
        "filter",
        "workspace",
    },
    "commands": {
        "workspace",
        "archive",
        "cache",
        "metadata",
        "tmux",
        "core",
        "config",
        "commands",
    },
    "ui": {
        "core",
        "config",
        "cache",
        "metadata",
        "archive",
        "filter",
        "notes",
        "workspace",
        "commands",
        "tmux",
        "ui",
    },
    "cli": {
        "core",
        "config",
        "cache",
        "metadata",
        "archive",
        "filter",
        "notes",
        "workspace",
        "commands",
        "tmux",
        "ui",
        "cli",
    },
}

KNOWN_LAYERING_EXCEPTIONS = {
    "src/homebase/cache/api.py:16 imports homebase.metadata.api",
    "src/homebase/cache/api.py:17 imports homebase.workspace.projects",
    "src/homebase/cli/__init__.py:5 imports homebase.entry",
    "src/homebase/config/prefs.py:34 imports homebase.filter",
    "src/homebase/metadata/api.py:28 imports homebase.filter",
    "src/homebase/metadata/api.py:29 imports homebase.workspace",
    "src/homebase/metadata/api.py:10 imports homebase.archive",
    "src/homebase/tmux/flow.py:8 imports homebase.commands",
    "src/homebase/ui/__init__.py:3 imports homebase.app",
    "src/homebase/ui/__init__.py:4 imports homebase.context",
    "src/homebase/workspace/benchmark.py:23 imports homebase.commands.archive",
    "src/homebase/workspace/projects.py:176 imports homebase.tmux.flow",
    "src/homebase/workspace/projects.py:177 imports homebase.ui",
    "src/homebase/workspace/projects.py:243 imports homebase.tmux.flow",
    "src/homebase/workspace/regression.py:21 imports homebase.commands.archive",
}


def _module_parts_for_path(path: Path) -> list[str]:
    rel = path.relative_to(SRC_ROOT)
    parts = ["homebase", *rel.with_suffix("").parts]
    if parts[-1] == "__init__":
        return parts[:-1]
    return parts


def _resolve_from_import_target(parts: list[str], node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        base = []
    else:
        package_parts = parts[:-1]
        up = node.level - 1
        if up > len(package_parts):
            return None
        base = package_parts[: len(package_parts) - up]
    mod = node.module.split(".") if node.module else []
    target = [*base, *mod]
    if not target:
        return None
    return ".".join(target)


def test_layering_imports_follow_rules() -> None:
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        module_parts = _module_parts_for_path(path)
        if len(module_parts) < 2:
            continue
        source_layer = module_parts[1]
        if source_layer not in ALLOWED_IMPORTS:
            continue
        allowed = ALLOWED_IMPORTS[source_layer]

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            target_module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name == "homebase" or name.startswith("homebase."):
                        parts = name.split(".")
                        if len(parts) >= 2:
                            target_layer = parts[1]
                            if target_layer not in allowed:
                                violations.append(
                                    f"{path.relative_to(ROOT)}:{node.lineno} imports {name}"
                                )
            elif isinstance(node, ast.ImportFrom):
                target_module = _resolve_from_import_target(module_parts, node)
                if target_module is None:
                    continue
                if target_module == "homebase" or target_module.startswith("homebase."):
                    parts = target_module.split(".")
                    if len(parts) >= 2:
                        target_layer = parts[1]
                        if target_layer not in allowed:
                            violations.append(
                                f"{path.relative_to(ROOT)}:{node.lineno} imports {target_module}"
                            )

    unexpected = sorted(v for v in violations if v not in KNOWN_LAYERING_EXCEPTIONS)
    assert not unexpected, "Layering violations:\n" + "\n".join(unexpected)
