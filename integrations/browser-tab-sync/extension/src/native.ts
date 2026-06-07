import { browser, type Browser } from "wxt/browser";
import { validateHostMessage, type ExtensionMessage, type HostMessage } from "./protocol";

declare const __NATIVE_HOST__: string;

export type Reply = (msg: ExtensionMessage) => void;
export type HostHandler = (msg: HostMessage, reply: Reply) => void | Promise<void>;

// Singleton, self-healing connection to the Python native host. Chrome keeps the
// service worker alive while a native-messaging port is open, so the goal is to
// (re)establish the port whenever the worker wakes.

let port: Browser.runtime.Port | null = null;
let handler: HostHandler | null = null;

export function setHandler(onMessage: HostHandler): void {
  handler = onMessage;
}

export function ensureConnected(): void {
  if (port) return;
  try {
    port = browser.runtime.connectNative(__NATIVE_HOST__);
  } catch (err) {
    console.warn("[homebase-bts] connectNative threw:", err);
    port = null;
    return;
  }
  console.info("[homebase-bts] connected to native host", __NATIVE_HOST__);

  port.onMessage.addListener((raw) => {
    const current = port;
    const parsed = validateHostMessage(raw);
    if (!parsed.ok) {
      console.warn("[homebase-bts] rejected native host message:", parsed.error);
      if (parsed.request_id) {
        current?.postMessage({
          type: "ensure_result",
          request_id: parsed.request_id,
          ok: false,
          error: `invalid native host message: ${parsed.error}`,
        });
      }
      return;
    }
    if (!handler) {
      if ("request_id" in parsed.message) {
        current?.postMessage({
          type: "ensure_result",
          request_id: parsed.message.request_id,
          ok: false,
          error: "extension handler is not ready",
        });
      }
      return;
    }
    Promise.resolve(handler(parsed.message, (msg) => current?.postMessage(msg))).catch((err) => {
      console.warn("[homebase-bts] native host handler failed:", err);
      if ("request_id" in parsed.message) {
        current?.postMessage({
          type: "ensure_result",
          request_id: parsed.message.request_id,
          ok: false,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    });
  });

  port.onDisconnect.addListener(() => {
    console.warn("[homebase-bts] native host disconnected:", browser.runtime.lastError?.message);
    port = null;
  });
}

// Send an unsolicited message (e.g. a snapshot) to the host. Returns false if
// there's no live connection.
export function postToHost(msg: ExtensionMessage): boolean {
  if (!port) return false;
  try {
    port.postMessage(msg);
    return true;
  } catch (err) {
    console.warn("[homebase-bts] postToHost failed:", err);
    return false;
  }
}
