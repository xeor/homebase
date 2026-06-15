import {
  Action,
  ActionPanel,
  getPreferenceValues,
  Icon,
  List,
  showHUD,
  showToast,
  Toast,
} from "@raycast/api";
import { execFile } from "node:child_process";
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
};

type ProjectAction = {
  id: string;
  title: string;
};

type ProjectActionSet = {
  project: string;
  actions: ProjectAction[];
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

function parseProjects(output: string): Project[] {
  return output
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((title, index) => ({ id: `${index}:${title}`, title }));
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

function parseProjectActionSets(output: string): ProjectActionSet[] {
  const parsed = JSON.parse(output) as unknown;
  if (!Array.isArray(parsed)) {
    return [];
  }

  return parsed
    .map((item) => {
      if (
        typeof item === "object" &&
        item !== null &&
        "project" in item &&
        "actions" in item
      ) {
        return {
          project: String(item.project),
          actions: parseProjectActions(item.actions),
        };
      }

      return undefined;
    })
    .filter((item): item is ProjectActionSet =>
      Boolean(item?.project && item.actions),
    );
}

function runB(config: Config, args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      config.bPath,
      args,
      {
        env: { ...process.env, PATH: config.envPath },
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

async function runAction(title: string, action: () => Promise<string>) {
  const toast = await showToast({ style: Toast.Style.Animated, title });

  try {
    const output = await action();
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
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action
              icon={Icon.Terminal}
              title="Open"
              onAction={() =>
                runAction(`b open ${project.title}`, () =>
                  runB(config, ["open", project.title]),
                )
              }
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
  const [searchText, setSearchText] = useState("");
  const [actionsByProject, setActionsByProject] = useState<
    Record<string, ProjectAction[]>
  >({});
  const [state, setState] = useState<ListState>({
    isLoading: true,
    projects: [],
  });

  const loadActionsForProjects = useCallback(
    async (id: number, projects: Project[]) => {
      try {
        const output = await runB(config, [
          "integration",
          "raycast",
          "actions",
        ]);
        if (id !== requestId.current) {
          return;
        }

        const actionSets = parseProjectActionSets(output);
        const actionsByName = new Map(
          actionSets.map((item) => [item.project, item.actions]),
        );
        const entries = projects.map(
          (project) =>
            [project.id, actionsByName.get(project.title) || []] as const,
        );
        setActionsByProject(Object.fromEntries(entries));
      } catch {
        if (id === requestId.current) {
          setActionsByProject({});
        }
      }
    },
    [config],
  );

  const loadProjects = useCallback(
    async (filterExpr: string) => {
      const id = requestId.current + 1;
      requestId.current = id;
      setActionsByProject({});
      setState((current) => ({
        ...current,
        error: undefined,
        isLoading: true,
      }));

      try {
        const args = ["ls"];
        const filter = filterExpr.trim();
        if (filter) {
          args.push(filter);
        }

        const output = await runB(config, args);
        if (id !== requestId.current) {
          return;
        }
        const projects = parseProjects(output);
        setState({ isLoading: false, projects });
        void loadActionsForProjects(id, projects);
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
    },
    [config, loadActionsForProjects],
  );

  useEffect(() => {
    void loadProjects(searchText);
  }, [loadProjects, searchText]);

  return (
    <List
      isLoading={state.isLoading}
      filtering={false}
      throttle
      searchText={searchText}
      searchBarPlaceholder="Homebase filter expression"
      onSearchTextChange={setSearchText}
      actions={
        <ActionPanel>
          <Action
            icon={Icon.ArrowClockwise}
            title="Refresh"
            onAction={() => loadProjects(searchText)}
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
          description={
            searchText.trim()
              ? `No projects match ${searchText.trim()}`
              : "b ls returned no output"
          }
        />
      ) : null}
      {state.projects.map((project) => (
        <ProjectListItem
          key={project.id}
          config={config}
          onRefresh={() => loadProjects(searchText)}
          project={project}
          projectActions={actionsByProject[project.id] || []}
        />
      ))}
    </List>
  );
}
