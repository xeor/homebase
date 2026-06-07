# homebase-bts

File-as-desired-state controller for browser tab groups.

The profile file is desired state. The browser is actual state.
`homebase-bts` reconciles the two.

First target: Chrome on macOS. Vivaldi/Chromium-family browsers are best-effort.
More browsers and OSes are later work.

## Shape

```text
schema/      Profile + native-messaging JSON Schemas
cli/         Python CLI + native messaging host
extension/   MV3 browser extension
examples/    Example profile files
```

The CLI owns validation, diff/merge policy, state, sync targets, and file IO.
The extension only queries/mutates browser tabs and streams snapshots.

## Profile

```json
{
  "schema": 1,
  "id": "vacation",
  "title": "Vacation",
  "browser": { "preferred": "chrome", "strategy": "tab-group" },
  "group": { "title": "Vacation", "color": "cyan", "focus": "first" },
  "tabs": [
    { "url": "https://maps.google.com/" },
    { "url": "https://www.google.com/travel/flights" }
  ],
  "sync": { "mode": "two-way", "delete_missing": false, "adopt_existing": true }
}
```

See [`examples/vacation.json`](examples/vacation.json). When a command gets a
folder instead of a file, it looks for `.base-bts.yaml` in that folder. With no
profile argument, commands default to `.`.

## Commands

```bash
homebase-bts apply
homebase-bts apply --local
homebase-bts apply vacation.json
homebase-bts focus vacation.json
homebase-bts debug vacation.json
homebase-bts doctor
```

Modes:

- default: real browser via extension + native messaging host
- `--local`: file-backed simulator at `~/.config/homebase-bts/sim-browser.json`

Current MVP:

- `apply` works against the native backend
- `focus` works against native backend
- two-way sync is enabled by `apply` for `sync.mode: "two-way"`
- `status` shows the desired vs actual diff
- `export` snapshots actual browser state back into the profile file
- `debug` streams snapshots without writing files

Tabs are not deleted from the file unless `sync.delete_missing` is explicitly
`true`.

## Docs

- [Architecture](ARCHITECTURE.md)
- [Development](DEVELOP.md)
- [Install](INSTALL.md)
- [Release](RELEASE.md)
- [Security](SECURITY.md)
- [Support Matrix](SUPPORT.md)
