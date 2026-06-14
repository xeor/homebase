# Agent Instructions — `integrations`

This directory contains optional standalone companion projects for
Homebase. They live in this repo for context, not because they are part
of the main `homebase` package.

## Boundary

- Do not use, inspect, test, or modify integrations during ordinary
  Homebase work unless the user explicitly asks for integration work.
- Keep integrations optional. `src/homebase/` must not import from this
  directory or require integration packages at runtime.
- Keep integration dependencies in the integration-local manifests
  (`package.json`, `pyproject.toml`, lockfiles). Do not add them to the
  root `pyproject.toml` or root `uv.lock`.
- Keep build, lint, test, and release commands project-local. The root
  QA pipeline covers Homebase only.
- Mise may show inherited root tasks inside this monorepo. Do not rely
  on them for integration work; each integration must keep complete
  local manifests and commands.
- When changing an integration, use that integration's own docs,
  manifest, lockfile, and nested `AGENTS.md` rules.

## Projects

- `raycast/`: Raycast extension for finding/opening Homebase projects
  by shelling out to `b`.
- `browser-tab-sync/`: file-as-desired-state controller for browser tab
  groups, with a Python CLI/native host and WXT extension.
