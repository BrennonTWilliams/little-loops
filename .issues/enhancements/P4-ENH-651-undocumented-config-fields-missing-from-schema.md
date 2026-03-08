---
discovered_date: 2026-03-08T00:00:00Z
discovered_by: capture-issue
---

# ENH-651: Three config fields exist in code but are undocumented in schema

## Summary

Three fields in `config.py` have no corresponding entries in `config-schema.json`, making them undiscoverable by users inspecting the schema. They cannot be validated, autocompleted, or documented via schema tooling.

| Field | Location | Default |
|-------|----------|---------|
| `automation.idle_timeout_seconds` | `AutomationConfig` line 193 | `0` |
| `automation.max_continuations` | `AutomationConfig` line 198 | `3` |
| `parallel.require_code_changes` | `ParallelAutomationConfig` line 231 | `true` |

## Motivation

The schema is the contract between the tool and its users. Missing fields mean users can't discover, validate, or document these knobs without reading source code. Adding them enables schema-driven autocomplete and validation in IDEs and CI pipelines.

## Proposed Solution

Add the three properties to their respective sections in `config-schema.json`:

**`automation` section (~line 160):**
```json
"idle_timeout_seconds": {
  "type": "integer",
  "default": 0,
  "description": "Seconds of inactivity before automation considers the session idle. 0 disables."
},
"max_continuations": {
  "type": "integer",
  "default": 3,
  "description": "Maximum number of continuation prompts before automation stops."
}
```

**`parallel` section (~line 230):**
```json
"require_code_changes": {
  "type": "boolean",
  "default": true,
  "description": "Require worktree to produce code changes before merging. Skips no-op runs."
}
```

## Implementation Steps

1. Locate `automation` properties block in `config-schema.json`
2. Add `idle_timeout_seconds` and `max_continuations` entries with matching defaults and descriptions
3. Locate `parallel` properties block
4. Add `require_code_changes` entry
5. Validate: `python -m jsonschema --instance .claude/ll-config.json config-schema.json`

## Impact

- **Severity**: LOW — schema incomplete. No functional breakage; discoverability gap only.
- **Files affected**: `config-schema.json`

## Labels

enhancement, config, schema, documentation

## Status

---
open
---

## Session Log
- `/ll:capture-issue` - 2026-03-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82c79651-563d-4a71-9c05-13a21c920832.jsonl`
