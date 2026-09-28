---
id: ENH-3645
type: ENH
title: Add hooks.edit_batch_nudge config toggle and tunables
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T22:47:49Z'
---

# ENH-3645: Add hooks.edit_batch_nudge config toggle and tunables

## Summary

The `edit_batch_nudge` PostToolUse hook (`scripts/little_loops/hooks/edit_batch_nudge.py`, wired at `hooks/hooks.json` on the `Edit|Write|MultiEdit` matcher) has no user-facing config. `config-schema.json` has no `edit_batch_nudge`/`nudge` key, and the handler reads no config: `_NUDGE_THRESHOLD` (3) and `_BATCH_WINDOW_SECONDS` (3.0) are hardcoded constants. The only way to disable it today is removing the matcher entry from `hooks/hooks.json` or overriding it in the host's own settings.

Add a `hooks.edit_batch_nudge` object to `config-schema.json` (under the existing `hooks` block) with:
- `enabled` (bool, default `true`) — when `false`, the handler is a silent no-op (exit 0, no state write)
- `threshold` (int, default 3) — consecutive unbatched edits before the nudge fires
- `window_seconds` (number, default 3.0) — gap below which two edits count as batched

The handler should read these at call time via the project config, falling back to the current constants when the key or project is absent.

## Context

ENH-2499 and ENH-2503 both explicitly scoped config out ("No new `ll-config.json` keys"; ENH-2499 noted the constants "could be promoted to config if desired"). This captures that deferred follow-up. Found while checking whether the hook could be toggled per-project.

## Acceptance Criteria

- `config-schema.json` declares `hooks.edit_batch_nudge.{enabled,threshold,window_seconds}` with the defaults above
- `enabled: false` in `.ll/ll-config.json` (or `.ll/ll.local.md`) suppresses the nudge and writes no state
- Unset config preserves current behavior exactly
- Tests cover disabled, custom threshold, and custom window


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

## Current Pain Point

## Success Metrics

## Acceptance Criteria

## Scope Boundaries

## Backwards Compatibility

## API/Interface

```python
# Example interface/signature
```


## Session Log
- `/ll:capture-issue` - 2026-09-28T22:47:54 - `f34adacb-fb88-4876-a098-8175948c7ff2.jsonl`
