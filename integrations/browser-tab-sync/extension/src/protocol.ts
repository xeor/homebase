// Wire protocol. Mirror of schema/native-messaging.schema.json and
// cli/src/homebase_bts/protocol.py. Keep all three in sync.

export interface ProfileTab {
  url: string;
  title?: string;
}

export type BrowserName = "chrome" | "vivaldi" | "brave" | "edge" | "firefox";
export type BrowserStrategy = "tab-group" | "window";
export type BrowserWindow = "current" | "new";
export type GroupColor =
  | "grey"
  | "blue"
  | "red"
  | "yellow"
  | "green"
  | "pink"
  | "purple"
  | "cyan"
  | "orange";
export type SyncMode = "apply-only" | "two-way" | "manual";
export type MatchPolicy = "exact-url" | "normalized-url" | "title-url";

export interface BrowserSpec {
  preferred?: BrowserName;
  strategy?: BrowserStrategy;
  window?: BrowserWindow;
}

export interface GroupSpec {
  title?: string;
  color?: GroupColor;
  collapsed?: boolean;
  focus?: string;
}

export interface SyncSpec {
  mode?: SyncMode;
  delete_missing?: boolean;
  adopt_existing?: boolean;
  match?: MatchPolicy;
}

export interface Profile {
  schema: 1;
  id: string;
  title?: string;
  browser?: BrowserSpec;
  group?: GroupSpec;
  tabs: ProfileTab[];
  sync?: SyncSpec;
}

export interface EnsureProfile {
  type: "ensure_profile";
  request_id: string;
  profile: Profile;
}

export interface HealthCheck {
  type: "health_check";
  request_id: string;
}

export interface FocusProfile {
  type: "focus_profile";
  request_id: string;
  profile_id: string;
  group_title: string;
  focus?: string;
}

export interface SnapshotRequest {
  type: "snapshot_request";
  request_id: string;
  profile_id: string;
  group_title: string;
}

export interface StartWatch {
  type: "start_watch";
  request_id: string;
  profile_id: string;
  group_title: string;
}

export interface StopWatch {
  type: "stop_watch";
  profile_id: string;
}

export interface SnapshotTab {
  browser_tab_id: number;
  url: string;
  managed_url?: string;
  title?: string;
  active?: boolean;
  index: number;
}

export interface SnapshotGroup {
  title?: string;
  color?: string;
  collapsed?: boolean;
}

export interface ProfileSnapshot {
  type: "profile_snapshot";
  request_id?: string;
  profile_id: string;
  browser: string;
  window_id?: number;
  group_id?: number;
  group?: SnapshotGroup;
  tabs: SnapshotTab[];
}

export interface EnsureResult {
  type: "ensure_result";
  request_id: string;
  ok: boolean;
  error?: string;
  created_tabs?: number;
  existing_tabs?: number;
  moved_tabs?: number;
  removed_tabs?: number;
  group_created?: boolean;
  focused?: boolean;
}

export type HostMessage =
  | EnsureProfile
  | HealthCheck
  | FocusProfile
  | SnapshotRequest
  | StartWatch
  | StopWatch;
export type ExtensionMessage = ProfileSnapshot | EnsureResult;

const BROWSERS = new Set<BrowserName>(["chrome", "vivaldi", "brave", "edge", "firefox"]);
const STRATEGIES = new Set<BrowserStrategy>(["tab-group", "window"]);
const WINDOWS = new Set<BrowserWindow>(["current", "new"]);
const COLORS = new Set<GroupColor>([
  "grey",
  "blue",
  "red",
  "yellow",
  "green",
  "pink",
  "purple",
  "cyan",
  "orange",
]);
const SYNC_MODES = new Set<SyncMode>(["apply-only", "two-way", "manual"]);
const MATCH_POLICIES = new Set<MatchPolicy>(["exact-url", "normalized-url", "title-url"]);

export type ValidationResult =
  | { ok: true; message: HostMessage }
  | { ok: false; error: string; request_id?: string };

export function validateHostMessage(raw: unknown): ValidationResult {
  if (!isRecord(raw)) return invalid("message must be an object");
  const requestId = optionalString(raw.request_id);

  switch (raw.type) {
    case "ensure_profile": {
      if (!requestId) return invalid("request_id is required");
      return validateEnsureProfile(raw, requestId);
    }
    case "health_check": {
      if (!requestId) return invalid("request_id is required");
      return { ok: true, message: { type: "health_check", request_id: requestId } };
    }
    case "focus_profile": {
      if (!requestId) return invalid("request_id is required");
      return validateFocusProfile(raw, requestId);
    }
    case "snapshot_request": {
      if (!requestId) return invalid("request_id is required");
      return validateSnapshotRequest(raw, requestId);
    }
    case "start_watch": {
      if (!requestId) return invalid("request_id is required");
      return validateStartWatch(raw, requestId);
    }
    case "stop_watch":
      return validateStopWatch(raw, requestId);
    default:
      return invalid("unknown message type", requestId);
  }
}

function validateEnsureProfile(raw: Record<string, unknown>, requestId: string): ValidationResult {
  const profile = validateProfile(raw.profile);
  if (!profile.ok) return invalid(`profile.${profile.error}`, requestId);
  return {
    ok: true,
    message: { type: "ensure_profile", request_id: requestId, profile: profile.value },
  };
}

function validateFocusProfile(raw: Record<string, unknown>, requestId: string): ValidationResult {
  const profileId = requiredString(raw.profile_id, "profile_id");
  if (!profileId.ok) return invalid(profileId.error, requestId);
  const groupTitle = requiredString(raw.group_title, "group_title");
  if (!groupTitle.ok) return invalid(groupTitle.error, requestId);
  const focus = optionalString(raw.focus);
  return {
    ok: true,
    message: {
      type: "focus_profile",
      request_id: requestId,
      profile_id: profileId.value,
      group_title: groupTitle.value,
      ...(focus !== undefined ? { focus } : {}),
    },
  };
}

function validateSnapshotRequest(
  raw: Record<string, unknown>,
  requestId: string,
): ValidationResult {
  const profileId = requiredString(raw.profile_id, "profile_id");
  if (!profileId.ok) return invalid(profileId.error, requestId);
  const groupTitle = requiredString(raw.group_title, "group_title");
  if (!groupTitle.ok) return invalid(groupTitle.error, requestId);
  return {
    ok: true,
    message: {
      type: "snapshot_request",
      request_id: requestId,
      profile_id: profileId.value,
      group_title: groupTitle.value,
    },
  };
}

function validateStartWatch(raw: Record<string, unknown>, requestId: string): ValidationResult {
  const profileId = requiredString(raw.profile_id, "profile_id");
  if (!profileId.ok) return invalid(profileId.error, requestId);
  const groupTitle = requiredString(raw.group_title, "group_title");
  if (!groupTitle.ok) return invalid(groupTitle.error, requestId);
  return {
    ok: true,
    message: {
      type: "start_watch",
      request_id: requestId,
      profile_id: profileId.value,
      group_title: groupTitle.value,
    },
  };
}

function validateStopWatch(raw: Record<string, unknown>, requestId?: string): ValidationResult {
  const profileId = requiredString(raw.profile_id, "profile_id");
  if (!profileId.ok) return invalid(profileId.error, requestId);
  return { ok: true, message: { type: "stop_watch", profile_id: profileId.value } };
}

type ProfileResult = { ok: true; value: Profile } | { ok: false; error: string };

function validateProfile(raw: unknown): ProfileResult {
  if (!isRecord(raw)) return { ok: false, error: "must be an object" };
  if (raw.schema !== 1) return { ok: false, error: "schema must be 1" };

  const id = requiredString(raw.id, "id");
  if (!id.ok) return { ok: false, error: id.error };
  if (!/^[a-z0-9][a-z0-9._-]*$/.test(id.value)) {
    return { ok: false, error: "id is invalid" };
  }

  if (!Array.isArray(raw.tabs)) return { ok: false, error: "tabs must be an array" };
  const tabs: ProfileTab[] = [];
  for (const [i, tab] of raw.tabs.entries()) {
    const parsed = validateTab(tab);
    if (!parsed.ok) return { ok: false, error: `tabs[${i}].${parsed.error}` };
    tabs.push(parsed.value);
  }

  const title = optionalString(raw.title);
  const browser = validateBrowserSpec(raw.browser);
  if (!browser.ok) return { ok: false, error: `browser.${browser.error}` };
  const group = validateGroupSpec(raw.group);
  if (!group.ok) return { ok: false, error: `group.${group.error}` };
  const sync = validateSyncSpec(raw.sync);
  if (!sync.ok) return { ok: false, error: `sync.${sync.error}` };

  return {
    ok: true,
    value: {
      schema: 1,
      id: id.value,
      ...(title !== undefined ? { title } : {}),
      ...(browser.value !== undefined ? { browser: browser.value } : {}),
      ...(group.value !== undefined ? { group: group.value } : {}),
      tabs,
      ...(sync.value !== undefined ? { sync: sync.value } : {}),
    },
  };
}

type ValueResult<T> = { ok: true; value: T } | { ok: false; error: string };

function validateTab(raw: unknown): ValueResult<ProfileTab> {
  if (!isRecord(raw)) return { ok: false, error: "must be an object" };
  const url = requiredString(raw.url, "url");
  if (!url.ok) return url;
  if (!isHttpUrl(url.value)) return { ok: false, error: "url must be absolute http(s)" };
  const title = optionalString(raw.title);
  return { ok: true, value: { url: url.value, ...(title !== undefined ? { title } : {}) } };
}

function validateBrowserSpec(raw: unknown): ValueResult<BrowserSpec | undefined> {
  if (raw === undefined) return { ok: true, value: undefined };
  if (!isRecord(raw)) return { ok: false, error: "must be an object" };
  const preferred = optionalEnum(raw.preferred, BROWSERS, "preferred");
  if (!preferred.ok) return preferred;
  const strategy = optionalEnum(raw.strategy, STRATEGIES, "strategy");
  if (!strategy.ok) return strategy;
  const window = optionalEnum(raw.window, WINDOWS, "window");
  if (!window.ok) return window;
  return {
    ok: true,
    value: {
      ...(preferred.value !== undefined ? { preferred: preferred.value } : {}),
      ...(strategy.value !== undefined ? { strategy: strategy.value } : {}),
      ...(window.value !== undefined ? { window: window.value } : {}),
    },
  };
}

function validateGroupSpec(raw: unknown): ValueResult<GroupSpec | undefined> {
  if (raw === undefined) return { ok: true, value: undefined };
  if (!isRecord(raw)) return { ok: false, error: "must be an object" };
  const title = optionalString(raw.title);
  const color = optionalEnum(raw.color, COLORS, "color");
  if (!color.ok) return color;
  const collapsed = optionalBoolean(raw.collapsed, "collapsed");
  if (!collapsed.ok) return collapsed;
  const focus = optionalString(raw.focus);
  if (focus !== undefined && focus !== "first" && focus !== "last-active" && !isHttpUrl(focus)) {
    return { ok: false, error: "focus must be first, last-active, or an absolute http(s) URL" };
  }
  return {
    ok: true,
    value: {
      ...(title !== undefined ? { title } : {}),
      ...(color.value !== undefined ? { color: color.value } : {}),
      ...(collapsed.value !== undefined ? { collapsed: collapsed.value } : {}),
      ...(focus !== undefined ? { focus } : {}),
    },
  };
}

function validateSyncSpec(raw: unknown): ValueResult<SyncSpec | undefined> {
  if (raw === undefined) return { ok: true, value: undefined };
  if (!isRecord(raw)) return { ok: false, error: "must be an object" };
  const mode = optionalEnum(raw.mode, SYNC_MODES, "mode");
  if (!mode.ok) return mode;
  const deleteMissing = optionalBoolean(raw.delete_missing, "delete_missing");
  if (!deleteMissing.ok) return deleteMissing;
  const adoptExisting = optionalBoolean(raw.adopt_existing, "adopt_existing");
  if (!adoptExisting.ok) return adoptExisting;
  const match = optionalEnum(raw.match, MATCH_POLICIES, "match");
  if (!match.ok) return match;
  return {
    ok: true,
    value: {
      ...(mode.value !== undefined ? { mode: mode.value } : {}),
      ...(deleteMissing.value !== undefined ? { delete_missing: deleteMissing.value } : {}),
      ...(adoptExisting.value !== undefined ? { adopt_existing: adoptExisting.value } : {}),
      ...(match.value !== undefined ? { match: match.value } : {}),
    },
  };
}

function requiredString(raw: unknown, field: string): ValueResult<string> {
  if (typeof raw !== "string" || raw === "") {
    return { ok: false, error: `${field} must be a non-empty string` };
  }
  return { ok: true, value: raw };
}

function optionalString(raw: unknown): string | undefined {
  return typeof raw === "string" ? raw : undefined;
}

function optionalBoolean(raw: unknown, field: string): ValueResult<boolean | undefined> {
  if (raw === undefined) return { ok: true, value: undefined };
  if (typeof raw !== "boolean") return { ok: false, error: `${field} must be boolean` };
  return { ok: true, value: raw };
}

function optionalEnum<T extends string>(
  raw: unknown,
  values: Set<T>,
  field: string,
): ValueResult<T | undefined> {
  if (raw === undefined) return { ok: true, value: undefined };
  if (typeof raw !== "string" || !values.has(raw as T)) {
    return { ok: false, error: `${field} is invalid` };
  }
  return { ok: true, value: raw as T };
}

function isHttpUrl(raw: string): boolean {
  try {
    const url = new URL(raw);
    return (url.protocol === "http:" || url.protocol === "https:") && url.hostname !== "";
  } catch {
    return false;
  }
}

function isRecord(raw: unknown): raw is Record<string, unknown> {
  return raw !== null && typeof raw === "object" && !Array.isArray(raw);
}

function invalid(error: string, requestId?: string): ValidationResult {
  return { ok: false, error, ...(requestId !== undefined ? { request_id: requestId } : {}) };
}
