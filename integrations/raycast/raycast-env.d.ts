/// <reference types="@raycast/api">

/* 🚧 🚧 🚧
 * This file is auto-generated from the extension's manifest.
 * Do not modify manually. Instead, update the `package.json` file.
 * 🚧 🚧 🚧 */

/* eslint-disable @typescript-eslint/ban-types */

type ExtensionPreferences = {}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `projects` command */
  export type Projects = ExtensionPreferences & {
  /** b Path - Path to the b executable */
  "bPath": string,
  /** Base Folder - Homebase base folder (b daemon writes .homebase/runtime/raycast.json there) */
  "baseDir": string,
  /** Open With - herdr space: go to the project's herdr space or open a new one. b open: Homebase open mode. */
  "openWith": "herdr" | "b",
  /** New Space Command - Typed into a new herdr space by the Find Space item */
  "newSpaceCommand": string,
  /** New Project Command - Typed into a new herdr space by the New Project item */
  "newProjectCommand": string,
  /** Focus Command - Shell command that brings the herdr terminal to the front; prints false or fails to fall back to activating the terminal app */
  "focusCommand": string,
  /** Terminal App - Bundle id of the terminal that runs herdr */
  "terminalBundleId": string,
  /** Command Timeout - Timeout in milliseconds */
  "timeoutMs": string
}
}

declare namespace Arguments {
  /** Arguments passed to the `projects` command */
  export type Projects = {}
}

