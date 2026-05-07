# TODO

## Feature: `custom_actions` command for adding log entries to notes

### Proposed action definition

```yaml
- id: add_log_to_note
  label: Add log to note
  scope: target
  note_command: add_log
```

`note_command` must be a fixed enum value. Invalid values must fail startup/config load.

## Functional requirements

1. Use the note path from `notes.path_template`.
2. Before opening the input dialog, validate all target note files that already exist.
   - Validation must confirm the file can be safely modified by this command.
   - Invalid files must be marked as skipped (with reason) and must not be modified.
   - Valid files continue in the operation.

3. If the note file does not exist, create it with:
   - `# <project name>` as H1
   - a `## Log` section
4. If `## Log` does not exist, append it at the end of the document.
5. Add a new log entry under `## Log` in this format:
   - `### <ISO8601 timestamp with timezone>`
   - blank line
   - user-provided text
6. Prompt the user with a multiline input box for log text.
7. If multiple projects are selected (select mode), write the same log text to all selected projects.
8. Timestamp format must be human-readable ISO 8601 with seconds, using local time including timezone offset.

## Validation and safety

1. Validate Markdown structure for all existing target files before opening the input dialog.
2. If validation fails for a file, do not modify that file.
3. Show a notification with a clear error message for each skipped file.
4. Validation must catch malformed or ambiguous structures (e.g. duplicate `## Log` sections).
5. The action may continue for valid files even if other selected files are skipped.

## Implementation constraints

1. Implement in pure Python.
2. Put Markdown edit logic in one dedicated module/file for now, ready to expand with future note-edit commands.

## Testing requirements

Add thorough tests for parsing, validation, and mutation. Include at least:

- valid note with existing `## Log`
- missing `## Log` (append at end)
- missing file (create from scratch)
- duplicate `## Log` (reject)
- malformed heading structure (reject)
- multi-project write behavior
- preservation of existing content outside the inserted log entry

Also include line-ending variants (`\n`, `\r\n`) and add broad negative/edge-case coverage.

## Example markdown

```md
# Projectname

## Log

### 2026-05-04T22:18:32+02:00

Text from log

### 2026-05-07T21:48:35+02:00

Some text here from inputbox
```
