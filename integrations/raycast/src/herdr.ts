// herdr through its CLI (`herdr <group> <command>` prints JSON).
// Not the socket directly: the server stalls ~100 ms on a connection whose request
// is not there the moment it accepts, which Node's async connect usually hits.
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import os from "node:os";
import path from "node:path";

const CALL_TIMEOUT_MS = 3_000;

export type HerdrPane = {
  pane_id: string;
  tab_id: string;
  workspace_id: string;
  cwd: string;
  foreground_cwd?: string;
  focused?: boolean;
  agent?: string;
  agent_status?: string;
};

export type HerdrWorkspace = {
  workspace_id: string;
  label?: string;
  focused?: boolean;
};

export type ProjectPane = HerdrPane & { label: string };

export type ProjectPanes = {
  panes: ProjectPane[];
  workspaces: string[];
  agents: { name: string; status: string }[];
};

export type Herdr = (args: string[]) => Promise<Record<string, unknown>>;

// True when a herdr server is listening (its socket exists).
export function herdrRunning(): boolean {
  const socket =
    process.env.HERDR_SOCKET_PATH ||
    path.join(os.homedir(), ".config", "herdr", "herdr.sock");
  return existsSync(socket);
}

export function herdrCli(env: NodeJS.ProcessEnv): Herdr {
  return (args) =>
    new Promise((resolve, reject) => {
      execFile(
        "herdr",
        args,
        { env, timeout: CALL_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 },
        (error, stdout, stderr) => {
          if (error) {
            reject(
              new Error(
                `herdr ${args.slice(0, 2).join(" ")}: ${errorText(stderr) || error.message}`,
              ),
            );
            return;
          }
          try {
            resolve(stdout.trim() ? (JSON.parse(stdout).result ?? {}) : {});
          } catch (parseError) {
            reject(parseError);
          }
        },
      );
    });
}

function errorText(stderr: string): string {
  try {
    const parsed = JSON.parse(stderr);
    return String(parsed.error?.message || parsed.error?.code || stderr).trim();
  } catch {
    return stderr.trim();
  }
}

function isUnder(dir: string, root: string): boolean {
  return dir === root || dir.startsWith(root.endsWith("/") ? root : root + "/");
}

// Panes per project path (deepest matching project wins, like b's pane probe).
export async function panesByProject(
  herdr: Herdr,
  projectPaths: string[],
): Promise<Map<string, ProjectPanes>> {
  const [paneList, workspaceList] = await Promise.all([
    herdr(["pane", "list"]),
    herdr(["workspace", "list"]),
  ]);
  const panes = (paneList.panes ?? []) as HerdrPane[];
  const workspaces = (workspaceList.workspaces ?? []) as HerdrWorkspace[];
  const labels = new Map(
    workspaces.map((w) => [w.workspace_id, w.label || w.workspace_id]),
  );
  const roots = [...projectPaths].sort((a, b) => b.length - a.length);
  const out = new Map<string, ProjectPanes>();
  for (const pane of panes) {
    const cwd = pane.foreground_cwd || pane.cwd;
    const root = cwd ? roots.find((r) => isUnder(cwd, r)) : undefined;
    if (!root) {
      continue;
    }
    const entry = out.get(root) ?? { panes: [], workspaces: [], agents: [] };
    const label = labels.get(pane.workspace_id) ?? pane.workspace_id;
    entry.panes.push({ ...pane, label });
    if (!entry.workspaces.includes(label)) {
      entry.workspaces.push(label);
    }
    if (pane.agent) {
      entry.agents.push({
        name: pane.agent,
        status: pane.agent_status || "unknown",
      });
    }
    out.set(root, entry);
  }
  return out;
}

// The pane to jump to: one in a workspace named after the project, else the first.
export function bestPane(
  entry: ProjectPanes,
  projectName: string,
): ProjectPane | undefined {
  return entry.panes.find((p) => p.label === projectName) ?? entry.panes[0];
}

// Focus the tab holding the pane (switches workspace too).
export async function focusPane(herdr: Herdr, pane: HerdrPane): Promise<void> {
  await herdr(["tab", "focus", pane.tab_id]);
}

export async function createSpace(
  herdr: Herdr,
  cwd: string,
  label?: string,
): Promise<string> {
  const args = ["workspace", "create", "--cwd", cwd, "--focus"];
  if (label) {
    args.push("--label", label);
  }
  const result = await herdr(args);
  const root = result.root_pane as { pane_id?: string } | undefined;
  return root?.pane_id ?? "";
}

// Type a command into a pane and press Enter (herdr has no create --command).
export async function typeCommand(
  herdr: Herdr,
  paneId: string,
  command: string,
): Promise<void> {
  await herdr(["pane", "send-text", paneId, command]);
  await herdr(["pane", "send-keys", paneId, "enter"]);
}
