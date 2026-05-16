---
testable: false
---
# ENH: Add `refine_status` and `cli` sections to Full Configuration Example

## Summary

The Full Configuration Example in `docs/reference/CONFIGURATION.md` is missing two configuration sections (`refine_status` and `cli`) that are documented in the sections below but not shown in the top-level JSON example.

## Current Behavior

The Full Configuration Example at the top of CONFIGURATION.md does not include the `refine_status` or `cli` top-level keys. Users reading the example as a template will not know these sections exist.

## Expected Behavior

The Full Configuration Example should include skeleton entries for all top-level config sections, matching what users would get from `/ll:init`.

## Proposed Solution

Add the following blocks to the Full Configuration Example JSON, after the existing `dependency_mapping` block:

```json
  "refine_status": {
    "columns": [],
    "elide_order": []
  },

  "cli": {
    "color": true,
    "colors": {
      "fsm_edge_labels": {}
    }
  }
```

The `cli.colors.logger`, `cli.colors.priority`, and `cli.colors.type` sub-keys can be omitted (they have detailed defaults documented in API.md) — only the `fsm_edge_labels` override key (which is unique to CONFIGURATION.md) needs to be shown.

## Integration Map

### Files to Modify
- `docs/reference/CONFIGURATION.md` — add `refine_status` and `cli` blocks to the Full Configuration Example

### Tests
- N/A — documentation only

### Documentation
- `docs/reference/CONFIGURATION.md` — primary change location

### Configuration
- N/A

## Scope Boundaries

- Only the Full Configuration Example JSON block in CONFIGURATION.md is in scope
- Do NOT change the config schema (`config-schema.json`) or any Python implementation
- Do NOT document sub-keys beyond `fsm_edge_labels` for `cli.colors` (detailed defaults live in API.md)
- Do NOT modify the per-section documentation below the example

## Impact

- **Priority**: P4 — cosmetic completeness; no functional impact
- **Effort**: Trivial — two small JSON blocks to add
- **Risk**: None
- **Breaking Change**: No

## Labels

`documentation`, `configuration`

## Status

**Completed** | Created: 2026-03-24 | Priority: P4

## Resolution

Added `refine_status` and `cli` blocks to the Full Configuration Example in `docs/reference/CONFIGURATION.md` after the `dependency_mapping` block, matching the proposed solution exactly.

## Session Log
- `/ll:ready-issue` - 2026-03-24T22:11:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6bec1f70-ffc3-4abf-a70e-8a5dafe5b029.jsonl`
- `/ll:manage-issue enh improve ENH-877` - 2026-03-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6bec1f70-ffc3-4abf-a70e-8a5dafe5b029.jsonl`
