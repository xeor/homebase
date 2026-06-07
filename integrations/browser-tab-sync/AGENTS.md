# homebase-bts — Agent Instructions

Parent `../AGENTS.md` applies. This file adds project-specific rules.

## What this is

File-as-desired-state controller for browser tab groups. The JSON profile is
desired state, the browser is actual state, `homebase-bts` reconciles them.
See `IDEA.md` for the full design.

## Layout

```
schema/      Single source of truth: profile + native-messaging JSON Schemas
cli/         Python CLI + native messaging host (uv, src layout)
extension/   MV3 browser extension (WXT + TypeScript)
examples/    Sample profile files
```

Both `cli/` and `extension/` have their own `AGENTS.md`. Keep the wire protocol
and profile format in `schema/` authoritative — mirror, never fork, those types
in `cli/src/homebase_bts/protocol.py` and `extension/src/protocol.ts`.

## Architecture rules

- Business logic (diff/merge/policy/state) lives in the CLI. The extension only
  queries/mutates the browser and streams snapshots — it owns no file IO and no
  conflict policy.
- Never trust `group_id`/`window_id` as permanent identity (Chrome reuses them
  per session). Identity resolution order: local state → group title → most
  matching tabs.
- Backends are pluggable behind one interface (`backends/base.py`). Chrome via
  extension is primary; `macos`/`cdp` are later additions, not special cases.
- Default to non-destructive: never delete tabs from a file unless
  `sync.delete_missing` is explicitly true.

## Dev commands

`mise` (see `mise.toml`) is the task runner — it pins python/node/uv and orders
deps. Prefer it over raw commands.

```
mise run setup      # install CLI + extension deps
mise run dev        # extension HMR in Chrome
mise run test       # all tests
mise run lint       # ruff + mypy + tsc
mise run build      # production builds
mise tasks ls       # full list (cli:*, ext:* for per-side tasks)
```

Underlying tools still work directly (`cd cli && uv run ...`,
`cd extension && npm run ...`); `mise run cli:fmt` auto-fixes the CLI.
