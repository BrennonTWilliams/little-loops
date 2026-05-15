---
id: FEAT-1160
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue

blocked_by: [FEAT-1112]
relates_to: ['FEAT-1159', 'FEAT-1112']
---

# FEAT-1160: Context Window Analytics Command

## Summary

Add a `/ll:ctx-stats` command (or integrate into `ll-loop info`) that reports context window savings metrics for the current session: bytes processed vs bytes entered into context, per-tool breakdown, prompt cache hits and bytes saved, estimated session time gained, and compact count. Modeled after context-mode's `AnalyticsEngine`/`FullReport` pattern.

## Current Behavior

little-loops has no visibility into context window usage. There is no way to see how many tokens/bytes were processed by tools vs actually entered the context window, whether prompt cache is being hit, or how long tools are extending the usable session life.

## Expected Behavior

A command (e.g. `/ll:ctx-stats`) shows a before/after summary like:

```
Without savings:  |########################################| 480 KB in conversation
With savings:     |#########                               |  98 KB in conversation

382 KB processed by tools, never entered conversation. (79% reduction)
+6m session time gained.

  read          12 calls     42.1 KB used
  bash          8 calls      18.3 KB used

Cache: 4 hits | 96 KB saved | 5h TTL remaining
```

## Motivation

context-mode (github.com/mksglu/context-mode) demonstrates that this class of metrics—bytes kept out, per-tool savings, cache hit rate—is both computable from Claude Code hook data and genuinely useful for understanding session health. little-loops already has hook infrastructure (PostToolUse) that could accumulate these counters. Without this, users have no signal on whether compaction is near or whether large tool outputs are burning context unnecessarily.

## Proposed Solution

Extend FEAT-1112's SQLite + FTS5 store to include per-tool byte columns, then query that store from a new `/ll:ctx-stats` command. Approach 1 (PostToolUse hook writing to `.ll/ll-ctx-stats.json`) is out of scope — it re-introduces the fragmentation FEAT-1112 was designed to eliminate.

## Integration Map
### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- context-mode `src/session/analytics.ts` — reference implementation for the metrics shape
- `hooks/hooks.json` — existing PostToolUse hooks to extend or add alongside
- `scripts/little_loops/cli/loop/info.py` — pattern for session-scoped CLI display

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- `.ll/ll-config.json` — may need `analytics.enabled` flag

## Implementation Steps

> **Prerequisite**: FEAT-1112 must land first (SQLite + FTS5 store).

1. Define per-tool byte columns in FEAT-1112's SQLite schema (`bytes_in`, `bytes_out`, `cache_hit` per tool-call row)
2. Implement query / aggregation logic that computes session totals, per-tool breakdown, cache hit rate, and estimated context reduction percentage
3. Wire display logic into `/ll:ctx-stats` command or extend `ll-loop info` (`scripts/little_loops/cli/loop/info.py`)
4. Add tests for schema extension, query logic, and formatted output

## Impact
- **Priority**: P4 - Nice-to-have visibility feature; no current blocker
- **Effort**: Medium - Hook accumulation + CLI display + tests
- **Risk**: Low - Additive, no changes to existing behavior
- **Breaking Change**: No

## Related Key Documentation
_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels
`analytics`, `context-window`, `hooks`, `captured`

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-14T21:18:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75505ad4-6733-4424-b334-3143f412786b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:verify-issues` - 2026-04-26T19:34:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/316256f6-01c2-468b-8efc-2db79aff6b29.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-23T00:14:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c0e0697-1da9-403b-82a7-6eb401f63ad3.jsonl`
- `/ll:capture-issue` - 2026-04-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6ae308f-90dc-4b4e-8527-5207880ea6dd.jsonl`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-23

- No `/ll:ctx-stats` command or skill exists ✓
- No PostToolUse hook accumulating byte counters to `.ll/ll-ctx-stats.json` ✓
- Blocked by FEAT-1112 (session store) which is itself not yet implemented ✓
- Feature not yet implemented ✓

---

## Status
**Open** | Created: 2026-04-18 | Priority: P4

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): The "Approach 1" implementation path (PostToolUse hook writing to `.ll/ll-ctx-stats.json`) is removed from scope. Scope this issue exclusively to Approach 2: extend FEAT-1112's SQLite schema with per-tool byte columns and implement `/ll:ctx-stats` as a query over that store. The flat-file hook approach re-introduces the fragmentation FEAT-1112 was designed to eliminate. Implementation steps 1-3 must be rewritten to describe schema extension + query logic rather than a hook accumulator.
