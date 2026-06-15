---
id: BUG-2170
title: rn-implement implemented_count.txt reports 1 for 4 actual implementations
priority: P3
type: BUG
status: open
captured_at: '2026-06-15T15:41:00Z'
discovered_date: '2026-06-15'
discovered_by: audit-loop-run
source_loop: rn-implement
source_state: report
affects: scripts/little_loops/loops/rn-remediate.yaml
labels:
- rn-implement
- rn-remediate
- telemetry
confidence_score: 83
outcome_confidence: 79
decision_needed: false
score_complexity: 21
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 22
---

# BUG-2170: rn-implement implemented_count.txt reports 1 for 4 actual implementations

## Summary

After a run of `rn-implement` that processed 5 issues and successfully implemented 4 (ENH-2157, ENH-2158, ENH-2159, ENH-2160), the session report showed `implemented: 1`. The `implemented_count.txt` file contained `1` and `counted.txt` contained only `ENH-2157`, despite all four `subloop_outcome_*.txt` files correctly containing `IMPLEMENTED`.

The counter is maintained by the `emit_implemented` state in `rn-remediate`, which uses a dedup-guard pattern:
```bash
ALREADY_COUNTED=$(grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0)
if [ "$ALREADY_COUNTED" -eq 0 ]; then
  COUNT=$(cat "${context.run_dir}/implemented_count.txt" 2>/dev/null || echo 0)
  echo $((COUNT + 1)) > "${context.run_dir}/implemented_count.txt"
  echo "$ID" >> "${context.run_dir}/counted.txt"
fi
```

The sub-loops for ENH-2158–2160 ran `emit_implemented` successfully (exit 0, ~14ms each), wrote their `subloop_outcome_*.txt` files correctly, but did NOT append to `counted.txt` or update `implemented_count.txt`. The root cause is not yet confirmed from event data — possible causes include a path resolution mismatch between the first write (`subloop_outcome`) and the counter writes, or a silent shell conditional failure.

## Current Behavior

- Run: `2026-06-15T143021-rn-implement`
- `implemented_count.txt`: `1`
- `counted.txt`: `ENH-2157` (1 entry)
- `subloop_outcome_ENH-2157.txt` through `subloop_outcome_ENH-2160.txt`: all `IMPLEMENTED`
- Session report: `implemented: 1, total_processed: 5, sub_loop_crashes: 1`
- Actual implemented: 4

## Expected Behavior

`implemented_count.txt` = 4, `counted.txt` has 4 entries, report shows `implemented: 4`.

## Steps to Reproduce

1. Queue 4+ issues for `rn-implement` (e.g., ENH-2157 through ENH-2160)
2. Run the `rn-implement` loop: `ll-loop run rn-implement`
3. Wait for all sub-loops to complete — each reaching the `emit_implemented` state in `rn-remediate` with exit 0
4. Inspect the run directory: `cat .loops/runs/rn-implement-<timestamp>/implemented_count.txt` and `cat .loops/runs/rn-implement-<timestamp>/counted.txt`
5. Observe: `implemented_count.txt` = `1`, `counted.txt` has 1 entry, despite all `subloop_outcome_*.txt` files containing `IMPLEMENTED`

## Acceptance Criteria

1. Root cause identified: determine why the counter increment runs for ENH-2157 but not ENH-2158–2160 despite `emit_implemented` completing with exit 0 for all four.
2. Fix ensures `implemented_count.txt` accurately reflects the number of issues where `emit_implemented` ran.
3. Alternative: modify the `report` state in `rn-implement` to count `subloop_outcome_*.txt` files containing IMPLEMENTED as the authoritative source, rather than relying on `implemented_count.txt`.
4. Add a test or assertion that verifies the counter matches the file count after a multi-issue run.
5. Add test in `scripts/tests/test_rn_implement.py:TestSubLoopDelegation` asserting `run_dir` is in `run_remediation`'s `with:` bindings (model after `test_run_decomposition_has_with_bindings`).

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Anchor**: `emit_implemented` state (shell action)
- **Cause**: The `grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0` pattern produces double output. When `counted.txt` exists but `$ID` is not in it, `grep -c` outputs `0` to stdout AND exits 1, triggering `|| echo 0`. `ALREADY_COUNTED` captures `"0\n0"`, which fails the `[ "$ALREADY_COUNTED" -eq 0 ]` integer comparison — silently skipping the counter increment for all sub-loops after the first. (The `run_dir` path is already correctly propagated via `with: run_dir: "${captured.run_dir.output}"` at `rn-implement.yaml:504`.)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/fsm/executor.py:_execute_sub_loop()` (~lines 559–589): applies `with:` bindings as `child_fsm.context = {**child_fsm.context, **resolved}`, then uses `child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])` as a fallback. If `run_dir` is explicit in `with:`, the `with:` value wins and `setdefault` is a no-op.
- `scripts/little_loops/loops/rn-implement.yaml` `init` state: captures `run_dir` via `echo "$RUN_DIR"` + `capture: run_dir` — value is set once and stable across all sub-loop invocations; `${captured.run_dir.output}` resolves to the same path on every `run_remediation` call.
- **Critical discrepancy**: `subloop_outcome_*.txt` for ENH-2158–2160 were written correctly — these writes occur in the same shell action as the counter increment, on earlier lines, using the same `${context.run_dir}` reference. This proves the path resolved to a writable directory at that point in the script. The counter increment block runs later in the same shell process; if the path were wrong, the outcome write would also have failed.
- **Remaining suspect — shell early exit**: the `grep -cxF "$ID" ... 2>/dev/null || echo 0` pipeline exits 1 (no match found) before `|| echo 0` fires if the shell runs with implicit `set -e` and the `||` is not sufficient to suppress propagation. Alternatively, the `if [ "$ALREADY_COUNTED" -eq 0 ]` test could silently evaluate to false due to a whitespace artifact in `ALREADY_COUNTED`.
- **Test coverage gap**: `TestSubLoopDelegation.test_run_remediation_has_with_bindings` in `scripts/tests/test_rn_implement.py` does NOT assert `run_dir` is in `run_remediation`'s `with:` bindings. The parallel test `test_run_decomposition_has_with_bindings` DOES assert `run_dir` for `run_decomposition`. If `run_dir` were accidentally removed from `run_remediation`'s `with:`, the executor's `setdefault` fallback would inject the parent path silently — and no test would catch the regression.

## Proposed Solution

**Option A (Preferred)**:
> **Selected:** Option A — Fix the emit_implemented counter logic; root cause is the grep -cxF double-output bug, not run_dir propagation (which is already correct).

Fix `run_dir` propagation in `emit_implemented` state of `rn-remediate.yaml`.

Verify that `with: run_dir: "${captured.run_dir.output}"` passes the **outer loop's** `run_dir` (set once at `rn-implement` start) to each sub-loop invocation. If `captured.run_dir.output` is resolving to a per-sub-loop directory instead, change the delegation to thread the outer loop's `run_dir` consistently across all four sub-loops.

**Option B (Fallback)**: Replace the counter in the `report` state of `rn-implement.yaml` with a direct file-count:

```bash
IMPLEMENTED=$(find "${context.run_dir}" -name "subloop_outcome_*.txt" | xargs grep -lx "IMPLEMENTED" 2>/dev/null | wc -l)
```

This reads ground truth from the outcome files rather than trusting the counter, eliminating the path-resolution dependency.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-15.

**Selected**: Option A — Fix the `emit_implemented` counter logic in `rn-remediate.yaml`

**Reasoning**: Codebase evidence confirms `run_dir` IS already correctly propagated via `with: run_dir: "${captured.run_dir.output}"` in `run_remediation` (rn-implement.yaml:504) — Option A's stated hypothesis is already the current state. The actual root cause is the `grep -cxF "$ID" counted.txt 2>/dev/null || echo 0` double-output bug in `emit_implemented`: when `counted.txt` exists but `$ID` isn't in it, `grep -c` outputs `0` AND exits 1, triggering `|| echo 0`, so `ALREADY_COUNTED` captures `"0\n0"` — causing `[ "$ALREADY_COUNTED" -eq 0 ]` to fail the integer comparison for ENH-2158–2160. Option B introduces a `find | xargs grep -lx | wc -l` pipeline with zero precedent in any loop YAML, breaks the existing `test_report_state_writes_summary_json` assertion (`"implemented_count.txt" in action`), and creates asymmetry with `decomposed_count.txt` which has no file-count equivalent.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (fix emit_implemented counter logic) | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B (replace counter with find \| wc -l in report) | 2/3 | 2/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- **Option A FOR**: `run_decomposition` uses identical `with: run_dir:` pattern and works correctly (rn-implement.yaml:565); `TestCounterIncrementInEmitImplemented` class in test_rn_remediate.py provides existing test infrastructure; fix is one-line change from `grep -cxF ... || echo 0` to `grep -qxF`
- **Option B AGAINST**: `test_report_state_writes_summary_json` (test_rn_implement.py:365) asserts `"implemented_count.txt" in action` and must be updated; `decomposed_count.txt` has no file-count equivalent creating report asymmetry; `find | xargs grep -lx | wc -l` pipeline has zero precedent across all loop YAMLs

## Diagnosis Hints

- Compare the shell expansion of `${context.run_dir}` across sub-loop iterations — if it resolves to different paths for the counter writes vs the `subloop_outcome` write, the counter silently writes to a non-existent or wrong directory.
- Check whether `emit_implemented` for ENH-2158 uses a different `context.run_dir` value than ENH-2157 (e.g., if `run_dir` is captured from the sub-loop rather than the outer loop).
- The `with: run_dir: "${captured.run_dir.output}"` delegation is the expected path — verify the materialized value matches the actual run_dir for all 4 sub-loop invocations.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml` — `emit_implemented` state: the counter/dedup-guard shell action; primary fix target for Option A
- `scripts/little_loops/loops/rn-implement.yaml` — `report` state: replace `implemented_count.txt` read with `find ... | wc -l` file-count for Option B

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/rn-implement.yaml` — `init` state: initializes `implemented_count.txt` to `0` and captures `run_dir` via `capture: run_dir`
- `scripts/little_loops/loops/rn-implement.yaml` — `run_remediation` state: invokes `rn-remediate` with `with: run_dir: "${captured.run_dir.output}"`
- `scripts/little_loops/loops/rn-implement.yaml` — `classify_remediation` state: reads `subloop_outcome_*.txt` via `${captured.run_dir.output}`
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()` (~lines 559–589): applies `with:` bindings then `setdefault("run_dir", self.fsm.context["run_dir"])` fallback
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` (line 162): injects top-level `run_dir` into parent FSM context on startup

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` — `run_decomposition` state: correct `with: run_dir: "${captured.run_dir.output}"` pattern to model after
- `scripts/little_loops/loops/rn-decompose.yaml` — `parameters.run_dir` block: reference declaration of `run_dir` as a required parameter (same contract as `rn-remediate`)
- `scripts/little_loops/loops/lib/common.yaml` — fragment `subloop_rate_limit_diagnostic`: alternate token-write pattern using `${param.run_dir}` (for fragment contexts)

### Tests
- `scripts/tests/test_rn_remediate.py` — class `TestCounterIncrementInEmitImplemented`: asserts counter/dedup guard in `emit_implemented`
- `scripts/tests/test_rn_remediate.py` — class `TestOutcomeTokenChannel`: asserts `subloop_outcome_*.txt` written to `${context.run_dir}`
- `scripts/tests/test_rn_implement.py` — `TestSubLoopDelegation.test_run_remediation_has_with_bindings`: **does NOT assert `run_dir` in `with:` bindings** — test gap to fix
- `scripts/tests/test_rn_implement.py` — `TestSubLoopDelegation.test_run_decomposition_has_with_bindings`: model test asserting `run_dir` in `with:` for `run_decomposition`
- `scripts/tests/test_builtin_loops.py` — integration tests for multi-issue `rn-implement` runs (add counter == IMPLEMENTED file count assertion)

### Documentation
- `docs/guides/LOOPS_REFERENCE.md` — documents `rn-implement`, `rn-remediate`, `rn-decompose` architectures and counter patterns

## Implementation Steps

1. In `scripts/little_loops/loops/rn-remediate.yaml` `emit_implemented` state (~line 609): replace the `ALREADY_COUNTED=$(grep -cxF ...)` + integer-comparison `if` block with a direct quiet-grep guard:
   ```bash
   # Before (buggy — double output when ID absent):
   ALREADY_COUNTED=$(grep -cxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null || echo 0)
   if [ "$ALREADY_COUNTED" -eq 0 ]; then
   # After:
   if ! grep -qxF "$ID" "${context.run_dir}/counted.txt" 2>/dev/null; then
   ```
   The three inner lines (`COUNT=`, `echo $((COUNT + 1))`, `echo "$ID" >>`) remain unchanged.
2. In `scripts/tests/test_rn_remediate.py:TestCounterIncrementInEmitImplemented` (~line 1108): add a test asserting `grep -qxF` (not `grep -cxF`) appears in `emit_implemented`'s action — model after `test_emit_implemented_uses_run_dir_for_counter` at ~line 1145.
3. In `scripts/tests/test_rn_implement.py:TestSubLoopDelegation.test_run_remediation_has_with_bindings` (lines 246-253): add `assert with_bindings["run_dir"] == "${captured.run_dir.output}"` — model after `test_run_decomposition_has_with_bindings` at lines 298-304.
4. (Optional / AC4) In `scripts/tests/test_builtin_loops.py`: add assertion that the counter value in `implemented_count.txt` equals the count of `subloop_outcome_*.txt` files containing `IMPLEMENTED` after a multi-issue run.
5. Validate: `python -m pytest scripts/tests/test_rn_remediate.py scripts/tests/test_rn_implement.py -v` — all tests pass including the new dedup-guard test.

## Impact

- **Priority**: P3 — Telemetry inaccuracy in session reports; does not block issue implementation but misreports progress
- **Effort**: Small — Likely a one-line fix in `rn-remediate.yaml` or `rn-implement.yaml`; no FSM engine changes required
- **Risk**: Low — Fix is confined to counter logic in loop YAML; no changes to Python core or shared state
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-15 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-15_

**Readiness Score**: 83/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- ~~Root cause was TBD~~ — **Root cause now confirmed** (updated by `/ll:refine-issue` 2026-06-15): the `grep -cxF` double-output bug in `emit_implemented`. `run_dir` propagation is correct. Implementation steps have been updated to reflect the confirmed fix.
- AC1 (root cause identification) is satisfied. Proceed directly to applying the fix in Implementation Step 1.

## Session Log
- `/ll:refine-issue` - 2026-06-15T17:02:53 - `bffefeb0-fbda-400c-89f6-f9e3c1696323.jsonl`
- `/ll:decide-issue` - 2026-06-15T16:57:22 - `c31adb30-3c6b-4940-9ce0-5ccae335bee1.jsonl`
- `/ll:refine-issue` - 2026-06-15T16:43:28 - `3b3e7dff-d0aa-440f-841c-9a9413d063e2.jsonl`
- `/ll:format-issue` - 2026-06-15T16:01:02 - `6af8e5ab-bf71-4158-bd83-ace02f8dce6e.jsonl`
- `/ll:confidence-check` - 2026-06-15T00:00:00Z - `ba516de3-ccc4-4cfe-8e0b-52004dc88302.jsonl`
- `/ll:confidence-check` - 2026-06-15T17:30:00Z - `a8588f62-8142-4c3e-8508-a7bb5ac8275f.jsonl`
