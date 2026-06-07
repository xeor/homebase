# Security

`homebase-bts` has two privileged components:

- MV3 extension: reads and mutates browser tabs/tab groups.
- Python native host: reads/writes profile files and bridges CLI requests.

The profile file is desired state. The browser is actual state. The CLI/host owns
validation, policy, merge, and file IO. The extension only executes browser API
operations requested by the host and streams snapshots for watched groups.

## Extension Permissions

Manifest permissions:

| Permission | Why it is needed | Boundaries |
|---|---|---|
| `tabs` | Read tab URL/title/index/active state, create tabs, focus tabs, group tabs. | No `host_permissions`; no page content access; no content scripts. |
| `tabGroups` | Query, create, update, focus, and observe Chrome tab groups. | Operations resolve a managed group by session binding or unique title. Ambiguous title fallback is rejected. |
| `nativeMessaging` | Connect to `nu.boa.homebase_bts`. | Browser enforces the native host manifest `allowed_origins`. |
| `storage` | Keep session-local tab/group bindings and watched profiles across MV3 worker restarts. | Uses `storage.session`, not `storage.sync` or durable browser storage. |
| `alarms` | Reconnect the native port when the service worker wakes. | One keepalive alarm; no network or page access. |

Not requested:

- `host_permissions`
- `scripting`
- content scripts
- `webRequest`
- remote code execution APIs

The extension cannot read arbitrary files. It cannot write profile files. It
does not fetch network resources.

## Native Messaging Boundary

Host name: `nu.boa.homebase_bts`.

Browser-to-host authorization is controlled by the native messaging manifest:

```json
{
  "name": "nu.boa.homebase_bts",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://<extension-id>/"]
}
```

The installer writes one manifest for one browser variant or one explicit dev
profile. It does not install broadly across all browsers by default.

Frames use Chrome native messaging framing:

```text
uint32 little-endian byte length
UTF-8 JSON body
```

Protocol source of truth:

- `schema/native-messaging.schema.json`
- `cli/src/homebase_bts/protocol.py`
- `extension/src/protocol.ts`

Python validates every frame with Pydantic discriminated unions and rejects
frames above `8 MiB`. The extension also validates host messages at runtime
before dispatch. Invalid host messages are dropped; if they contain a request
ID, the extension returns an error result instead of mutating browser state.

### Wire Examples

Host to extension: apply a profile.

```json
{
  "type": "ensure_profile",
  "request_id": "1f74f0e5-5c25-47ef-9b61-b9327c30f426",
  "profile": {
    "schema": 1,
    "id": "vacation",
    "title": "Vacation",
    "group": { "title": "Vacation", "color": "cyan", "focus": "first" },
    "tabs": [
      { "url": "https://maps.google.com/", "title": "Maps" },
      { "url": "https://www.google.com/travel/flights", "title": "Flights" }
    ],
    "sync": { "mode": "two-way", "delete_missing": false }
  }
}
```

Extension to host: result of that browser mutation.

```json
{
  "type": "ensure_result",
  "request_id": "1f74f0e5-5c25-47ef-9b61-b9327c30f426",
  "ok": true,
  "created_tabs": 2,
  "existing_tabs": 0,
  "group_created": true,
  "focused": true
}
```

Extension to host: watched group snapshot for two-way sync.

```json
{
  "type": "profile_snapshot",
  "profile_id": "vacation",
  "browser": "chrome",
  "group_id": 42,
  "group": { "title": "Vacation", "color": "cyan", "collapsed": false },
  "tabs": [
    {
      "browser_tab_id": 1001,
      "url": "https://maps.google.com/",
      "managed_url": "https://maps.google.com/",
      "title": "Maps",
      "active": true,
      "index": 0
    }
  ]
}
```

CLI to host: register a persistent two-way sync target.

```json
{
  "type": "watch_profile",
  "request_id": "8f5fb441-ce9d-42cc-8aa8-6224d274e25b",
  "profile_id": "vacation",
  "group_title": "Vacation",
  "file_path": "/Users/me/work/vacation.json",
  "debug": false
}
```

Each JSON payload above is sent inside a length-prefixed native messaging frame.
The JSON body is what the validators parse; the frame prefix only defines byte
length.

### Validation Map

| Data | Schema | Python validation | Extension validation |
|---|---|---|---|
| Profile file | `schema/profile.schema.json` | `cli/src/homebase_bts/models.py` (`Profile`, `TabSpec`, `SyncSpec`) | Rechecked for host-originated `ensure_profile` in `extension/src/protocol.ts` (`validateProfile`) |
| Native messages | `schema/native-messaging.schema.json` | `cli/src/homebase_bts/protocol.py` (`Message`, `read_frame`, `decode_frame`) | `extension/src/protocol.ts` (`validateHostMessage`) for host-to-extension messages |
| Frame size | native framing rule | `MAX_FRAME_BYTES = 8 * 1024 * 1024` in `cli/src/homebase_bts/protocol.py` | Browser native messaging API handles host-to-extension message framing |
| Sync target file | profile schema plus host policy | `cli/src/homebase_bts/nativehost.py` (`_validate_sync_target`) | Not applicable; extension has no file IO |
| Browser group identity | local state plus browser APIs | Host stores sync target profile ID/title | `extension/src/reconcile.ts` and `extension/src/observer.ts` reject ambiguous title fallback |

Important validated fields:

- message `type` must be one of the protocol discriminators;
- request/response messages that need replies must carry `request_id`;
- profile `schema` must be `1`;
- profile `id` must match `^[a-z0-9][a-z0-9._-]*$`;
- tab `url` must be absolute `http` or `https`;
- group color, sync mode, match policy, browser, strategy, and window are enums;
- unknown profile fields are rejected by Python (`extra="forbid"`);
- sync target `file_path` must already exist and contain the same profile ID.

## CLI Socket Boundary

The browser owns the native host process lifecycle. The host also opens a local
Unix socket under a private runtime directory:

```text
HBTS_RUNTIME_DIR/homebase-bts/host.sock
$XDG_RUNTIME_DIR/homebase-bts/host.sock
<per-user temp>/homebase-bts-<uid>/host.sock
```

The runtime directory is chmod `0700`; the socket is chmod `0600`. It accepts
length-prefixed protocol frames from the same user account. CLI requests are
forwarded to the extension; replies are matched by `request_id` and time out
after 30 seconds.

Persistent sync targets are stored in:

```text
~/.config/homebase-bts/sync.json
```

Two-way sync registration is constrained:

- `file_path` must resolve to an existing file.
- The file must parse as a valid profile.
- The file profile ID must match the requested profile ID.
- The host writes only registered target files.

Profile writes are atomic: temp file, fsync, rename, directory fsync. Existing
profile contents are backed up under `.homebase-bts/history/`.

## Data Flow

Apply:

```text
CLI -> host socket -> native host -> extension -> browser APIs
```

Two-way sync:

```text
browser tab/group event -> extension snapshot -> native host -> merge -> profile file
```

The extension snapshots only watched managed groups. Snapshot payload contains
tab IDs, URLs, titles, active/index state, group metadata, and session-local
group/tab IDs. It does not include page DOM, cookies, local storage, request
bodies, response bodies, or credentials.

## Managed Group Resolution

Browser `group_id`, `window_id`, and `tab_id` are session-local and not trusted
as durable identity.

Resolution order:

1. Session binding stored by profile ID.
2. Unique tab group title fallback.

If title fallback is ambiguous, the extension does not pick the first match:

- snapshot is skipped;
- focus returns an error;
- apply creates a new managed group instead of mutating an arbitrary group.

This prevents same-title groups from leaking unrelated tab URLs into a profile
or receiving unintended mutations.

## Destructive Operations

Defaults are non-destructive.

Closed browser tabs are kept in the profile file unless:

```json
{ "sync": { "delete_missing": true } }
```

The extension does not remove tabs from the browser in the MVP. File-side tab
removal only happens in the Python merge path and only when `delete_missing` is
explicitly true.

## URL Handling

Managed tab URLs must be absolute `http` or `https` URLs:

- enforced by the Python profile model;
- enforced again by extension runtime validation for host messages.

The extension does not open `file:`, `javascript:`, `data:`, or extension URLs
from profile input.

URL matching is normalized for idempotency and redirect handling. The extension
stores a session-local binding from browser tab ID to the desired managed URL so
redirects do not cause duplicate tab creation or file pollution.

## Logging

The native host writes logs to:

```text
~/.config/homebase-bts/logs/homebase-bts.log
```

Native messaging stdout is reserved for framed JSON only. The host does not log
to stdout.

The extension logs connection state, rejected native messages, watch activation,
and ambiguous group resolution to the browser console. It does not intentionally
log full snapshots.

## Failure Modes

Fail closed cases:

- invalid native frame in Python: rejected;
- oversized native frame: rejected;
- invalid host message in extension: rejected before dispatch;
- duplicate title fallback: skipped or reported as error;
- profile ID mismatch on sync registration: rejected;
- host/extension timeout: CLI receives an error result.

Expected degradation:

- MV3 service worker restarts clear some session bindings; the extension falls
  back only to unique title resolution.
- If the native port is down, snapshots are not posted until reconnect.
- If a profile file cannot be parsed or written, the host logs the failure and
  does not partially write the file.

## Checks

```bash
mise run test
mise run lint
homebase-bts doctor
```

`doctor` checks the host executable, native host manifest, and live host socket.
