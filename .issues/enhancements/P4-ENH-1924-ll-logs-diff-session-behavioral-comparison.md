---
id: ENH-1924
title: 'll-logs diff: compare sessions before/after a prompt change'
type: ENH
priority: P4
status: done
captured_at: '2026-06-04T02:27:34Z'
discovered_date: '2026-06-04'
discovered_by: capture-issue
parent: EPIC-1918
relates_to:
- EPIC-1918
- FEAT-1920
labels:
- captured
- ll-logs
- regression
confidence_score: 91
outcome_confidence: 87
completed_at: '2026-06-06T03:44:36Z'
score_complexity: 22
score_test_coverage: 20
score_ambiguity: 20
score_change_surface: 25
size: Medium
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

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `diff` subcommand to `ll-logs`

### Dependent Files (Callers/Importers)
- FEAT-1920 (eval-export): replay-vs-original comparison consumer

### Similar Patterns
- ENH-1919 shared extractor: ll-invocation event stream builder (reuse)
- `ll-session path` (`scripts/little_loops/cli/session.py`): session-id → log-path resolution (reuse for argument resolution)

### Tests
- TBD — add two fixture sessions with a seeded behavioral difference and assert diff accuracy

### Documentation
- `docs/reference/API.md` — update ll-logs subcommand reference

### Configuration
- N/A

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

- **Priority**: P4 — Nice-to-have observability tooling; not blocking current workflows
- **Effort**: Small — new subcommand reusing the existing event-stream extractor (ENH-1919); no new parsing infrastructure needed
- **Risk**: Low — purely additive new subcommand; no modification to existing `ll-logs` behavior
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-logs, ll-session)

## Labels

captured, ll-logs, regression

## Status

open


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:ready-issue` - 2026-06-06T03:39:03 - `14e150ad-47fa-414b-a6be-4f8d77236420.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f85e4cc3-4abd-48ec-bd01-8a39df77bf18.jsonl`
- `/ll:format-issue` - 2026-06-04T03:10:25 - `4276cd32-50a5-4188-b806-1ea69e9f0941.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
