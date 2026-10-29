import { getPreferenceValues, showHUD, showToast, Toast } from "@raycast/api";
import { execFile, spawn } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { Herdr, herdrCli, herdrRunning } from "./herdr";

const DEFAULT_B_PATH = "/Users/xeor/.local/bin/b";
const DEFAULT_BASE_DIR = "~/base";
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_NEW_SPACE_COMMAND = "b --open-mode shell_cd";
const DEFAULT_NEW_PROJECT_COMMAND = "b new";
const DEFAULT_TERMINAL_BUNDLE = "com.apple.Terminal";
const COMMAND_PATHS = [
  "/Users/xeor/.local/bin",
  "/opt/homebrew/bin",
  "/usr/local/bin",
  "/usr/bin",
  "/bin",
  "/usr/sbin",
  "/sbin",
];

type ExtensionPreferences = {
  bPath?: string;
  baseDir?: string;
  openWith?: string;
  newSpaceCommand?: string;
  newProjectCommand?: string;
  focusCommand?: string;
  terminalBundleId?: string;
  timeoutMs?: string;
};

export type Config = {
  bPath: string;
  baseDir: string;
  envPath: string;
  openWith: "herdr" | "b";
  newSpaceCommand: string;
  newProjectCommand: string;
  focusCommand: string;
  terminalBundleId: string;
  timeoutMs: number;
};

function expandHome(value: string): string {
  return value === "~" || value.startsWith("~/")
    ? path.join(os.homedir(), value.slice(1))
    : value;
}

export function getConfig(): Config {
  const preferences = getPreferenceValues<ExtensionPreferences>();
  const bPath =
    preferences.bPath?.trim() || process.env.B_BIN || DEFAULT_B_PATH;
  const configuredTimeout = Number(preferences.timeoutMs || DEFAULT_TIMEOUT_MS);
  const timeoutMs =
    Number.isFinite(configuredTimeout) && configuredTimeout > 0
      ? configuredTimeout
      : DEFAULT_TIMEOUT_MS;
  const envPaths = bPath.includes("/")
    ? [path.dirname(bPath), ...COMMAND_PATHS]
    : COMMAND_PATHS;

  return {
    bPath,
    baseDir: expandHome(preferences.baseDir?.trim() || DEFAULT_BASE_DIR),
    envPath: [...new Set(envPaths)].join(":"),
    openWith: preferences.openWith === "b" ? "b" : "herdr",
    newSpaceCommand:
      preferences.newSpaceCommand?.trim() || DEFAULT_NEW_SPACE_COMMAND,
    newProjectCommand:
      preferences.newProjectCommand?.trim() || DEFAULT_NEW_PROJECT_COMMAND,
    focusCommand: preferences.focusCommand?.trim() ?? "",
    terminalBundleId:
      preferences.terminalBundleId?.trim() || DEFAULT_TERMINAL_BUNDLE,
    timeoutMs,
  };
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function commandEnv(config: Config): NodeJS.ProcessEnv {
  return { ...process.env, PATH: config.envPath };
}

export function herdrFor(config: Config): Herdr | undefined {
  return herdrRunning() ? herdrCli(commandEnv(config)) : undefined;
}

export function runB(config: Config, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      config.bPath,
      args,
      {
        env: commandEnv(config),
        maxBuffer: 2 * 1024 * 1024,
        timeout: config.timeoutMs,
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(stderr.trim() || error.message));
          return;
        }

        resolve(stdout);
      },
    );
  });
}

export function runBDetached(config: Config, args: string[]) {
  const child = spawn(config.bPath, args, {
    detached: true,
    env: commandEnv(config),
    stdio: "ignore",
  });
  child.once("error", (error) => {
    void showToast({
      style: Toast.Style.Failure,
      title: `b ${args[0]} failed`,
      message: errorMessage(error),
    });
  });
  child.unref();
}

export function runShell(config: Config, command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      "/bin/sh",
      ["-c", command],
      { env: commandEnv(config), timeout: 5_000 },
      (error, stdout) => (error ? reject(error) : resolve(stdout.trim())),
    );
  });
}

export async function runAction(title: string, action: () => Promise<string>) {
  const actionPromise = Promise.resolve().then(action);
  const toast = await showToast({ style: Toast.Style.Animated, title });

  try {
    const output = await actionPromise;
    toast.style = Toast.Style.Success;
    toast.title = title;
    toast.message = output || undefined;

    await showHUD(output || title);
  } catch (error) {
    toast.style = Toast.Style.Failure;
    toast.title = title;
    toast.message = errorMessage(error);
  }
}
