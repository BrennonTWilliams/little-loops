---
captured_at: '2026-06-04T23:09:17Z'
completed_at: '2026-06-04T23:28:53Z'
discovered_date: 2026-06-04
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-1950: dequeue_next pipeline fallback fails when depth_map.txt is missing

## Summary

The `dequeue_next` state in the `rn-implement` loop has a bash pipeline fallback bug. When extracting an issue's depth from `depth_map.txt`, the `|| echo "0"` fallback applies to `awk` (the last command in the pipeline), not `grep`. On the first dequeue (or any dequeue where the issue isn't in the depth map), `grep` exits non-zero but `awk` on empty input exits 0 — so the fallback never fires. `DEPTH` is set to an empty string, which is written to `current_depth.txt`. When `check_depth` reads the empty file and echoes a blank line, its `output_numeric` evaluator fails with `"Cannot parse as number"`, crashing the loop.

## Current Behavior

```bash
# dequeue_next action (broken)
DEPTH=$(grep "^$CURRENT " "$DEPTH_MAP" 2>/dev/null | awk '{print $2}' || echo "0")
```

When `depth_map.txt` doesn't exist (first dequeue):
- `grep` exits 2 (file not found, stderr → /dev/null)
- `awk` on empty input exits 0 (success)
- The `|| echo "0"` applies to `awk`'s exit code (0), so it does NOT fire
- `DEPTH=""` (empty string)
- `echo "" > current_depth.txt` writes a blank line
- `check_depth` reads blank line → `output_numeric` fails: `"Cannot parse as number"`

Shell reproduction confirms:

```
$ DEPTH=$(grep "^ENH-1945 " "/nonexistent/depth_map.txt" 2>/dev/null | awk '{print $2}' || echo "0")
$ echo "DEPTH=[$DEPTH]"
DEPTH=[]       ← empty, not "0"
```

## Expected Behavior

When `depth_map.txt` is missing or the issue has no depth entry, `DEPTH` should default to `"0"`, and `check_depth` should receive a valid numeric value (`0 < max_depth` → route to `run_remediation`).

## Steps to Reproduce

1. Run `ll-loop run rn-implement "<any-issue-id>"` with an empty run history (no pre-existing `depth_map.txt`)
2. Observe `init` succeeds, `dequeue_next` succeeds (with the `>&2` fix from d1d2bc5e active)
3. Observe `check_depth` fails: `output_numeric` evaluator returns `"Cannot parse as number"`

## Root Cause

- **File**: `scripts/little_loops/loops/rn-implement.yaml`
- **Anchor**: state `dequeue_next`, action body lines 6–7
- **Cause**: Bash pipeline `cmd1 | cmd2 || fallback` — the `||` operator applies to the exit status of the last command in the pipeline (`awk`), not the first (`grep`). Since `awk` on empty stdin exits 0, the fallback is unreachable when `grep` fails. This is a standard bash pitfall. The fix is to check `$PIPESTATUS[0]` or restructure to avoid relying on pipeline exit status for the grep result.

## Proposed Solution

**Option A — explicit empty check (simplest)**:
```bash
DEPTH=$(grep "^$CURRENT " "$DEPTH_MAP" 2>/dev/null | awk '{print $2}')
DEPTH=${DEPTH:-0}
```

**Option B — pipefail with explicit fallback**:
```bash
DEPTH=$(set -o pipefail; grep "^$CURRENT " "$DEPTH_MAP" 2>/dev/null | awk '{print $2}' || echo "0")
```

**Recommendation**: Option A — it's idiomatic, doesn't require a subshell, and makes the intent explicit.

## Implementation Steps

1. Edit `scripts/little_loops/loops/rn-implement.yaml` — replace the `DEPTH=$(grep ... | awk ... || echo "0")` line in `dequeue_next` with the two-line Option A pattern
2. Verify the fix: `bash -c 'DEPTH=$(grep "^FOO " /nonexistent 2>/dev/null | awk '"'"'{print $2}'"'"'); DEPTH=${DEPTH:-0}; echo "[$DEPTH]"'` → outputs `[0]`
3. Run `ll-loop validate rn-implement` to confirm no schema violations
4. Run `ll-loop run rn-implement "<test-issue>"` to confirm `check_depth` receives numeric input

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `dequeue_next` state, action body

### Dependent Files (Callers/Importers)
- N/A (loop YAML, no code imports)

### Similar Patterns
- The same `grep ... | awk ... || echo "0"` pattern appears in `dequeue_next` only; no other loop YAML files use this pattern based on the resolved config

### Tests
- `scripts/tests/test_builtin_loops.py` — may need a regression test for empty depth_map.txt scenario

### Documentation
- N/A

### Configuration
- N/A

## Motivation

This bug silently breaks the `rn-implement` loop on its FIRST dequeue of every run. Without the fix, the loop can never reach `check_depth` or any productive state (it either fails at `dequeue_next` from the separate `run_dir` capture corruption, or if that's fixed, fails at `check_depth` from this bug). The `rn-implement` loop is the queue orchestrator for the recursive plan-and-implement workflow — it's a critical path component.

## Impact

- **Priority**: P2 — Runtime failure that blocks the `rn-implement` loop from processing any issues
- **Effort**: Small — One-line fix in a YAML file
- **Risk**: Low — The fix is a well-understood bash idiom; no change to loop topology or routing
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `loops`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-04T23:20:47 - `6c496b7a-95d9-436e-9b45-c5133f828bfc.jsonl`
- `/ll:format-issue` - 2026-06-04T23:12:17 - `47aa587d-6c0f-4941-b880-b37184474217.jsonl`
- `/ll:capture-issue` - 2026-06-04T23:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9de5a8f-5fed-40f9-b3a5-a5902a7ec3e8.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:14:15Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1c3059c-1426-42f0-8eec-cf5e5d2303ea.jsonl`
- `/ll:manage-issue` - 2026-06-04T23:28:53Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb9b6c11-854a-4eb4-97ba-3bf5f6c2f6bc.jsonl`

## Resolution

**Applied fix**: Replaced the broken pipeline fallback `|| echo "0"` with `DEPTH=${DEPTH:-0}` in `rn-implement.yaml` dequeue_next state (Option A from proposed solutions). This is a standard bash idiom that correctly defaults DEPTH to "0" when the grep/awk pipeline produces empty output (missing depth_map.txt or issue not present).

**Verification**:
- Shell reproduction confirms both failure modes now produce `DEPTH=[0]`
- `ll-loop validate rn-implement` passes (11 states, schema valid)
- Full test suite: 9,858 passed, 0 failed

## Status

**Open** | Created: 2026-06-04 | Priority: P2
