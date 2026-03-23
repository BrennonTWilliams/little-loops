---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
---

# FEAT-706: Hook management tooling for target projects

## Summary

Little-loops has no tooling to read, evaluate, or install hooks in a target project's `.claude/settings.json`. Users who don't load little-loops as a Claude Code plugin have no supported path to configure hooks, and there's no way to inspect or repair hook configuration through little-loops tooling.

## Current Behavior

Little-loops has no tooling to read, evaluate, or install hooks in a target project's `.claude/settings.json`. Users who load little-loops via CLAUDE.md (rather than as a registered plugin) have no supported path to configure hooks. There is no way to inspect what hooks are active, diagnose why a hook-dependent feature isn't working, or validate that configured hooks point to real scripts.

## Expected Behavior

A `/ll:configure hooks` command (or sub-command) provides three modes:
- **show**: Display a unified table of all hooks (plugin-level and settings.json), their event types, script paths, and enabled status, flagging any broken paths
- **install**: Generate and merge hook entries into the user's chosen settings file (`.claude/settings.json` or `.claude/settings.local.json`) from the plugin's `hooks/hooks.json`, preserving existing unrelated keys
- **validate**: Check each configured hook for script existence, executable bit, and timeout reasonableness, reporting issues by severity

## Use Case

A developer installs little-loops, runs `/ll:init`, enables context monitoring and handoff, but is using little-loops via CLAUDE.md rather than as a registered plugin. Currently, there is no command to:
- Show what hooks are currently configured (plugin hooks vs. settings.json hooks)
- Install the relevant hook entries into the project's `.claude/settings.json`
- Validate whether configured hooks point to real scripts
- Diagnose why a hook-dependent feature isn't working

## Acceptance Criteria

- [ ] A command or skill can display current hook configuration (both plugin-level and target `.claude/settings.json`)
- [ ] A command or skill can install little-loops hook entries into a target project's settings file
- [ ] The user is prompted to choose target file: `.claude/settings.local.json` (recommended, gitignored) or `.claude/settings.json` (tracked)
- [ ] Installed hooks correctly reference plugin scripts via `${CLAUDE_PLUGIN_ROOT}`
- [ ] The tool validates that referenced script paths exist before installing
- [ ] Existing hooks in the target file are preserved (additive, not destructive)
- [ ] A `--dry-run` flag shows what would be installed without making changes

## Proposed Solution

Add a `/ll:configure hooks` sub-command (or extend `/ll:configure`) with the following capabilities:

### `show` mode
- Display a table of all hooks: source (plugin vs. settings.json), event type, script path, enabled status
- Flag any hooks whose script paths don't resolve

### `install` mode
- Read `hooks/hooks.json` from the plugin
- **Ask the user which target file** to write to: `.claude/settings.local.json` (recommended — gitignored, personal) or `.claude/settings.json` (tracked, shared with team). Follow the same prompt pattern as `allowed-tools` in `areas.md:760-783`.
- Generate equivalent entries with `${CLAUDE_PLUGIN_ROOT}`-relative paths
- Merge into the chosen file without overwriting unrelated keys
- Report what was added

### `validate` mode
- Check each configured hook (both sources) for: script existence, executable bit, timeout reasonableness
- Report issues by severity

## Scope Boundaries

- **In scope**: Read/install/validate hooks in target project `.claude/settings.json`; display combined hook state
- **Out of scope**: Modifying the plugin's own `hooks/hooks.json`; hooks for non-little-loops tools

## Implementation Steps

1. **Settings.json schema is already documented** — `docs/claude-code/hooks-reference.md` contains the full hook schema. The structure is identical to `hooks/hooks.json`. No separate research needed.

2. **Register `hooks` area in `skills/configure/SKILL.md`** — Six edits required:
   - Frontmatter `description` field (line 10): append `|hooks` to the pipe-delimited area list
   - Area Mapping table (line 59→60): add `hooks` row → reads/writes `.claude/settings.json` like `allowed-tools`
   - `--list` mode output (line 85→86): add `hooks [DEFAULT]` line; status detection checks `hooks` key in settings files, not `ll-config.json`
   - Batch 3 "More areas..." description (line 190): update from `"Show context, prompt"` → `"Show context, prompt, hooks"`
   - Interactive area selection Batch 4 (lines 195-207): add `hooks` option to the final batch alongside `context`, `prompt`, `allowed-tools`
   - Arguments list (line 273→274): add `hooks` bullet

3. **Append `## Area: hooks` to `skills/configure/areas.md`** — Append after the `allowed-tools` section (after line 792, current EOF). Follow the `allowed-tools` pattern (lines 736-792) exactly: detect current state, display table, interactive round, merge JSON, write result. **Do NOT create a separate `hooks.md` file** — all area logic lives in `areas.md`.

4. **Implement `show` mode**: Read `hooks/hooks.json` (plugin hooks, always present) + `.claude/settings.json` (may not exist). Display unified table with columns: Source (`[Plugin]`/`[Project]`/`[Local]`), Event, Matcher, Script, Timeout, Status (exists/missing). Flag broken script paths.

5. **Implement `install` mode**: First, ask the user which target file to write to — `.claude/settings.local.json` (recommended, gitignored) or `.claude/settings.json` (tracked). Use the same "Target File" `AskUserQuestion` pattern as `allowed-tools` (areas.md:760-783). Then translate each entry in `hooks/hooks.json` into a settings.json-compatible entry (command strings stay the same — `${CLAUDE_PLUGIN_ROOT}` is valid). Merge into the chosen file using the same pattern as `allowed-tools` (areas.md:785-790): read target (default to `{}`), merge `hooks` key additively (don't overwrite existing non-ll hooks), write with 2-space indent.

6. **Implement `validate` mode**: For each hook in both sources, check: script path exists (`[ -f <path> ]`), executable bit set (`[ -x <path> ]`), timeout is reasonable (warn if > 30s for blocking hooks). Report by severity: ERROR (missing script), WARNING (not executable, high timeout).

7. **Add `--dry-run` support for `install`**: Show what entries would be added without writing. Follow the `--dry-run` pattern already established in the issue's Acceptance Criteria.

8. **Implement `hooks --show` display inline in `areas.md`**: Follow the `allowed-tools` pattern (areas.md:738-758) — define state detection bash block + display table directly in the `## Area: hooks` section. Do NOT add a section to `show-output.md`; `allowed-tools` has no entry there either, and hooks follows the same inline approach.

9. **Add Step 10.5 (Install Hooks) to `skills/init/SKILL.md`**: Insert a new step between Step 10 (Update Allowed Tools) and Step 11 (Display Completion Message). Pattern mirrors Step 10 exactly:
   - Detect whether little-loops is loaded as a **plugin** (skip — hooks are already active via `hooks/hooks.json`) or via **CLAUDE.md** (proceed with installation)
   - To detect plugin vs CLAUDE.md loading: check whether `${CLAUDE_PLUGIN_ROOT}` is set in the environment (`[ -n "$CLAUDE_PLUGIN_ROOT" ]`)
   - Ask which target file: `.claude/settings.local.json` (recommended, gitignored) or `.claude/settings.json` (tracked) — same `AskUserQuestion` pattern as Step 10 / `allowed-tools` in `areas.md:760-783`
   - Merge the `hooks` key from `hooks/hooks.json` into the chosen file additively (read target or start with `{}`; merge `hooks` key without overwriting existing non-ll hooks; write with 2-space indent)
   - **`--yes` mode**: use `.claude/settings.local.json` without prompting (skip if plugin user)
   - **`--dry-run` mode**: skip this step (already previewed in dry-run output)
   - Track whether hooks were installed for use in the completion message

10. **Update Step 11 (completion message) in `skills/init/SKILL.md`**: Add a conditional line to the "Created/Updated" block:
    ```
    Updated: .claude/settings.json (added ll- hooks)   # Only show if hooks were installed in Step 10.5
    ```
    Add a conditional next step: `Configure hooks: /ll:configure hooks` — only shown if user skipped hook installation in Step 10.5.

## Integration Map

### Files to Modify
- `skills/configure/SKILL.md` — add `hooks` to: Area Mapping table (line 60, after `allowed-tools`), `--list` output (line 85, after `allowed-tools`), Batch 4 interactive selection (line 206, before the closing `\`\`\``), Arguments list (line 274, after `allowed-tools`)
- `skills/configure/areas.md` — append new `## Area: hooks` section after line 792 (current EOF), following the `allowed-tools` pattern exactly
- `skills/init/SKILL.md` — add Step 10.5 (Install Hooks) between Step 10 and Step 11; update Step 11 completion message to show hooks installation status and conditional next-step hint

### Dependent Files (Read-Only)
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only; do not modify)

### Similar Patterns
- Existing `/ll:configure` sub-command dispatch pattern

### Tests
- TBD — manual validation of show/install/validate modes against a test project

### Documentation
- `docs/ARCHITECTURE.md` — update if hook management becomes a new subsystem
- `/ll:help` output — new sub-command needs listing

### Configuration
- `.claude/settings.json` or `.claude/settings.local.json` — target file for hook installation (user chooses)
- `hooks/hooks.json` — read-only source for hook definitions

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### Exact integration points in `skills/configure/SKILL.md`

- **Line 10** (frontmatter `description` field): Append `|hooks` to the pipe-delimited area list: `"project|issues|...allowed-tools|hooks (optional - prompts if omitted)"`
- **Line 59→60** (Area Mapping table, lines 46-59): Add `hooks` row after `allowed-tools`. Pattern: `| \`hooks\` | \`hooks\` in \`.claude/settings.json\` or \`.claude/settings.local.json\` | ll- lifecycle hook configuration |`
- **Line 85→86** (`--list` mode output, lines 71-90): Add `hooks` line after `allowed-tools`. Pattern: `  hooks         [DEFAULT]     ll- hook configuration in settings.json/settings.local.json`. Status detection: check `.claude/settings.json` and `.claude/settings.local.json` for a `hooks` key (not `ll-config.json`).
- **Line 190** (Batch 3 "More areas..." description): Update description from `"Show context, prompt"` to `"Show context, prompt, hooks"` so users know `hooks` is available in Batch 4.
- **Lines 195-207** (Batch 4, the final interactive area selection batch): Add `hooks` option alongside `context`, `prompt`, `allowed-tools`. This batch currently has 3 options; `hooks` makes it 4 — still within the standard batch size, no additional "More areas..." needed.
- **Lines 261-273** (Arguments list): Add `hooks` bullet at line 274 after `allowed-tools`.

#### Exact integration points in `skills/configure/areas.md`

- Append a new `## Area: hooks` section at the end of the file (after the `allowed-tools` section which runs lines 736-793). Model after `## Area: allowed-tools` (lines 736-793) — same pattern: detect/display current state, interactive round, JSON merge logic, write result. New section begins at line 794.

#### `skills/configure/show-output.md` — no entry needed for hooks

- `show-output.md` has 171 lines covering 11 areas (project through sync). `allowed-tools` has no entry there — it displays state inline in areas.md. **Hooks follows the same pattern**: implement the display table directly in the `## Area: hooks` section of areas.md (state detection bash block + display table), not in show-output.md.

#### `hooks/hooks.json` — complete hook inventory (7 hook objects across 6 event types)

All scripts use `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/` prefix. When installed to `.claude/settings.json`, these command strings remain valid since `${CLAUDE_PLUGIN_ROOT}` resolves at runtime.

**Important**: `UserPromptSubmit` and `Stop` event groups have **no `matcher` field** (not even `"*"`). `PostToolUse` has two separate groups with different matchers. Show/install/validate must handle the absence of `matcher` gracefully.

| Event | Matcher | Script | Timeout |
|-------|---------|--------|---------|
| `SessionStart` | `*` | `session-start.sh` | 5s |
| `UserPromptSubmit` | _(no matcher)_ | `user-prompt-check.sh` | 3s |
| `PreToolUse` | `Write\|Edit` | `check-duplicate-issue-id.sh` | 5s |
| `PostToolUse` | `*` | `context-monitor.sh` | 5s |
| `PostToolUse` | `Bash` | `issue-completion-log.sh` | 5s |
| `Stop` | _(no matcher)_ | `session-cleanup.sh` | 15s |
| `PreCompact` | `*` | `precompact-state.sh` | 5s |

Scripts live at `hooks/scripts/`: `session-start.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`, `context-monitor.sh`, `issue-completion-log.sh`, `session-cleanup.sh`, `precompact-state.sh` (+ `lib/common.sh`).

#### `.claude/settings.json` hook schema (from `docs/claude-code/hooks-reference.md`)

The schema is identical to `hooks/hooks.json`. A top-level `hooks` key with event names as keys. No `description` field is needed at top level. Example translation of one plugin hook:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/context-monitor.sh",
            "timeout": 5,
            "statusMessage": "Monitoring context usage..."
          }
        ]
      }
    ]
  }
}
```

**Important**: `.claude/settings.json` does not currently exist in this project. Install mode must create it from scratch when absent, initialized as `{"hooks": {...}}`.

#### JSON merge pattern (from `skills/configure/areas.md:785-790`)

The `allowed-tools` area uses this exact pattern — directly reusable:
1. Read target file (or start with `{}` if absent)
2. Remove existing conflicting entries
3. Append new entries
4. Write result with 2-space indent, preserving all top-level keys

#### Test pattern (from `scripts/tests/test_hooks_integration.py`)

Existing hook tests use `subprocess.run([str(hook_script)], input=json.dumps(input_data), ...)` directly against shell scripts. The hooks skill itself is a Claude Code skill (markdown), so new tests would be manual integration tests; no Python unit test pattern to follow for skill behavior itself.

### Related Issues
- ENH-705: Init should validate plugin loading and hook activation (complementary — ENH-705 warns, this FEAT fixes). If ENH-705 is implemented before FEAT-706, its warning for inactive hooks must reference `/ll:configure hooks install` as the remediation path. Once FEAT-706's Step 10.5 lands in `/ll:init`, the ENH-705 warning becomes largely redundant for new installs (hooks are installed during init); ENH-705 retains value only for projects initialized before FEAT-706 was available.

## Impact

- **Priority**: P3 - Quality-of-life improvement for non-plugin users; not blocking core functionality
- **Effort**: Medium - Requires new skill file with three modes, JSON merging logic, and path validation
- **Risk**: Low - Additive only; writes to `.claude/settings.json` are guarded by `--dry-run` and preserve existing keys
- **Breaking Change**: No

## Labels

`feature`, `hooks`, `tooling`, `configure`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `hooks/hooks.json` exists and is the described source of truth. No `skills/configure/hooks.md` file exists. The `skills/configure/SKILL.md` has no `hooks` subcommand dispatch. Feature not yet implemented.

## Status

**Open** | Created: 2026-03-12 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-03-23T18:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa97f181-0c89-48a7-90d1-c20a0ffe9cd8.jsonl`
- `/ll:refine-issue` - 2026-03-23T18:25:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7c741821-281c-470e-a210-3206e80affa1.jsonl`
- `/ll:confidence-check` - 2026-03-23T18:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dbb81656-ef71-4079-a8b7-1bf83a1c6364.jsonl`
- `/ll:refine-issue` - 2026-03-23T18:12:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/500f7108-96bd-4385-b940-17a9e320101e.jsonl`
- `/ll:refine-issue` - 2026-03-19T02:51:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f2bd1a9-9196-4775-a221-228c31d6c262.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
- `/ll:format-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5037113-2ca1-4048-ba39-278c6ef9c09c.jsonl`
