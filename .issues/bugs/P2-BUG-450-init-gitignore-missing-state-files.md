---
type: BUG
id: BUG-450
title: Init .gitignore update missing context-state and sync-state files
priority: P2
status: open
created: 2026-02-22
---

# Init .gitignore update missing context-state and sync-state files

## Summary

Step 9 of `/ll:init` adds only `.auto-manage-state.json` and `.parallel-manage-state.json` to `.gitignore`. Two other runtime state files defined in `config-schema.json` are missing:

- `.claude/ll-context-state.json` (from `context_monitor.state_file`)
- `.claude/ll-sync-state.json` (from `sync.github.state_file`)

These files are generated at runtime and should not be committed.

## Expected Behavior

All runtime state files should be added to `.gitignore` during init, or at minimum the ones for features the user enabled.

## Current Behavior

After running `/ll:init`, the generated `.gitignore` block includes:

```
# little-loops state files
.auto-manage-state.json
.parallel-manage-state.json
```

Two additional runtime state files defined in `config-schema.json` are absent:
- `.claude/ll-context-state.json` (`context_monitor.state_file` default)
- `.claude/ll-sync-state.json` (`sync.github.state_file` default)

## Steps to Reproduce

1. Run `/ll:init --interactive` and complete the wizard, enabling context monitoring and GitHub sync features
2. Inspect the generated `.gitignore` entries added for little-loops
3. Observe: `.claude/ll-context-state.json` and `.claude/ll-sync-state.json` are not listed

## Actual Behavior

After completing init with context monitoring or GitHub sync enabled, the `.gitignore` block contains only `.auto-manage-state.json` and `.parallel-manage-state.json`. Upon using those features, `.claude/ll-context-state.json` and `.claude/ll-sync-state.json` are generated at runtime and appear as untracked files in every `git status` output.

## Root Cause

- **File**: `skills/init/SKILL.md`
- **Anchor**: `Step 9 (.gitignore update, lines ~184-203)`
- **Cause**: Step 9 was written when only the automation state files existed. As `context_monitor` and `sync` features were added to `config-schema.json`, their corresponding `state_file` defaults were not reflected in the wizard's gitignore step.

## Proposed Solution

Update `skills/init/SKILL.md` Step 9 to include all state files:

```
# little-loops state files
.auto-manage-state.json
.parallel-manage-state.json
.claude/ll-context-state.json
.claude/ll-sync-state.json
```

Optionally, only add feature-specific state files when those features are enabled (context monitor, sync).

## Location

- **File**: `skills/init/SKILL.md`
- **Lines**: ~184-203 (Step 9)
- **Also**: `config-schema.json` (state_file defaults at lines ~129, 178, 429, 607)

## Motivation

Runtime state files are generated automatically and contain ephemeral data that should not be committed. If not gitignored, they appear as untracked changes in every `git status` and could accidentally be committed, adding noise to repository history.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 9 gitignore block: add `.claude/ll-context-state.json` and `.claude/ll-sync-state.json`

### Dependent Files (Callers/Importers)
- `config-schema.json` — source of truth for state file default paths (lines ~129, 178, 429, 607)

### Similar Patterns
- Existing gitignore block in Step 9 — same pattern, extend the list

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate Step 9 in `skills/init/SKILL.md` (lines ~184-203)
2. Add `.claude/ll-context-state.json` and `.claude/ll-sync-state.json` to the gitignore block
3. Optionally: add conditional logic to only include feature-specific state files when those features are enabled
4. Verify the complete gitignore block covers all `state_file` defaults in `config-schema.json`

## Impact

- **Priority**: P2 — State files committed inadvertently cause repository noise; affects users of context monitoring and GitHub sync
- **Effort**: Small — Single file change (Step 9 in SKILL.md)
- **Risk**: Low — Additive gitignore entries; no behavioral impact
- **Breaking Change**: No

## Labels

`bug`, `init`, `gitignore`, `state-files`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocks

- ENH-453
- ENH-458

---

## Status

**Open** | Created: 2026-02-22 | Priority: P2
