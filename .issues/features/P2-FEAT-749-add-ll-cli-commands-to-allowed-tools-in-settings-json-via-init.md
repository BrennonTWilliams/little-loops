---
id: FEAT-749
priority: P2
type: FEAT
status: active
discovered_date: 2026-03-14
discovered_by: capture-issue
---

# FEAT-749: Add ll- CLI Commands to Allowed Tools in settings.json via Init

## Overview

Extend `/ll:init` (and the `ll-config.json` setup flow) to optionally populate the Claude Code `permissions.allow` list in `.claude/settings.json` or `.claude/settings.local.json` with Bash entries for each `ll-` CLI command, using flags optimized for AI coding agent usage.

## Motivation

Currently users must manually add `ll-` CLI commands to their `permissions.allow` list. This creates friction during setup and leads to inconsistent tool authorization across projects. The `ll-` commands are first-class citizens of the little-loops workflow and should be pre-authorized as part of init without requiring manual knowledge of each command's optimal invocation pattern.

## Use Case

A user runs `/ll:init` on a new project. At the end of the flow, little-loops detects whether `.claude/settings.json` or `.claude/settings.local.json` exists, asks which file to update (or offers to skip), and writes the recommended `permissions.allow` entries — each with the right glob pattern for agent use.

## Acceptance Criteria

1. `/ll:init` detects existing settings files (`.claude/settings.json`, `.claude/settings.local.json`)
2. If neither exists, `AskUserQuestion` prompts user to create one or skip
3. If one or both exist, prompt user which to update (or skip)
4. Writes `Bash(ll-<cmd> <optimal-flags>:*)` allow entries without overwriting unrelated entries
5. Optimal flags are chosen per-command for AI agent use (structured output, non-interactive, no confirmation prompts)
6. Idempotent: re-running init does not duplicate existing entries

## Implementation Steps

### Step 1: Determine Optimal Flag Patterns per Command

Based on `-h` output, the recommended `permissions.allow` Bash patterns for agent use:

```json
"Bash(ll-issues next-id:*)",
"Bash(ll-issues list:*)",
"Bash(ll-issues show:*)",
"Bash(ll-issues count:*)",
"Bash(ll-issues sequence:*)",
"Bash(ll-issues search:*)",
"Bash(ll-issues refine-status:*)",
"Bash(ll-issues append-log:*)",
"Bash(ll-issues impact-effort:*)",
"Bash(ll-auto --dry-run:*)",
"Bash(ll-auto --quiet:*)",
"Bash(ll-auto:*)",
"Bash(ll-parallel --dry-run:*)",
"Bash(ll-parallel --cleanup:*)",
"Bash(ll-parallel:*)",
"Bash(ll-sprint create:*)",
"Bash(ll-sprint run:*)",
"Bash(ll-sprint list:*)",
"Bash(ll-sprint show:*)",
"Bash(ll-sprint edit:*)",
"Bash(ll-sprint analyze:*)",
"Bash(ll-loop run:*)",
"Bash(ll-loop validate:*)",
"Bash(ll-loop list:*)",
"Bash(ll-loop status:*)",
"Bash(ll-loop history:*)",
"Bash(ll-loop show:*)",
"Bash(ll-loop simulate:*)",
"Bash(ll-loop test:*)",
"Bash(ll-messages:*)",
"Bash(ll-messages --stdout:*)",
"Bash(ll-history summary:*)",
"Bash(ll-history analyze:*)",
"Bash(ll-history export:*)",
"Bash(ll-deps analyze:*)",
"Bash(ll-deps validate:*)",
"Bash(ll-deps fix --dry-run:*)",
"Bash(ll-sync status:*)",
"Bash(ll-sync push:*)",
"Bash(ll-sync pull:*)",
"Bash(ll-sync diff:*)",
"Bash(ll-verify-docs:*)",
"Bash(ll-check-links:*)"
```

Note: Broad `Bash(ll-<cmd>:*)` patterns cover all subcommand/flag combinations. The list above uses subcommand-specific entries where the tool is commonly called with specific subcommands.

**Alternative (simpler)**: A single wildcard per binary: `Bash(ll-issues:*)`, `Bash(ll-auto:*)`, etc. — covers all usage with one entry each. Preferred for maintainability; subcommand-level granularity only if the project's security posture requires it.

### Step 2: Settings File Detection Logic (in init skill)

```
1. Check .claude/settings.json exists
2. Check .claude/settings.local.json exists
3. Determine action:
   a. Neither exists → AskUserQuestion: "Create settings.local.json, settings.json, or skip?"
   b. One exists → AskUserQuestion: "Add ll- commands to <file>? (y/n/skip)"
   c. Both exist → AskUserQuestion: "Add ll- commands to settings.local.json, settings.json, or skip?"
```

### Step 3: Merge Logic

- Read existing JSON (or start with `{"permissions": {"allow": [], "deny": []}}`)
- Filter out any existing `ll-` entries (for idempotency)
- Append the canonical `ll-` allow list
- Write back with 2-space indent

### Step 4: Integration Points

- **`/ll:init`**: Add as a final optional step after config file creation (similar to how `.gitignore` suggestions work)
- **`/ll:configure`**: Add a new `configure allowed-tools` sub-option that can run standalone

## API / Interface Changes

No config-schema.json changes needed — this operates on `.claude/settings.json` / `.claude/settings.local.json` which are Claude Code's native settings files, not ll-config.json.

Optional: add a `cli.allowed_tools_hint` boolean to `ll-config.json` to suppress the prompt on future init runs once the user has made their choice.

## Files Likely Touched

- `skills/init/SKILL.md` — add new final phase for allowed-tools
- `skills/init/interactive.md` — new Round 8 for allowed-tools opt-in
- `skills/configure/SKILL.md` — add `allowed-tools` configure option

## Dependencies

None.

## Session Log
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92f6d283-84cd-41ed-b8d5-c0319fe66f82.jsonl`
