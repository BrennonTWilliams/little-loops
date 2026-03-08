---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# ENH-650: `worktree_copy_files` schema default lags behind code — schema missing `.claude/settings.local.json`

## Summary

`config-schema.json` declares `parallel.worktree_copy_files` default as `[".env"]`. `ParallelAutomationConfig` in `config.py` defaults to `[".claude/settings.local.json", ".env"]`. The code is more correct — `settings.local.json` carries Claude Code auth tokens needed in worktrees — but users reading the schema see an incomplete default and may unknowingly strip it from their configs.

## Motivation

Schema and code must agree on defaults. When they diverge, users configuring from the schema get subtly broken behavior (missing auth in worktrees). Keeping the schema accurate also enables schema validation tools to catch misconfigurations.

## Current Behavior

Schema shows default `[".env"]`; code uses `[".claude/settings.local.json", ".env"]`.

## Expected Behavior

Schema `parallel.worktree_copy_files.default` matches code: `[".claude/settings.local.json", ".env"]`.

## Proposed Solution

Update `config-schema.json` line ~229:

```json
"default": [".claude/settings.local.json", ".env"]
```

## Implementation Steps

1. Open `config-schema.json`
2. Find `parallel.worktree_copy_files` property definition
3. Update `"default"` value to `[".claude/settings.local.json", ".env"]`
4. Optionally add a description note explaining why `settings.local.json` is included
5. Validate: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`

## Impact

- **Severity**: MEDIUM — schema behind code. Users configuring from schema may omit critical file.
- **Files affected**: `config-schema.json`

## Labels

enhancement, config, schema, parallel

## Status

---
open
---

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
