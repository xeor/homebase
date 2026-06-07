# Develop

Use `mise`. It pins Python, Node and uv, and orders dependencies.

```bash
mise install
mise run setup
mise tasks ls
```

## Repository

```text
schema/      Source of truth for profile and native-message JSON Schemas
cli/         Python CLI, native messaging host, state, reconcile logic
extension/   WXT MV3 extension, browser API adapter, snapshots
examples/    Example profiles
```

Keep protocol/profile mirrors in sync:

```text
schema/profile.schema.json
schema/native-messaging.schema.json
cli/src/homebase_bts/models.py
cli/src/homebase_bts/protocol.py
extension/src/protocol.ts
```

Business logic belongs in `cli/`. The extension owns no file IO and no conflict
policy.

## Common commands

```bash
mise run setup
mise run dev
mise run build
mise run lint
mise run test
```

Per side:

```bash
mise run cli:sync
mise run cli:run -- --help
mise run cli:run -- apply examples/vacation.json
mise run cli:test
mise run cli:test:watch
mise run cli:fmt
mise run cli:lint

mise run ext:install
mise run ext:dev
mise run ext:compile
mise run ext:build
```

Direct equivalents:

```bash
cd cli && uv run homebase-bts --help
cd cli && uv run pytest -x --tb=short
cd cli && uv run ruff check . && uv run ruff format --check . && uv run mypy

cd extension && npm run compile
cd extension && npm run build
```

## Development browser

```bash
mise run ext:dev
```

This launches WXT with a persistent dev profile:

```text
.dev-profile/
```

It also runs `host:install-dev`, which writes:

```text
.dev-profile/NativeMessagingHosts/nu.boa.homebase_bts.json
```

The dev install does not touch daily Chrome/Vivaldi profiles. Override the
browser binary when needed:

```bash
HBTS_DEV_BROWSER_BIN="/Applications/Chromium.app/Contents/MacOS/Chromium" mise run ext:dev
```

If the native socket is missing, restart `mise run ext:dev` after the manifest
has been written.

Manual dev host registration:

```bash
mise run cli:run -- native-host install-dev \
  --extension-dir "$PWD/extension/.output/chrome-mv3-dev" \
  --manifest-dir "$PWD/.dev-profile/NativeMessagingHosts"
```

## Running against browser

Start the dev browser:

```bash
mise run ext:dev
```

In another shell:

```bash
mise run cli:run -- doctor
mise run cli:run -- apply examples/vacation.json
mise run cli:run -- focus examples/vacation.json
mise run cli:run -- debug examples/vacation.json
```

`debug` is read-only. It prints snapshots until interrupted.

## Local simulator

Use the local backend for reconcile work without a browser:

```bash
mise run cli:run -- apply examples/vacation.json --local
mise run cli:run -- apply examples/vacation.json --local
```

The second run should be idempotent.

Simulator state:

```text
~/.config/homebase-bts/sim-browser.json
```

## Native messaging

Host name:

```text
nu.boa.homebase_bts
```

Keep it synchronized:

```text
cli/src/homebase_bts/installer.py
extension/wxt.config.ts
```

Runtime topology:

```text
homebase-bts CLI
  -> Unix socket
  -> browser-owned Python native host
  -> Chrome native messaging stdio
  -> MV3 service worker
  -> browser tabs/tabGroups APIs
```

The native host is spawned by the browser when the extension connects. It is not
a user-managed daemon.

Runtime socket path resolution:

```text
HBTS_RUNTIME_DIR/homebase-bts/host.sock
$XDG_RUNTIME_DIR/homebase-bts/host.sock
<per-user temp>/homebase-bts-<uid>/host.sock
```

Persistent state:

```text
~/.config/homebase-bts/sync.json
~/.config/homebase-bts/logs/
```

## Manual extension load

```bash
mise run ext:build
```

Chrome:

```text
chrome://extensions
Developer mode
Load unpacked -> extension/.output/chrome-mv3/
```

Then register the extension ID:

```bash
homebase-bts native-host install --browser chrome --extension-id <id>
```

Restart the browser before checking the socket:

```bash
homebase-bts doctor
```

## Testing focus

CLI:

```bash
mise run cli:test
mise run cli:lint
```

Extension:

```bash
mise run ext:compile
```

All:

```bash
mise run lint
mise run test
```

For schema changes, test both Python and TypeScript mirrors.

## Build artifacts

Extension:

```bash
mise run ext:build
cd extension && npm run zip
```

Python:

```bash
cd cli
uv build
```

See [RELEASE.md](RELEASE.md) for release packaging.

## Troubleshooting

Host executable missing:

```bash
mise run cli:run -- doctor
```

Browser socket missing:

```bash
mise run ext:dev
mise run cli:run -- doctor
```

Wrong native host origin:

```bash
homebase-bts native-host install --browser chrome --extension-id <current-id>
```

Unpacked extension IDs can change when the extension output path changes.
