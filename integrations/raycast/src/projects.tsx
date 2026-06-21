import {
  Action,
  ActionPanel,
  closeMainWindow,
  getPreferenceValues,
  Icon,
  List,
  showHUD,
  showToast,
  Toast,
} from "@raycast/api";
import { execFile, spawn } from "node:child_process";
import path from "node:path";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const DEFAULT_B_PATH = "/Users/xeor/.local/bin/b";
const DEFAULT_TIMEOUT_MS = 10_000;
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
  timeoutMs?: string;
};

type Config = {
  bPath: string;
  envPath: string;
  timeoutMs: number;
};

type Project = {
  id: string;
  title: string;
  keywords: string[];
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
    envPath: [...new Set(envPaths)].join(":"),
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

function parseProjects(output: string): Project[] {
  const parsed = JSON.parse(output) as unknown;
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
        return {
          id: `${index}:${title}`,
          title,
          keywords: parseStringList("keywords" in item ? item.keywords : []),
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
      title: "b open failed",
      message: errorMessage(error),
    });
  });
  child.unref();
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

async function openProject(config: Config, project: Project) {
  runBDetached(config, ["open", project.title]);
  await closeMainWindow({ clearRootSearch: true });
}

function ProjectListItem({
  config,
  onRefresh,
  project,
  projectActions,
}: {
  config: Config;
  onRefresh: () => void;
  project: Project;
  projectActions: ProjectAction[];
}) {
  const visibleActions = projectActions.filter(
    (action) => action.id !== "open_selected",
  );

  return (
    <List.Item
      key={project.id}
      icon={Icon.Folder}
      title={project.title}
      subtitle={project.subtitle}
      keywords={project.keywords}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action
              icon={Icon.Terminal}
              title="Open"
              onAction={() => openProject(config, project)}
            />
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

  const loadProjects = useCallback(async () => {
    const id = requestId.current + 1;
    requestId.current = id;
    setState((current) => ({
      ...current,
      error: undefined,
      isLoading: true,
    }));

    try {
      const args = ["integration", "raycast", "projects"];
      const output = await runB(config, args);
      if (id !== requestId.current) {
        return;
      }
      const projects = parseProjects(output);
      setState({ isLoading: false, projects });
    } catch (error) {
      if (id !== requestId.current) {
        return;
      }
      const message = errorMessage(error);
      setState({ error: message, isLoading: false, projects: [] });
      await showToast({
        style: Toast.Style.Failure,
        title: "b ls failed",
        message,
      });
    }
  }, [config]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  return (
    <List
      isLoading={state.isLoading}
      filtering
      searchBarPlaceholder="Search projects"
      actions={
        <ActionPanel>
          <Action
            icon={Icon.ArrowClockwise}
            title="Refresh"
            onAction={() => loadProjects()}
          />
        </ActionPanel>
      }
    >
      {state.error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="b ls failed"
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
      {state.projects.map((project) => (
        <ProjectListItem
          key={project.id}
          config={config}
          onRefresh={() => loadProjects()}
          project={project}
          projectActions={project.actions}
        />
      ))}
    </List>
  );
}
