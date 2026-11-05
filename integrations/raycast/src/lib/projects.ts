import { readFile } from "node:fs/promises";
import path from "node:path";
import { Config, runB } from "./config";

export type ProjectAction = {
  id: string;
  title: string;
};

export type Project = {
  id: string;
  title: string;
  path: string;
  keywords: string[];
  tags: string[];
  subtitle?: string;
  actions: ProjectAction[];
};

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

// The project list file `b daemon` keeps current (`b integration raycast snapshot`).
function snapshotPath(config: Config): string {
  return path.join(config.baseDir, ".homebase", "runtime", "raycast.json");
}

export async function readSnapshot(
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

// No daemon (or a stale snapshot): let b write the file, then read it.
export async function projectsFromB(config: Config): Promise<Project[]> {
  await runB(config, ["integration", "raycast", "snapshot"]);
  const rebuilt = await readSnapshot(config);
  return (
    rebuilt?.projects ??
    parseProjects(
      JSON.parse(await runB(config, ["integration", "raycast", "projects"])),
      config.baseDir,
    )
  );
}

export function runProjectAction(
  config: Config,
  action: ProjectAction,
  project: Project,
): Promise<string> {
  return runB(config, [
    "integration",
    "raycast",
    "run",
    action.id,
    project.title,
  ]);
}
