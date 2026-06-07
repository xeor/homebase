import { browser, type Browser } from "wxt/browser";
import {
  loadBinding,
  loadGroupBinding,
  saveBinding,
  saveGroupBinding,
  type Binding,
} from "./binding";
import type { EnsureProfile, EnsureResult, FocusProfile } from "./protocol";
import { sameUrl } from "./urlnorm";

// Execute host requests against the browser. The host owns file IO and policy;
// here we make the managed tab group match the desired profile, idempotently,
// without touching other tabs/windows/groups.

type GroupResolveResult =
  | { ok: true; group?: Browser.tabGroups.TabGroup }
  | { ok: false; error: string };

export async function ensure(req: EnsureProfile): Promise<EnsureResult> {
  const { profile } = req;
  const groupTitle = profile.group?.title ?? profile.title ?? profile.id;

  const win = await browser.windows.getCurrent();
  const windowId = win.id!;

  const resolved = await resolveGroup(profile.id, groupTitle, windowId);
  if (!resolved.ok) {
    console.warn("[homebase-bts]", resolved.error);
  }
  let group = resolved.ok ? resolved.group : undefined;
  let groupCreated = false;
  let created = 0;
  let existing = 0;

  const groupTabs = group ? await browser.tabs.query({ groupId: group.id }) : [];
  const binding = await loadBinding(profile.id);
  const claimed = new Set<number>();
  const nextBinding: Binding = {};
  const newTabIds: number[] = [];

  // A tab matches a desired URL if its current URL matches, OR if it was opened
  // for that desired URL earlier (recorded binding) — surviving redirects.
  const matches = (t: Browser.tabs.Tab, desiredUrl: string): boolean => {
    if (t.id == null) return false;
    const recorded = binding[t.id];
    if (recorded !== undefined && sameUrl(recorded, desiredUrl)) return true;
    return t.url != null && t.url !== "" && sameUrl(t.url, desiredUrl);
  };

  for (const desired of profile.tabs) {
    const match = groupTabs.find((t) => t.id != null && !claimed.has(t.id) && matches(t, desired.url));
    if (match?.id != null) {
      claimed.add(match.id);
      nextBinding[match.id] = desired.url;
      existing++;
      continue;
    }
    const tab = await browser.tabs.create({ url: desired.url, active: false, windowId });
    if (tab.id != null) {
      newTabIds.push(tab.id);
      claimed.add(tab.id);
      nextBinding[tab.id] = desired.url;
    }
    created++;
  }

  await saveBinding(profile.id, nextBinding);

  if (newTabIds.length > 0) {
    const tabIds = newTabIds as [number, ...number[]];
    if (group) {
      await browser.tabs.group({ tabIds, groupId: group.id });
    } else {
      const groupId = await browser.tabs.group({ tabIds, createProperties: { windowId } });
      group = await browser.tabGroups.get(groupId);
      groupCreated = true;
    }
  }

  if (group) {
    await browser.tabGroups.update(group.id, {
      title: groupTitle,
      ...(profile.group?.color
        ? { color: profile.group.color as Browser.tabGroups.UpdateProperties["color"] }
        : {}),
      ...(profile.group?.collapsed != null ? { collapsed: profile.group.collapsed } : {}),
    });
    await saveGroupBinding(profile.id, group.id);
  }

  const focused = group ? await focusGroup(group.id, profile.group?.focus, nextBinding) : false;

  return {
    type: "ensure_result",
    request_id: req.request_id,
    ok: true,
    created_tabs: created,
    existing_tabs: existing,
    moved_tabs: 0,
    removed_tabs: 0,
    group_created: groupCreated,
    focused,
  };
}

async function focusGroup(groupId: number, focus: string | undefined, binding: Binding): Promise<boolean> {
  const tabs = (await browser.tabs.query({ groupId })).sort((a, b) => a.index - b.index);
  const target = pickFocusTarget(tabs, focus, binding);
  if (target?.id == null) return false;
  await browser.tabGroups.update(groupId, { collapsed: false });
  await browser.tabs.update(target.id, { active: true });
  if (target.windowId != null) await browser.windows.update(target.windowId, { focused: true });
  return true;
}

// focus: "first" (default), "last-active", or a tab URL. Unknown URLs fall back
// to the first tab so focus never silently fails.
function pickFocusTarget(
  tabs: Browser.tabs.Tab[],
  focus: string | undefined,
  binding: Binding,
): Browser.tabs.Tab | undefined {
  if (focus === "last-active") {
    return tabs.reduce<Browser.tabs.Tab | undefined>(
      (best, t) => ((best?.lastAccessed ?? -1) >= (t.lastAccessed ?? -1) ? best : t),
      undefined,
    );
  }
  if (focus && focus !== "first") {
    const url = focus;
    const byUrl = tabs.find((t) => {
      const recorded = t.id != null ? binding[t.id] : undefined;
      if (recorded !== undefined && sameUrl(recorded, url)) return true;
      return t.url != null && t.url !== "" && sameUrl(t.url, url);
    });
    if (byUrl) return byUrl;
  }
  return tabs[0];
}

export async function focus(req: FocusProfile): Promise<EnsureResult> {
  const win = await browser.windows.getCurrent();
  const resolved = await resolveGroup(req.profile_id, req.group_title, win.id!);
  if (!resolved.ok || !resolved.group) {
    return {
      type: "ensure_result",
      request_id: req.request_id,
      ok: false,
      error: resolved.ok ? `group not found: ${req.group_title}` : resolved.error,
    };
  }
  const binding = await loadBinding(req.profile_id);
  const focused = await focusGroup(resolved.group.id, req.focus, binding);
  return { type: "ensure_result", request_id: req.request_id, ok: true, focused };
}

async function resolveGroup(
  profileId: string,
  title: string,
  windowId: number,
): Promise<GroupResolveResult> {
  const boundGroupId = await loadGroupBinding(profileId);
  if (boundGroupId !== undefined) {
    try {
      const group = await browser.tabGroups.get(boundGroupId);
      if (group.title === title) return { ok: true, group };
    } catch {
      // Session-local ids disappear when Chrome recycles the group.
    }
  }
  const matches = await browser.tabGroups.query({ title, windowId });
  if (matches.length > 1) {
    return { ok: false, error: `ambiguous group title: ${title}` };
  }
  return { ok: true, group: matches[0] };
}
