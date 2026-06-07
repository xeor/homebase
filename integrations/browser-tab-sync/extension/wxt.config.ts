import { resolve } from "node:path";
import { defineConfig } from "wxt";

// Host name must match installer.HOST_NAME in the CLI.
const NATIVE_HOST = "nu.boa.homebase_bts";

// Persistent dev profile. The browser resolves the native-messaging host dir
// relative to its user-data-dir, so we use a stable profile (not web-ext's
// throwaway temp) and install the host manifest into <profile>/NativeMessagingHosts.
// This keeps everything self-contained; your daily browser is never touched.
const devProfile = process.env.HBTS_DEV_PROFILE ?? resolve(process.cwd(), "../.dev-profile");

// Optional: override the launched binary (default: whatever wxt finds).
const devBrowserBin = process.env.HBTS_DEV_BROWSER_BIN;

export default defineConfig({
  manifest: {
    name: "homebase-bts",
    description: "Browser-tab-sync helper for Homebase.",
    permissions: ["tabs", "tabGroups", "nativeMessaging", "storage", "alarms"],
  },
  webExt: {
    startUrls: ["about:blank"],
    chromiumProfile: devProfile,
    keepProfileChanges: true,
    ...(devBrowserBin ? { binaries: { chrome: devBrowserBin } } : {}),
  },
  // Surfaced to other modules via import.meta if needed during build.
  vite: () => ({ define: { __NATIVE_HOST__: JSON.stringify(NATIVE_HOST) } }),
});
