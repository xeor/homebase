# Release

Release artifacts:

- Python wheel/sdist from `cli/`
- Chrome MV3 extension zip from `extension/`
- Native messaging manifest installed by `homebase-bts native-host install`

Current version source:

- CLI: `cli/pyproject.toml` (`[project].version`)
- Extension: `extension/package.json` (`version`)

Keep both versions equal.

## Preconditions

```bash
mise install
mise run setup
mise run lint
mise run test
mise run build
```

`mise run build` currently builds the extension. Build the Python package
explicitly until a release task exists:

```bash
cd cli
uv build
```

Expected outputs:

```text
cli/dist/homebase_bts-<version>-py3-none-any.whl
cli/dist/homebase_bts-<version>.tar.gz
extension/.output/chrome-mv3/
extension/.output/homebase-bts-extension-<version>-chrome.zip
```

If the extension zip is missing:

```bash
cd extension
npm run zip
```

## Version bump

```bash
# edit both files to the same version
$EDITOR cli/pyproject.toml extension/package.json

mise run lint
mise run test
mise run build
cd cli && uv build
cd ../extension && npm run zip
```

Do not change schema without updating all mirrors in the same release:

- `schema/profile.schema.json`
- `schema/native-messaging.schema.json`
- `cli/src/homebase_bts/models.py`
- `cli/src/homebase_bts/protocol.py`
- `extension/src/protocol.ts`

## Python package deploy

The package exposes two scripts:

```text
homebase-bts
homebase-bts-host
```

The native messaging manifest points to `homebase-bts-host`. Install the Python
package before registering the native host, otherwise the browser manifest can
point at a missing executable.

Local artifact install:

```bash
python -m pip install --user cli/dist/homebase_bts-<version>-py3-none-any.whl
homebase-bts version
which homebase-bts-host
```

Recommended user install once releases exist:

```bash
pipx install homebase-bts
homebase-bts version
which homebase-bts-host
```

PyPI publish, when enabled:

```bash
cd cli
uv publish
```

Use TestPyPI first for the first public package release:

```bash
cd cli
uv publish --publish-url https://test.pypi.org/legacy/
```

## Extension build and registration

Development registration is self-contained:

```bash
mise run ext:dev
```

This does three things:

- builds/serves the WXT dev extension
- computes the unpacked dev extension ID from `extension/.output/chrome-mv3-dev`
- writes the native host manifest to `.dev-profile/NativeMessagingHosts/`

Manual dev registration:

```bash
mise run ext:build
mise run cli:run -- native-host install-dev \
  --extension-dir "$PWD/extension/.output/chrome-mv3-dev" \
  --manifest-dir "$PWD/.dev-profile/NativeMessagingHosts"
```

Machine/browser registration for a real browser:

```bash
homebase-bts native-host install \
  --browser chrome \
  --extension-id <chrome-extension-id>
```

Supported `--browser` values:

```text
chrome
chrome-beta
chrome-canary
chrome-for-testing
chromium
vivaldi
brave
edge
```

macOS manifest locations are under:

```text
~/Library/Application Support/<browser>/NativeMessagingHosts/nu.boa.homebase_bts.json
```

The manifest format:

```json
{
  "name": "nu.boa.homebase_bts",
  "description": "homebase-bts native messaging host",
  "path": "/absolute/path/to/homebase-bts-host",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://<extension-id>/"]
}
```

The host name must stay in sync:

- `cli/src/homebase_bts/installer.py` (`HOST_NAME`)
- `extension/wxt.config.ts` (`NATIVE_HOST`)

## Chrome Web Store

Not wired yet. When publishing through Chrome Web Store:

1. Build and zip:

   ```bash
   cd extension
   npm run build
   npm run zip
   ```

2. Upload `extension/.output/*-chrome.zip`.
3. After Chrome Web Store assigns the stable extension ID, register the native
   host with that ID:

   ```bash
   homebase-bts native-host install --browser chrome --extension-id <store-id>
   ```

4. Verify:

   ```bash
   homebase-bts doctor
   homebase-bts apply examples/vacation.json
   ```

Store release notes should include the required Python package version. The
extension cannot work against the real browser without the CLI/native host.

## Release checklist

```bash
git status --short
mise run lint
mise run test
mise run build
cd cli && uv build
cd ../extension && npm run zip
```

Install from artifacts in a clean environment:

```bash
python -m pip install --user cli/dist/homebase_bts-<version>-py3-none-any.whl
homebase-bts version
homebase-bts native-host install --browser chrome --extension-id <id>
homebase-bts doctor
homebase-bts apply examples/vacation.json --local
homebase-bts apply examples/vacation.json
```

Tag after artifact verification:

```bash
git tag v<version>
```

Push/publish only after the Python package, extension zip, and native messaging
registration have been verified together.
