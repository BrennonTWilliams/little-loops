---
id: BUG-2030
type: BUG
priority: P3
status: done
captured_at: '2026-06-08T00:00:00Z'
completed_at: '2026-06-09T01:03:34Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
- ENH-1293
confidence_score: 89
outcome_confidence: 75
score_complexity: 23
score_test_coverage: 10
score_ambiguity: 20
score_change_surface: 22
---

# BUG-2030: rn-implement `implement` state double-counts `implemented_count` on api_error_retry

## Summary

When the ENH-1293 `api_error_retry` mechanism fires after a successful `implement` action (exit 0 + verdict yes), the state is re-entered and `ll-auto --only <ID>` runs again. Since `ll-auto` exits 0 even when there are 0 issues to process (the issue is already done), the `implemented_count.txt` counter increments a second time. The final summary reports `Implemented: 3` for 2 issues processed.

## Current Behavior

Run: `rn-implement` / `2026-06-08T234012`
- ENH-1911 `implement` action: completed exit 0 (38.8 min), verdict yes
- `api_error_retry` fired (attempt 1, backoff 30s) — post-action API error during routing
- Second `implement` invocation: exited 0, "0 issues processed"
- `implemented_count.txt`: incremented twice → final value `3` (should be `2`)

## Steps to Reproduce

1. Start `rn-implement` loop with 2+ issues queued
2. An issue enters the `implement` state and completes successfully (exit 0, verdict yes)
3. A post-action API error triggers `api_error_retry` (ENH-1293 mechanism, backoff 30s)
4. The `implement` state is re-entered; `ll-auto --only <ID>` runs again
5. `ll-auto` exits 0 (0 issues processed — issue already `done`)
6. Observe: `implemented_count.txt` value is one higher than the number of issues actually implemented

## Expected Behavior

`implemented_count.txt` is incremented at most once per issue per loop run. Re-entering the `implement` state due to `api_error_retry` does not increment the counter if the issue was already counted in this run.

## Root Cause

`implement` state shell action:
```bash
if [ $EXIT_CODE -eq 0 ]; then
  COUNT=$(cat ".../implemented_count.txt" 2>/dev/null || echo 0)
  echo $((COUNT + 1)) > ".../implemented_count.txt"
fi
```

No idempotency guard — increments on any exit 0, including retries where the issue was already closed.

## Proposed Solution

Guard the counter increment with an idempotency check — either:
1. Track counted IDs in a `counted.txt` file in run_dir and skip if already present
2. Compare issue status before/after `ll-auto` and only increment on a status transition to `done`

Option 1 (counted.txt) is simpler and doesn't require an extra `ll-issues show` call:

```bash
ID="..."
ll-auto --only "$ID" 2>&1
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
  ALREADY_COUNTED=$(grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0)
  if [ "$ALREADY_COUNTED" -eq 0 ]; then
    COUNT=$(cat "${context.run_dir}/implemented_count.txt" 2>/dev/null || echo 0)
    echo $((COUNT + 1)) > "${context.run_dir}/implemented_count.txt"
    echo "$ID" >> "${context.run_dir}/counted.txt"
  fi
fi
```

## Acceptance Criteria

- [x] `implemented_count` is not inflated when the `implement` state is retried due to `api_error_retry`
- [x] An issue that was already `done` before the retry does not get double-counted
- [x] A fresh implementation (issue newly closed) is still counted exactly once
- [x] No regression to the sub-loop outcome token (`emit_implemented` still fires correctly)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `implement` state shell action (counter increment logic)

### Dependent Files (Callers/Importers)
- N/A — counter logic is self-contained within the YAML shell action

### Similar Patterns
- Other loop YAML files with counter increments — search for `implemented_count.txt` patterns to audit for the same vulnerability

### Tests
- TBD — no existing automated tests for `rn-implement` YAML; validate manually by simulating `api_error_retry` retry scenario

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Causes incorrect run summary stats but does not affect actual issue processing or loop correctness
- **Effort**: Small — Single targeted change to one shell action block in `rn-implement.yaml`
- **Risk**: Low — Isolated counter logic change; no effect on loop FSM transitions, issue outcomes, or `emit_implemented` token
- **Breaking Change**: No

## Labels

`loop`, `automation`, `idempotency`

## Status

**Open** | Created: 2026-06-08 | Priority: P3


## Resolution

Added idempotency guard to the `implement` state counter increment in `rn-remediate.yaml`. Uses a `counted.txt` file in `run_dir` to track which issue IDs have already been counted in the current run. On `api_error_retry` re-entry, the ID is found in `counted.txt` and the increment is skipped.

**Change**: `scripts/little_loops/loops/rn-remediate.yaml` — `implement` state shell action, lines 254-261.

## Session Log
- `/ll:ready-issue` - 2026-06-09T01:01:28 - `7a21239f-d687-45b5-806b-a7e465c237e0.jsonl`
- `/ll:format-issue` - 2026-06-09T00:50:18 - `bea10966-71b7-4204-8a23-f81e25338cef.jsonl`
- `/ll:confidence-check` - 2026-06-08T00:00:00Z - `eec350cd-8fcb-4138-9ae5-62a639e912c8.jsonl`
- `/ll:manage-issue` - 2026-06-09T01:03:34Z - fixed
