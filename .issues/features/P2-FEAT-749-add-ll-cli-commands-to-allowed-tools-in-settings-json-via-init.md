---
id: FEAT-749
priority: P2
type: FEAT
status: active
discovered_date: 2026-03-14
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 79
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

### Step 1: Canonical Allow Entries

One wildcard entry per binary — covers all subcommands and flags. Preferred for maintainability over subcommand-level granularity.

```json
"Bash(ll-issues:*)",
"Bash(ll-auto:*)",
"Bash(ll-parallel:*)",
"Bash(ll-sprint:*)",
"Bash(ll-loop:*)",
"Bash(ll-workflows:*)",
"Bash(ll-messages:*)",
"Bash(ll-history:*)",
"Bash(ll-deps:*)",
"Bash(ll-sync:*)",
"Bash(ll-verify-docs:*)",
"Bash(ll-check-links:*)"
```

### Step 2: Settings File Detection Logic (new Round 11 in `skills/init/interactive.md`, "Always shown")

Round 11 structure follows Round 10 pattern (`interactive.md:562–600`) — single `AskUserQuestion` call:

```
1. Check .claude/settings.json exists
2. Check .claude/settings.local.json exists
3. Determine action:
   a. Neither exists → AskUserQuestion: "Create settings.local.json, settings.json, or skip?"
   b. One exists → AskUserQuestion: "Add ll- commands to <file>? (y/n/skip)"
   c. Both exist → AskUserQuestion: "Add ll- commands to settings.local.json, settings.json, or skip?"
4. Also update Round summary table at interactive.md:608–619 (add Row 11: "Always shown")
```

Note: This must be "Always shown" (unconditional), unlike Rounds 8–10 which are gated by the Extended Config Gate in Round 7 and never shown during init.

### Step 3: Merge Logic

Merge is performed inline using the Read and Write tools (no Python utility) — the same approach as the Step 9 `.gitignore` update.

Steps:
1. **Read** the target settings file (or start with `{"permissions": {"allow": [], "deny": []}}` if absent)
2. **Filter** `permissions.allow`: keep all entries that do not start with `Bash(ll-` (preserves non-ll entries and the deny list)
3. **Append** the canonical list from Step 1
4. **Write** the result back with 2-space indent, preserving any top-level keys (e.g., `$schema`, `env`)

Idempotency: any existing `Bash(ll-` entries (including old subcommand-specific ones) are removed before appending, so re-running always converges to the canonical set.

### Step 4: Integration Points

- **`/ll:init` `SKILL.md`**: Add Step 10 (allowed-tools detection + merge) following the Step 9 `.gitignore` structure at lines 301–323. Update dry-run preview block (lines 261–266) and completion message table (lines 333–334).
- **`/ll:configure`**: Add `allowed-tools` area to `skills/configure/areas.md` (following existing area pattern) and update `skills/configure/SKILL.md` Area Mapping (lines 44–59), `--list` block (lines 70–88), and paginated selection (lines 139–203). This area writes to `.claude/settings.json` / `settings.local.json` rather than `ll-config.json` — note this in the area handler.

## API/Interface

No config-schema.json changes needed — this operates on `.claude/settings.json` / `.claude/settings.local.json` which are Claude Code's native settings files, not ll-config.json.

`cli.allowed_tools_hint` (a boolean to suppress the prompt on future init runs) is **out of scope** for the initial implementation. Omitted to keep the scope small; can be added later if re-prompting proves annoying in practice.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add Step 10 for allowed-tools (before current Step 10 "Display Completion Message", following the Step 9 `.gitignore` pattern at lines 301–323); update dry-run preview block (lines 261–266) to include `[update] .claude/settings.local.json`; update completion message table (lines 333–334)
- `skills/init/interactive.md` — add Round 11 for allowed-tools opt-in as an "Always shown" round (unlike Rounds 8–10 which are "Never shown"); update Round summary table at lines 608–619
- `skills/configure/SKILL.md` — add `allowed-tools` area to: frontmatter argument hint (line 10), Area Mapping table (lines 44–59), `--list` output block (lines 70–88), paginated selection flow (lines 139–203)
- `skills/configure/areas.md` — add `allowed-tools` area handler following existing area pattern

### Dependent Files (Callers/Importers)
- N/A — init skill is invoked directly by user, no programmatic callers

### Similar Patterns
- `skills/init/SKILL.md` Step 9 (`.gitignore` update step) — follow same detection-and-append pattern (check if entries exist, append only if absent)

### Tests

No unit tests — merge is inline (Read/Write tools), matching the `.gitignore` step precedent. Verification is by manual smoke test after implementation:

- [ ] Fresh project (no settings files): init creates `settings.local.json` with correct structure
- [ ] Existing file with non-ll entries: entries preserved, ll entries appended
- [ ] Re-run init: ll entries not duplicated (idempotent)
- [ ] Existing file with old subcommand-specific ll entries: replaced with canonical wildcards
- [ ] Deny list untouched after merge

### Documentation
- `commands/init.md` — update with new allowed-tools phase description

### Configuration
- `.claude/settings.json` / `.claude/settings.local.json` — written by this feature (Claude Code native files)

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
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8f8df48-fdc2-4d5b-9f5f-95f168709047.jsonl`
- `/ll:refine-issue` - 2026-03-16T01:26:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/93df5671-2743-4b52-aada-babab544472e.jsonl`
- `/ll:verify-issues` - 2026-03-15T18:54:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:format-issue` - 2026-03-15T18:51:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:capture-issue` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/92f6d283-84cd-41ed-b8d5-c0319fe66f82.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17fe5945-f06b-4c69-8093-7caebe31db0d.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/763473e1-42fe-4586-a7a6-6c4f070de693.jsonl`
