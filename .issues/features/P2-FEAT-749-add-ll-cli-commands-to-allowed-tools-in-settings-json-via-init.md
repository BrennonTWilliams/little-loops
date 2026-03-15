---
id: FEAT-749
priority: P2
type: FEAT
status: active
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 78
---

# FEAT-749: Add ll- CLI Commands to Allowed Tools in settings.json via Init

## Summary

Extend `/ll:init` (and the `ll-config.json` setup flow) to optionally populate the Claude Code `permissions.allow` list in `.claude/settings.json` or `.claude/settings.local.json` with Bash entries for each `ll-` CLI command, using flags optimized for AI coding agent usage.

## Current Behavior

Users must manually add `ll-` CLI commands to their `permissions.allow` list in `.claude/settings.json` or `.claude/settings.local.json`. There is no automated or guided process in `/ll:init` to populate these entries, requiring users to know the correct Bash glob patterns for each command.

## Expected Behavior

After running `/ll:init`, users are prompted to optionally add recommended `ll-` CLI command allow entries to their Claude Code settings file. The init flow detects existing settings files, asks which to update (or to skip), and writes idempotent `Bash(ll-<cmd>:*)` allow entries alongside existing entries without overwriting unrelated configuration.

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
"Bash(ll-workflows:*)",
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

### Step 2: Settings File Detection Logic (in init skill, as new Step 10 in SKILL.md before current "Display Completion Message")

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

## API/Interface

No config-schema.json changes needed — this operates on `.claude/settings.json` / `.claude/settings.local.json` which are Claude Code's native settings files, not ll-config.json.

Optional: add a `cli.allowed_tools_hint` boolean to `ll-config.json` to suppress the prompt on future init runs once the user has made their choice.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add new final phase for allowed-tools
- `skills/init/interactive.md` — new Round 11 for allowed-tools opt-in (Rounds 8–10 already exist for Project Advanced, Continuation, and Prompt Optimization)
- `skills/configure/SKILL.md` — add `allowed-tools` configure option

### Dependent Files (Callers/Importers)
- N/A — init skill is invoked directly by user, no programmatic callers

### Similar Patterns
- `skills/init/SKILL.md` Step 9 (`.gitignore` update step) — follow same detection-and-append pattern (check if entries exist, append only if absent)

### Tests
- TBD — identify integration test for settings file detection and merge logic

### Documentation
- `docs/reference/API.md` — if `cli.allowed_tools_hint` config key is added, document it
- `commands/init.md` — update with new allowed-tools phase description

### Configuration
- `.claude/settings.json` / `.claude/settings.local.json` — written by this feature (Claude Code native files)
- Optional: `ll-config.json` `cli.allowed_tools_hint` boolean to suppress prompt on future runs

## Dependencies

None.

## Impact

- **Priority**: P2 — Reduces setup friction for new projects; not blocking but improves first-run experience meaningfully
- **Effort**: Small — Additive change to existing init skill flow; reuses existing JSON merge patterns
- **Risk**: Low — No breaking changes; purely additive; init is a user-triggered one-time flow
- **Breaking Change**: No

## Labels

`feature`, `init`, `configure`, `ux`

## Status

**Open** | Created: 2026-03-14 | Priority: P2

## Verification Notes

_Verified 2026-03-15 by /ll:verify-issues_

**Verdict**: NEEDS_UPDATE — corrections applied.

**Corrections made:**
1. **Round numbering**: `interactive.md` already has Rounds 8 (Project Advanced), 9 (Continuation), 10 (Prompt Optimization). New allowed-tools round corrected to Round 11 in Integration Map and Implementation Steps.
2. **Similar Patterns reference**: "Round 7 (.gitignore suggestions step)" was wrong — Round 7 is "Extended Config Gate (Auto-Skipped)". The `.gitignore` logic lives in `SKILL.md` Step 9. Corrected to reference Step 9 pattern.
3. **Missing CLI command**: `ll-workflows` (entry point in `scripts/pyproject.toml`) was absent from the allow list. Added.

**Confirmed accurate:**
- All 3 referenced files exist: `skills/init/SKILL.md`, `skills/init/interactive.md`, `skills/configure/SKILL.md`
- Current behavior claim is accurate: no `permissions.allow` logic exists in init skill
- `/ll:configure` does not have an `allowed-tools` area (confirmed from configure/SKILL.md)
- Feature is not yet implemented; issue remains valid and actionable

## Session Log
- `/ll:verify-issues` - 2026-03-15T18:54:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T18:51:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92f6d283-84cd-41ed-b8d5-c0319fe66f82.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
