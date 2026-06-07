# Support Matrix

Scope for now: desktop Chromium-based browsers.

`homebase-bts` requires:

- Chromium extension APIs: `tabs`, `tabGroups`, `nativeMessaging`, `storage`
- MV3 service worker support
- native messaging host lookup for the browser/profile
- manual or store-based extension installation

## Browser Matrix

| Browser | macOS | Native messaging | Extension load | Status | Notes |
|---|---:|---:|---:|---|---|
| Chrome | yes | yes | unpacked / store | supported | Primary target. |
| Chrome for Testing | yes | yes | unpacked | planned | Useful for automated testing. |
| Chromium | yes | yes | unpacked | planned | Same API family as Chrome. |
| Vivaldi | yes | likely | unpacked / Chrome Web Store | needs test | Desktop supports Chromium extensions. Snap build does not support NativeMessaging. |
| Brave | yes | likely | unpacked / Chrome Web Store | planned | Needs native-host path verification. |
| Edge | yes | likely | unpacked / Edge/Chrome store | planned | Needs native-host path verification. |
| Helium | unknown | unknown | Chromium extensions | research | <https://helium.computer>; desktop beta, Chromium-based, native-host manifest path needs proof. |
| Opera | unknown | unknown | likely | out of scope | Add after core Chromium browsers. |
| Arc | unknown | unknown | likely | out of scope | Add after core Chromium browsers. |

Status meanings:

- `supported`: tested and expected to work
- `planned`: known Chromium target, not tested yet
- `needs test`: expected shape is known, must be verified manually
- `research`: browser-specific manifest location/API behavior unknown
- `out of scope`: intentionally not tested yet

## Native Host Paths

Current macOS installer targets:

| Browser key | Manifest directory |
|---|---|
| `chrome` | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/` |
| `chrome-beta` | `~/Library/Application Support/Google/Chrome Beta/NativeMessagingHosts/` |
| `chrome-canary` | `~/Library/Application Support/Google/Chrome Canary/NativeMessagingHosts/` |
| `chrome-for-testing` | `~/Library/Application Support/Google/Chrome for Testing/NativeMessagingHosts/` |
| `chromium` | `~/Library/Application Support/Chromium/NativeMessagingHosts/` |
| `vivaldi` | `~/Library/Application Support/Vivaldi/NativeMessagingHosts/` |
| `brave` | `~/Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts/` |
| `edge` | `~/Library/Application Support/Microsoft Edge/NativeMessagingHosts/` |

Manifest file:

```text
nu.boa.homebase_bts.json
```

Manifest origin must match the loaded extension ID:

```json
{
  "allowed_origins": ["chrome-extension://<extension-id>/"]
}
```

## Vivaldi Test

Goal: prove that Vivaldi desktop can load the extension, launch the native host,
and let `apply` mutate a tab group through the native backend.

Preconditions:

```bash
mise install
mise run setup
mise run lint
mise run test
```

Build the extension:

```bash
mise run ext:build
```

Load unpacked in Vivaldi:

```text
vivaldi://extensions
Developer mode
Load unpacked -> extension/.output/chrome-mv3/
copy extension ID
```

Register the native host:

```bash
mise run cli:run -- native-host install \
  --browser vivaldi \
  --extension-id <vivaldi-extension-id>
```

Restart Vivaldi, then verify:

```bash
mise run cli:run -- doctor
mise run cli:run -- apply examples/vacation.json
mise run cli:run -- focus examples/vacation.json
mise run cli:run -- debug examples/vacation.json
```

Pass criteria:

- `doctor` finds the host executable
- `doctor` finds the Vivaldi native host manifest
- `doctor` finds the host socket while Vivaldi is running
- `apply` creates or reuses the managed group
- a second `apply` is idempotent
- `focus` focuses the managed group
- `debug` prints snapshots after tab/group changes

Fail criteria:

- Vivaldi reports `Specified native messaging host not found`
- the host process starts but no socket appears
- `apply` times out waiting for the extension
- `tabGroups` calls fail in the extension

Log locations:

```text
~/.config/homebase-bts/logs/homebase-bts.log
~/Library/Application Support/Vivaldi/NativeMessagingHosts/nu.boa.homebase_bts.json
```

Cleanup:

```bash
mise run cli:run -- native-host uninstall
```

## Helium Notes

Helium is in scope for later Chromium-family testing:

- site: <https://helium.computer>
- desktop-only beta
- Chromium-based
- claims support for Chromium extensions

Unknown until tested:

- macOS native messaging manifest directory
- whether `chrome.runtime.connectNative` is enabled
- whether `tabGroups` behaves like Chrome/Vivaldi
- whether Chrome Web Store or unpacked extension IDs are stable enough for
  release installs

## Sources

- Chrome native messaging:
  <https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging>
- Vivaldi extension support and unpacked extension loading:
  <https://help.vivaldi.com/article/extensions/>
- Vivaldi Snap NativeMessaging limitation:
  <https://help.vivaldi.com/desktop/install-update/install-vivaldi-for-snap/>
- Helium:
  <https://helium.computer>
