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

## Fix

Update `skills/init/SKILL.md` Step 9 to include all state files:

```
# little-loops state files
.auto-manage-state.json
.parallel-manage-state.json
.claude/ll-context-state.json
.claude/ll-sync-state.json
```

Optionally, only add feature-specific state files when those features are enabled (context monitor, sync).

## Files

- `skills/init/SKILL.md` (Step 9, lines ~184-203)
- `config-schema.json` (state_file defaults at lines ~129, 178, 429, 607)
