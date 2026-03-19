---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 78
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

2. **Register `hooks` area in `skills/configure/SKILL.md`** — Three edits required:
   - Area Mapping table (lines 46-60): add `hooks` row → reads/writes `.claude/settings.json` like `allowed-tools`
   - Interactive area selection (lines 138-207): add `hooks` option to the appropriate "More areas..." batch
   - Arguments list (lines 261-273): add `hooks` bullet

3. **Create `skills/configure/areas.md` section `## Area: hooks`** — Append after the `allowed-tools` section (line 792). Follow the `allowed-tools` pattern (lines 736-792) exactly: detect current state, display table, interactive round, merge JSON, write result.

4. **Implement `show` mode**: Read `hooks/hooks.json` (plugin hooks, always present) + `.claude/settings.json` (may not exist). Display unified table with columns: Source (`[Plugin]`/`[Project]`/`[Local]`), Event, Matcher, Script, Timeout, Status (exists/missing). Flag broken script paths.

5. **Implement `install` mode**: First, ask the user which target file to write to — `.claude/settings.local.json` (recommended, gitignored) or `.claude/settings.json` (tracked). Use the same "Target File" `AskUserQuestion` pattern as `allowed-tools` (areas.md:760-783). Then translate each entry in `hooks/hooks.json` into a settings.json-compatible entry (command strings stay the same — `${CLAUDE_PLUGIN_ROOT}` is valid). Merge into the chosen file using the same pattern as `allowed-tools` (areas.md:785-790): read target (default to `{}`), merge `hooks` key additively (don't overwrite existing non-ll hooks), write with 2-space indent.

6. **Implement `validate` mode**: For each hook in both sources, check: script path exists (`[ -f <path> ]`), executable bit set (`[ -x <path> ]`), timeout is reasonable (warn if > 30s for blocking hooks). Report by severity: ERROR (missing script), WARNING (not executable, high timeout).

7. **Add `--dry-run` support for `install`**: Show what entries would be added without writing. Follow the `--dry-run` pattern already established in the issue's Acceptance Criteria.

8. **Add `hooks --show` format to `skills/configure/show-output.md`**: Follow the pattern of existing show sections (e.g., lines 5-21 for `project --show`).

## Integration Map

### Files to Modify
- `skills/configure/SKILL.md` — add `hooks` subcommand dispatch
- `skills/configure/hooks.md` — new file implementing hook management logic
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only from this tool)

### Dependent Files (Callers/Importers)
- `skills/configure/SKILL.md` — dispatcher that routes to sub-commands
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only)

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

- **Line 46-60** (Area Mapping table): Add a `hooks` row pointing to a new area description. Pattern to follow is the `allowed-tools` row at line 59: `| \`allowed-tools\` | \`permissions.allow\` in \`.claude/settings.json\`... | ll- CLI tool allow entries |`. Hooks writes to `.claude/settings.json` similarly.
- **Lines 138-207** (interactive area selection batches): Add `hooks` option to one of the "More areas..." batches.
- **Lines 261-273** (Arguments list): Add `hooks` to the bullet list of valid areas.

#### Exact integration points in `skills/configure/areas.md`

- Append a new `## Area: hooks` section at the end of the file (after the `allowed-tools` section at line 736). Model after `## Area: allowed-tools` (lines 736-792) — same pattern: detect/display current state, interactive round, JSON merge logic, write result.

#### New file: `skills/configure/show-output.md`

- Add a `## hooks --show` section following the pattern of existing show sections (e.g., `## issues --show`, `## parallel --show`).

#### `hooks/hooks.json` — complete hook inventory (6 hooks across 6 events)

All scripts use `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/` prefix. When installed to `.claude/settings.json`, these command strings remain valid since `${CLAUDE_PLUGIN_ROOT}` resolves at runtime:

| Event | Matcher | Script | Timeout |
|-------|---------|--------|---------|
| `SessionStart` | `*` | `session-start.sh` | 5s |
| `UserPromptSubmit` | (none) | `user-prompt-check.sh` | 3s |
| `PreToolUse` | `Write\|Edit` | `check-duplicate-issue-id.sh` | 5s |
| `PostToolUse` | `*` | `context-monitor.sh` | 5s |
| `Stop` | (none) | `session-cleanup.sh` | 15s |
| `PreCompact` | `*` | `precompact-state.sh` | 5s |

Scripts live at `hooks/scripts/`: `session-start.sh`, `user-prompt-check.sh`, `check-duplicate-issue-id.sh`, `context-monitor.sh`, `session-cleanup.sh`, `precompact-state.sh` (+ `lib/common.sh`).

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
- ENH-705: Init should validate plugin loading and hook activation (complementary — ENH-705 warns, this FEAT fixes)

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
- `/ll:refine-issue` - 2026-03-19T02:51:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f2bd1a9-9196-4775-a221-228c31d6c262.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
- `/ll:format-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5037113-2ca1-4048-ba39-278c6ef9c09c.jsonl`
