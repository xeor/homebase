import {
  Action,
  ActionPanel,
  closeMainWindow,
  Color,
  getPreferenceValues,
  Icon,
  List,
  showHUD,
  showToast,
  Toast,
} from "@raycast/api";
import { execFile, spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fitRow, FitResult, Marker } from "./fit";
import {
  completeTag,
  filterItems,
  parseQuery,
  tagCounts,
  tagSuggestions,
} from "./query";
import {
  bestPane,
  createSpace,
  focusPane,
  Herdr,
  herdrCli,
  herdrRunning,
  panesByProject,
  ProjectPanes,
  typeCommand,
} from "./herdr";

const DEFAULT_B_PATH = "/Users/xeor/.local/bin/b";
const DEFAULT_BASE_DIR = "~/base";
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_NEW_SPACE_COMMAND = "b --open-mode shell_cd";
const DEFAULT_NEW_PROJECT_COMMAND = "b new";
const DEFAULT_TERMINAL_BUNDLE = "com.apple.Terminal";
// The daemon rewrites the snapshot at least every minute; older means it is not running.
const SNAPSHOT_STALE_S = 180;
const COMMAND_PATHS = [
  "/Users/xeor/.local/bin",
  "/opt/homebrew/bin",
  "/usr/local/bin",
  "/usr/bin",
  "/bin",
  "/usr/sbin",
  "/sbin",
];

type CommandPreferences = {
  bPath?: string;
  baseDir?: string;
  openWith?: string;
  newSpaceCommand?: string;
  newProjectCommand?: string;
  focusCommand?: string;
  terminalBundleId?: string;
  timeoutMs?: string;
};

type Config = {
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

type Project = {
  id: string;
  title: string;
  path: string;
  keywords: string[];
  tags: string[];
  subtitle?: string;
  actions: ProjectAction[];
};

type ProjectAction = {
  id: string;
  title: string;
};

type ListState = {
  error?: string;
  isLoading: boolean;
  projects: Project[];
};

function expandHome(value: string): string {
  return value === "~" || value.startsWith("~/")
    ? path.join(os.homedir(), value.slice(1))
    : value;
}

function getConfig(): Config {
  const preferences = getPreferenceValues<CommandPreferences>();
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

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function parseProjectActions(value: unknown): ProjectAction[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      if (
        typeof item === "object" &&
        item !== null &&
        "id" in item &&
        "title" in item
      ) {
        return {
          id: String(item.id),
          title: String(item.title),
        };
      }

      return undefined;
    })
    .filter((item): item is ProjectAction => Boolean(item?.id && item.title));
}

function parseStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.map((item) => String(item).trim()).filter(Boolean);
}

function parseProjects(parsed: unknown, baseDir: string): Project[] {
  if (!Array.isArray(parsed)) {
    return [];
  }

  return parsed
    .map((item, index) => {
      if (
        typeof item === "object" &&
        item !== null &&
        "project" in item &&
        "actions" in item
      ) {
        const title = String(item.project);
        const subtitle =
          "subtitle" in item && String(item.subtitle).trim()
            ? String(item.subtitle)
            : "";
        const projectPath =
          "path" in item && String(item.path)
            ? String(item.path)
            : path.join(baseDir, title);
        return {
          id: `${index}:${title}`,
          title,
          path: projectPath,
          keywords: parseStringList("keywords" in item ? item.keywords : []),
          tags: parseStringList("tags" in item ? item.tags : []),
          ...(subtitle ? { subtitle } : {}),
          actions: parseProjectActions(item.actions),
        };
      }

      return undefined;
    })
    .filter((item): item is Project => Boolean(item?.title && item.actions));
}

function commandEnv(config: Config): NodeJS.ProcessEnv {
  return { ...process.env, PATH: config.envPath };
}

function runB(config: Config, args: string[]): Promise<string> {
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

function runBDetached(config: Config, args: string[]) {
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

function runShell(config: Config, command: string): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      "/bin/sh",
      ["-c", command],
      { env: commandEnv(config), timeout: 5_000 },
      (error, stdout) => (error ? reject(error) : resolve(stdout.trim())),
    );
  });
}

// The project list file `b daemon` keeps current (`b integration raycast snapshot`).
function snapshotPath(config: Config): string {
  return path.join(config.baseDir, ".homebase", "runtime", "raycast.json");
}

async function readSnapshot(
  config: Config,
): Promise<{ projects: Project[]; ageS: number } | undefined> {
  try {
    const data = JSON.parse(await readFile(snapshotPath(config), "utf8"));
    if (typeof data !== "object" || data === null || data.version !== 1) {
      return undefined;
    }
    return {
      projects: parseProjects(data.projects, config.baseDir),
      ageS: Date.now() / 1000 - Number(data.generated_ts || 0),
    };
  } catch {
    return undefined;
  }
}

async function runAction(title: string, action: () => Promise<string>) {
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

// Bring the herdr terminal window to the front: the focus command (Hammerspoon
// pair.focusTerminal) when set, else (or when it fails) the terminal app.
async function focusTerminal(config: Config) {
  if (config.focusCommand) {
    try {
      if ((await runShell(config, config.focusCommand)) !== "false") {
        return;
      }
    } catch {
      // fall through to activating the app
    }
  }
  await runShell(config, `open -b '${config.terminalBundleId}'`).catch(
    () => undefined,
  );
}

function herdrFor(config: Config): Herdr | undefined {
  return herdrRunning() ? herdrCli(commandEnv(config)) : undefined;
}

async function openInHerdr(
  config: Config,
  herdr: Herdr,
  project: Project,
  panes: ProjectPanes | undefined,
  forceNew: boolean,
) {
  const pane = forceNew || !panes ? undefined : bestPane(panes, project.title);
  const herdrDone = pane
    ? focusPane(herdr, pane)
    : createSpace(herdr, project.path, project.title);
  await Promise.all([herdrDone, closeMainWindow({ clearRootSearch: true })]);
  await focusTerminal(config);
  runBDetached(config, ["integration", "raycast", "opened", project.title]);
}

async function openProject(
  config: Config,
  project: Project,
  panes: ProjectPanes | undefined,
  forceNew = false,
) {
  const herdr = config.openWith === "herdr" ? herdrFor(config) : undefined;
  if (!herdr) {
    runBDetached(config, ["open", project.title]);
    await closeMainWindow({ clearRootSearch: true });
    return;
  }
  try {
    await openInHerdr(config, herdr, project, panes, forceNew);
  } catch (error) {
    await showToast({
      style: Toast.Style.Failure,
      title: "herdr open failed",
      message: errorMessage(error),
    });
  }
}

// A new herdr space in the base folder running `command`: the b picker
// (same as ⌘N in herdr) or b's new-project popup.
async function newSpaceWithB(config: Config, command: string) {
  const herdr = herdrFor(config);
  if (!herdr) {
    await showToast({
      style: Toast.Style.Failure,
      title: "herdr is not running",
    });
    return;
  }
  try {
    const paneId = await createSpace(herdr, config.baseDir);
    await Promise.all([
      typeCommand(herdr, paneId, command),
      closeMainWindow({ clearRootSearch: true }),
    ]);
    await focusTerminal(config);
  } catch (error) {
    await showToast({
      style: Toast.Style.Failure,
      title: "new space failed",
      message: errorMessage(error),
    });
  }
}

// The top items, searchable like projects.
const FIND_SPACE_SEARCHABLE = {
  title: "Find Space with b",
  keywords: ["open", "find", "space", "herdr", "b"],
  tags: [],
};
const NEW_PROJECT_SEARCHABLE = {
  title: "New Project with b",
  keywords: ["new", "create", "project", "space", "herdr", "b"],
  tags: [],
};

const AGENT_COLORS: Record<string, Color> = {
  working: Color.Yellow,
  blocked: Color.Red,
  done: Color.Green,
  idle: Color.SecondaryText,
};

// Most urgent agent state first: it colors the one "AI" pill.
const AGENT_ORDER = ["blocked", "working", "done", "idle", "unknown"];

function agentState(panes: ProjectPanes): string {
  const states = panes.agents.map((a) => a.status);
  return AGENT_ORDER.find((s) => states.includes(s)) ?? "unknown";
}

function agentLabel(panes: ProjectPanes): string {
  return panes.agents.length > 1 ? `AI ${panes.agents.length}` : "AI";
}

function markers(panes: ProjectPanes | undefined): Marker[] {
  if (!panes) {
    return [];
  }
  const out: Marker[] = [];
  if (panes.agents.length) {
    out.push({ kind: "pill", text: agentLabel(panes) });
  }
  out.push({ kind: "count", text: String(panes.panes.length) });
  return out;
}

// Small pills on the right: project tags (#tag, "+N" for the rest), then the
// herdr markers (agents as "AI", pane count), which are never dropped.
function itemAccessories(
  fit: FitResult,
  panes: ProjectPanes | undefined,
): List.Item.Accessory[] {
  const out: List.Item.Accessory[] = fit.tags.map((tag) => ({
    tag: { value: `#${tag}`, color: Color.Purple },
  }));
  if (fit.hiddenTags.length) {
    out.push({
      tag: { value: `+${fit.hiddenTags.length}`, color: Color.Purple },
      tooltip: fit.hiddenTags.map((t) => `#${t}`).join(" "),
    });
  }
  if (!panes) {
    return out;
  }
  if (panes.agents.length) {
    out.push({
      tag: {
        value: agentLabel(panes),
        color: AGENT_COLORS[agentState(panes)] ?? Color.SecondaryText,
      },
      tooltip: panes.agents.map((a) => `${a.name}: ${a.status}`).join(", "),
    });
  }
  out.push({
    icon: { source: Icon.Terminal, tintColor: Color.Green },
    text: String(panes.panes.length),
    tooltip: `Open in herdr: ${panes.workspaces.join(", ")} (${panes.panes.length} panes)`,
  });
  return out;
}

function ProjectListItem({
  config,
  onRefresh,
  project,
  panes,
}: {
  config: Config;
  onRefresh: () => void;
  project: Project;
  panes: ProjectPanes | undefined;
}) {
  const visibleActions = project.actions.filter(
    (action) => action.id !== "open_selected",
  );
  const useHerdr = config.openWith === "herdr";
  const fit = fitRow({
    title: project.title,
    subtitle: project.subtitle ?? "",
    tags: project.tags,
    markers: markers(panes),
  });

  return (
    <List.Item
      key={project.id}
      icon={Icon.Folder}
      title={fit.title}
      subtitle={fit.subtitle}
      keywords={project.keywords}
      accessories={itemAccessories(fit, panes)}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action
              icon={Icon.Terminal}
              title={panes && useHerdr ? "Go to Space" : "Open"}
              onAction={() => openProject(config, project, panes)}
            />
            {useHerdr && panes ? (
              <Action
                icon={Icon.Plus}
                title="Open in New Space"
                shortcut={{ modifiers: ["cmd"], key: "return" }}
                onAction={() => openProject(config, project, panes, true)}
              />
            ) : null}
            {visibleActions.map((action) => (
              <Action
                key={action.id}
                icon={Icon.Gear}
                title={action.title}
                onAction={() =>
                  runAction(action.title, () =>
                    runB(config, [
                      "integration",
                      "raycast",
                      "run",
                      action.id,
                      project.title,
                    ]),
                  )
                }
              />
            ))}
          </ActionPanel.Section>
          <Action
            icon={Icon.ArrowClockwise}
            title="Refresh"
            shortcut={{ modifiers: ["cmd"], key: "r" }}
            onAction={onRefresh}
          />
        </ActionPanel>
      }
    />
  );
}

export default function Command() {
  const config = useMemo(getConfig, []);
  const requestId = useRef(0);
  const [state, setState] = useState<ListState>({
    isLoading: true,
    projects: [],
  });
  const [openPanes, setOpenPanes] = useState<Map<string, ProjectPanes>>(
    new Map(),
  );
  const [searchText, setSearchText] = useState("");
  const query = useMemo(() => parseQuery(searchText), [searchText]);
  const counts = useMemo(() => tagCounts(state.projects), [state.projects]);
  const visible = useMemo(
    () => filterItems(state.projects, query),
    [state.projects, query],
  );
  const suggestions = useMemo(
    () => tagSuggestions(query, counts),
    [query, counts],
  );
  const topItems = query.tagTerms.length
    ? []
    : filterItems([FIND_SPACE_SEARCHABLE, NEW_PROJECT_SEARCHABLE], query);

  const loadOpenPanes = useCallback(
    async (projects: Project[]) => {
      const herdr = herdrFor(config);
      if (!herdr) {
        return;
      }
      try {
        setOpenPanes(
          await panesByProject(
            herdr,
            projects.map((p) => p.path),
          ),
        );
      } catch {
        setOpenPanes(new Map());
      }
    },
    [config],
  );

  const loadProjects = useCallback(
    async (fromB = false) => {
      const id = requestId.current + 1;
      requestId.current = id;
      setState((current) => ({
        ...current,
        error: undefined,
        isLoading: true,
      }));

      // Fast path: the daemon's snapshot file, no b process.
      const snapshot = fromB ? undefined : await readSnapshot(config);
      if (snapshot && id === requestId.current) {
        const fresh = snapshot.ageS < SNAPSHOT_STALE_S;
        setState({ isLoading: !fresh, projects: snapshot.projects });
        void loadOpenPanes(snapshot.projects);
        if (fresh) {
          return;
        }
      }

      try {
        // No daemon (or a stale snapshot): let b write the file, then read it.
        await runB(config, ["integration", "raycast", "snapshot"]);
        const rebuilt = await readSnapshot(config);
        const projects =
          rebuilt?.projects ??
          parseProjects(
            JSON.parse(
              await runB(config, ["integration", "raycast", "projects"]),
            ),
            config.baseDir,
          );
        if (id !== requestId.current) {
          return;
        }
        setState({ isLoading: false, projects });
        void loadOpenPanes(projects);
      } catch (error) {
        if (id !== requestId.current) {
          return;
        }
        const message = errorMessage(error);
        setState((current) => ({
          error: current.projects.length ? undefined : message,
          isLoading: false,
          projects: current.projects,
        }));
        await showToast({
          style: Toast.Style.Failure,
          title: "b project list failed",
          message,
        });
      }
    },
    [config, loadOpenPanes],
  );

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  return (
    <List
      isLoading={state.isLoading}
      filtering={false}
      searchText={searchText}
      onSearchTextChange={setSearchText}
      searchBarPlaceholder="Search projects, #tag, -#tag"
      actions={
        <ActionPanel>
          <Action
            icon={Icon.ArrowClockwise}
            title="Refresh"
            onAction={() => loadProjects(true)}
          />
        </ActionPanel>
      }
    >
      {state.error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="b project list failed"
          description={state.error}
        />
      ) : null}
      {!state.error && !state.isLoading && state.projects.length === 0 ? (
        <List.EmptyView
          icon={Icon.MagnifyingGlass}
          title="No projects"
          description="b integration raycast projects returned no output"
        />
      ) : null}
      {suggestions.length ? (
        <List.Section title="Tags" subtitle="Enter completes">
          {suggestions.map((s) => (
            <List.Item
              key={`tag:${s.tag}`}
              icon={{ source: Icon.Tag, tintColor: Color.Purple }}
              title={`${query.typingTag?.prefix ?? "#"}${s.tag}`}
              accessories={[{ text: String(s.count) }]}
              actions={
                <ActionPanel>
                  <Action
                    icon={Icon.Tag}
                    title="Complete Tag"
                    onAction={() =>
                      setSearchText(completeTag(searchText, query, s.tag))
                    }
                  />
                </ActionPanel>
              }
            />
          ))}
        </List.Section>
      ) : null}
      {state.error
        ? null
        : topItems.map((item) =>
            item === FIND_SPACE_SEARCHABLE ? (
              <List.Item
                key="find-space"
                icon={{ source: Icon.MagnifyingGlass, tintColor: Color.Blue }}
                title={item.title}
                subtitle="new herdr space, b picker"
                keywords={item.keywords}
                actions={
                  <ActionPanel>
                    <Action
                      icon={Icon.MagnifyingGlass}
                      title="Open Space with B Picker"
                      onAction={() =>
                        newSpaceWithB(config, config.newSpaceCommand)
                      }
                    />
                  </ActionPanel>
                }
              />
            ) : (
              <List.Item
                key="new-project"
                icon={{ source: Icon.Plus, tintColor: Color.Blue }}
                title={item.title}
                subtitle="new herdr space, b new-project popup"
                keywords={item.keywords}
                actions={
                  <ActionPanel>
                    <Action
                      icon={Icon.Plus}
                      title="Create Project in New Space"
                      onAction={() =>
                        newSpaceWithB(config, config.newProjectCommand)
                      }
                    />
                  </ActionPanel>
                }
              />
            ),
          )}
      {visible.map((project) => (
        <ProjectListItem
          key={project.id}
          config={config}
          onRefresh={() => loadProjects(true)}
          project={project}
          panes={openPanes.get(project.path)}
        />
      ))}
    </List>
  );
}
