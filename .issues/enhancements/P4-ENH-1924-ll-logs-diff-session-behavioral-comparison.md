---
id: ENH-1924
title: "ll-logs diff: compare sessions before/after a prompt change"
type: ENH
priority: P4
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, FEAT-1920]
labels: [captured, ll-logs, regression]
---

# ENH-1924: ll-logs diff — compare sessions before/after a prompt change

## Summary

Add `ll-logs diff <sessionA> <sessionB>` to compare two sessions' ll-invocation
behavior — skills invoked, tool-call sequences, failures, corrections — to spot
behavioral regressions after a skill prompt or config change.

## Current Behavior

There is no way to compare what changed between two sessions at the
tool/skill level. Detecting whether a prompt edit improved or regressed behavior
relies on manual transcript reading.

## Expected Behavior

`ll-logs diff <sessionA> <sessionB> [--json]` resolves both sessions (via
`ll-session path` / log paths) and reports added/removed skills, changed
invocation sequences, and deltas in failure/correction counts.

## Motivation

Pairs with FEAT-1920 (eval-export): export real inputs, replay through the new
prompt, then `diff` the replay session against the original to see behavioral
drift concretely.

## Proposed Solution

Add `diff` to `cli/logs.py` reusing the shared extractor (ENH-1919). Build the
ll-invocation event stream for each session and compute a structured set/sequence
diff plus failure/correction count deltas.

## Integration Map

- FEAT-1920 (eval-export): replay-vs-original comparison consumer.
- `ll-session path`: session-id → log-path resolution.

## Implementation Steps

1. Resolve two session identifiers to log paths.
2. Build each session's ll-invocation event stream (shared extractor).
3. Compute set diff (skills) + sequence diff + failure/correction deltas.
4. Text + `--json`; tests over two fixture sessions.

## Success Metrics

- A seeded behavioral change between two fixture sessions is reported accurately.

## Scope Boundaries

- Out: semantic/LLM diffing of message content — this is structural tool/skill diffing only.

## Impact

Makes prompt/config-edit regressions observable without manual transcript reading.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs, ll-session)

## Labels

captured, ll-logs, regression

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
