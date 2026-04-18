---
id: FEAT-1160
type: FEAT
priority: P4
status: open
discovered_date: 2026-04-18
discovered_by: capture-issue
related: [FEAT-1159, FEAT-1112]
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

TBD - requires investigation. Two plausible approaches:
1. Accumulate byte counters in a PostToolUse hook (shell script) writing to `.ll/ll-ctx-stats.json`, then read by a skill/command at query time.
2. Extend FEAT-1112's SQLite store to include per-tool byte columns, queried by a new CLI command.

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
1. Define the metrics schema (`ContextStats` dataclass or JSON shape)
2. Implement PostToolUse hook accumulator (shell or Python) writing to `.ll/ll-ctx-stats.json`
3. Implement query/format logic (new skill or extend `ll-loop info`)
4. Wire into `/ll:ctx-stats` command
5. Add tests for byte accumulation and formatting

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
- `/ll:capture-issue` - 2026-04-18T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f6ae308f-90dc-4b4e-8527-5207880ea6dd.jsonl`

---

## Status
**Open** | Created: 2026-04-18 | Priority: P4
