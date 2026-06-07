import { browser } from "wxt/browser";
import type { HostMessage } from "../src/protocol";
import { ensureConnected, setHandler } from "../src/native";
import { addWatch, readSnapshot, removeWatch, scheduleSnapshot } from "../src/observer";
import { ensure, focus } from "../src/reconcile";

const KEEPALIVE_ALARM = "homebase-bts-keepalive";

export default defineBackground(() => {
  setHandler(async (msg: HostMessage, reply) => {
    switch (msg.type) {
      case "ensure_profile":
        reply(await ensure(msg));
        break;
      case "health_check":
        reply({ type: "ensure_result", request_id: msg.request_id, ok: true });
        break;
      case "focus_profile":
        reply(await focus(msg));
        break;
      case "snapshot_request":
        {
          const snapshot = await readSnapshot(msg.profile_id, msg.group_title, msg.request_id);
          reply(
            snapshot ?? {
              type: "ensure_result",
              request_id: msg.request_id,
              ok: false,
              error: `group not found: ${msg.group_title}`,
            },
          );
        }
        break;
      case "start_watch":
        await addWatch(msg.profile_id, msg.group_title);
        break;
      case "stop_watch":
        await removeWatch(msg.profile_id);
        break;
    }
  });

  // Connect on every path that wakes the worker.
  ensureConnected();
  browser.runtime.onStartup.addListener(ensureConnected);
  browser.runtime.onInstalled.addListener(ensureConnected);

  // Top-level listeners so a group change wakes the worker and is observed even
  // after the worker was killed. The handler reads watched state from storage.
  const onChange = () => scheduleSnapshot();
  browser.tabs.onCreated.addListener(onChange);
  browser.tabs.onRemoved.addListener(onChange);
  browser.tabs.onMoved.addListener(onChange);
  browser.tabs.onAttached.addListener(onChange);
  browser.tabs.onDetached.addListener(onChange);
  browser.tabs.onUpdated.addListener(onChange);
  browser.tabGroups.onUpdated.addListener(onChange);
  browser.tabGroups.onMoved.addListener(onChange);
  browser.tabGroups.onRemoved.addListener(onChange);

  // Backstop: re-establish the native port if it dropped while the worker slept.
  browser.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 1 });
  browser.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === KEEPALIVE_ALARM) ensureConnected();
  });
});
