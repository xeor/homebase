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
  /** Command Timeout - Timeout in milliseconds */
  "timeoutMs": string
}
}

declare namespace Arguments {
  /** Arguments passed to the `projects` command */
  export type Projects = {}
}

