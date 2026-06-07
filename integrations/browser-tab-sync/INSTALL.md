# Install

Install pieces in this order:

1. Python package (`homebase-bts`, `homebase-bts-host`)
2. Browser extension
3. Native messaging manifest for that browser/extension ID

First target is Chrome on macOS. Chromium, Vivaldi, Brave and Edge use the same
native-messaging flow.

## Development install

```bash
mise install
mise run setup
mise run ext:dev
```

`mise run ext:dev` launches a dev browser with a persistent profile at
`.dev-profile/` and installs the native host manifest into that profile.

In another shell:

```bash
mise run cli:run -- doctor
mise run cli:run -- apply examples/vacation.json
```

Daily Chrome/Vivaldi profiles are not touched by the dev install.

Override the dev browser binary:

```bash
HBTS_DEV_BROWSER_BIN="/Applications/Chromium.app/Contents/MacOS/Chromium" mise run ext:dev
```

## User install from release artifacts

Install the Python package:

```bash
python -m pip install --user homebase_bts-<version>-py3-none-any.whl
homebase-bts version
which homebase-bts-host
```

Or, once published:

```bash
pipx install homebase-bts
homebase-bts version
which homebase-bts-host
```

Load the extension:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Load unpacked: `extension/.output/chrome-mv3/`
4. Copy the extension ID

Register the native host:

```bash
homebase-bts native-host install \
  --browser chrome \
  --extension-id <extension-id>
```

Restart the browser after installing the manifest.

Verify:

```bash
homebase-bts doctor
homebase-bts apply examples/vacation.json --local
homebase-bts apply examples/vacation.json
```

`doctor` should show:

```text
[ok ] host executable: ...
[ok ] native host manifest: ...
[ok ] host socket (browser running): ...
```

The socket check only passes while the browser extension is connected.

## Browser variants

Use one of:

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

Examples:

```bash
homebase-bts native-host install --browser chromium --extension-id <id>
homebase-bts native-host install --browser vivaldi --extension-id <id>
```

The manifest is written to:

```text
~/Library/Application Support/<browser>/NativeMessagingHosts/nu.boa.homebase_bts.json
```

## Uninstall

Remove native host manifests:

```bash
homebase-bts native-host uninstall
```

Remove the Python package:

```bash
pipx uninstall homebase-bts
```

or:

```bash
python -m pip uninstall homebase-bts
```

Remove the browser extension from `chrome://extensions`.

Optional local state cleanup:

```bash
rm -rf ~/.config/homebase-bts
```

## Troubleshooting

No host socket:

```bash
homebase-bts doctor
```

If only the socket check fails, the browser is not running, the extension is not
loaded, or the browser was started before the manifest existed. Restart the
browser.

Host executable missing:

```bash
which homebase-bts-host
```

Reinstall the Python package, then rerun:

```bash
homebase-bts native-host install --browser chrome --extension-id <id>
```

Wrong extension ID:

```bash
homebase-bts native-host install --browser chrome --extension-id <current-id>
```

For unpacked extensions, the ID can change if the output path changes.
