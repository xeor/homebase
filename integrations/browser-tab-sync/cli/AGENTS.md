# cli — Agent Instructions

Parent `../AGENTS.md` and repo-root rules apply.

Python CLI + native messaging host. `uv` managed, `src/` layout, strict typing.

## Module map

```
cli.py        Typer app: apply/focus/export/watch/status/doctor + install hooks
config.py     XDG paths, config.toml, log location (no secrets in logs)
models.py     Pydantic models for the profile file (mirrors schema/profile.schema.json)
protocol.py   Pydantic models for native-messaging wire format (mirrors schema/native-messaging.schema.json)
urlnorm.py    URL normalization + matching policy
state.py      SQLite local state (profiles, bindings, tabs)
reconcile.py  Controller core: diff desired vs actual, build actions
nativehost.py Native messaging host loop (stdin/stdout length-prefixed JSON)
installer.py  Write/remove native host manifest, doctor checks
backends/     Pluggable browser backends behind one interface
```

## Rules

- `models.py` / `protocol.py` are the Python mirror of `schema/*.json`. If the
  schema changes, change both sides in the same commit.
- Native messaging frames are `uint32` little-endian length prefix + UTF-8 JSON
  on stdin/stdout. The host must write nothing else to stdout — logs go to file.
- Catch concrete exceptions only (`json.JSONDecodeError`, `sqlite3.Error`,
  `pydantic.ValidationError`, `OSError`). No bare `except`.
- File writes are atomic: temp + fsync + rename, then history backup.

## Commands

```
uv sync
uv run homebase-bts --help
uv run pytest
uv run ruff check . && uv run ruff format .
uv run mypy
```
