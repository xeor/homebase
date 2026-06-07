from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src" / "homebase"
INTEGRATIONS_ROOT = ROOT / "integrations"


ALLOWED_IMPORTS: dict[str, set[str]] = {
    "core": {"core"},
    "config": {"core", "config"},
    "cache": {"core", "config", "cache"},
    "metadata": {"core", "config", "metadata"},
    "hooks": {"core", "config", "metadata", "hooks"},
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
        "hooks",
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
        "hooks",
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
        "hooks",
        "ui",
        "cli",
    },
}

KNOWN_LAYERING_EXCEPTIONS = {
    "src/homebase/cli/__init__.py:5 imports homebase.entry",
    "src/homebase/hooks/bundled/post/_tag_symlink_sync_common.py imports homebase.workspace.tag_sync",
    "src/homebase/tmux/flow.py imports homebase.commands",
    "src/homebase/ui/__init__.py imports homebase.app",
    "src/homebase/ui/__init__.py imports homebase.context",
    "src/homebase/workspace/projects.py imports homebase.tmux.flow",
    "src/homebase/workspace/new/cmd.py imports homebase.tmux.flow",
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

    # Allow exact "path:line imports target" matches as well as the
    # line-number-agnostic "path imports target" form, so the exception
    # list doesn't churn when unrelated code shifts line numbers.
    def _stripped(violation: str) -> str:
        path_part, _, rest = violation.partition(" imports ")
        path_no_line = path_part.rsplit(":", 1)[0]
        return f"{path_no_line} imports {rest}"

    known_loose = {_stripped(v) for v in KNOWN_LAYERING_EXCEPTIONS}
    unexpected = sorted(
        v for v in violations
        if v not in KNOWN_LAYERING_EXCEPTIONS and _stripped(v) not in known_loose
    )
    assert not unexpected, "Layering violations:\n" + "\n".join(unexpected)


def test_main_project_does_not_depend_on_integrations() -> None:
    offenders: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "integrations" in text or "homebase_bts" in text:
            offenders.append(str(path.relative_to(ROOT)))

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"].get("dependencies", [])
    dev_dependencies = pyproject["dependency-groups"].get("dev", [])
    forbidden_deps = {"homebase-bts", "homebase_bts", "@raycast/api", "@raycast/eslint-config"}
    for dep in [*dependencies, *dev_dependencies]:
        dep_name = dep.split("[", 1)[0].split(">=", 1)[0].split("==", 1)[0]
        if dep_name in forbidden_deps:
            offenders.append(f"pyproject.toml dependency {dep}")

    wheel_packages = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    if any(str(package).startswith("integrations") for package in wheel_packages):
        offenders.append("pyproject.toml wheel packages include integrations")

    sdist_include = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    if any(str(path).startswith("integrations") for path in sdist_include):
        offenders.append("pyproject.toml sdist includes integrations")
    sdist_exclude = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"].get("exclude", [])
    if "integrations" not in sdist_exclude:
        offenders.append("pyproject.toml sdist does not exclude integrations")

    assert INTEGRATIONS_ROOT.is_dir()
    assert not offenders, "Main project depends on integrations:\n" + "\n".join(offenders)
