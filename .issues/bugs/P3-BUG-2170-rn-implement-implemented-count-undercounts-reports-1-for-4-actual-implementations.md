---
id: BUG-2170
title: "rn-implement implemented_count.txt reports 1 for 4 actual implementations"
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

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Anchor**: `emit_implemented` state (shell action)
- **Cause**: TBD — `${context.run_dir}` in the `emit_implemented` shell block likely resolves to a different path for sub-loops ENH-2158–2160 than for ENH-2157. The first sub-loop writes `implemented_count.txt` and `counted.txt` successfully; subsequent sub-loops likely write to a non-overlapping `run_dir`, so the dedup-guard reads the file fresh each time and starts from 0, overwriting instead of incrementing. The `with: run_dir: "${captured.run_dir.output}"` delegation is the primary suspect.

## Proposed Solution

**Option A (Preferred)**: Fix `run_dir` propagation in `emit_implemented` state of `rn-remediate.yaml`.

Verify that `with: run_dir: "${captured.run_dir.output}"` passes the **outer loop's** `run_dir` (set once at `rn-implement` start) to each sub-loop invocation. If `captured.run_dir.output` is resolving to a per-sub-loop directory instead, change the delegation to thread the outer loop's `run_dir` consistently across all four sub-loops.

**Option B (Fallback)**: Replace the counter in the `report` state of `rn-implement.yaml` with a direct file-count:

```bash
IMPLEMENTED=$(find "${context.run_dir}" -name "subloop_outcome_*.txt" | xargs grep -lx "IMPLEMENTED" 2>/dev/null | wc -l)
```

This reads ground truth from the outcome files rather than trusting the counter, eliminating the path-resolution dependency.

## Diagnosis Hints

- Compare the shell expansion of `${context.run_dir}` across sub-loop iterations — if it resolves to different paths for the counter writes vs the `subloop_outcome` write, the counter silently writes to a non-existent or wrong directory.
- Check whether `emit_implemented` for ENH-2158 uses a different `context.run_dir` value than ENH-2157 (e.g., if `run_dir` is captured from the sub-loop rather than the outer loop).
- The `with: run_dir: "${captured.run_dir.output}"` delegation is the expected path — verify the materialized value matches the actual run_dir for all 4 sub-loop invocations.

## Implementation Steps

1. Reproduce: run `rn-implement` with 4 issues and confirm `implemented_count.txt` = 1
2. Log the materialized `context.run_dir` for each sub-loop invocation of `emit_implemented`; compare across ENH-2157 vs ENH-2158 to confirm path divergence
3. Apply Option A: fix `with: run_dir:` in `rn-remediate.yaml` to thread the outer run_dir correctly
4. If Option A does not resolve it, apply Option B: replace counter with `subloop_outcome_*.txt` file-count in `rn-implement.yaml` `report` state
5. Validate: re-run `rn-implement` with 4 issues and confirm report shows `implemented: 4`
6. Add assertion or test verifying counter == IMPLEMENTED file count after multi-issue run

## Impact

- **Priority**: P3 — Telemetry inaccuracy in session reports; does not block issue implementation but misreports progress
- **Effort**: Small — Likely a one-line fix in `rn-remediate.yaml` or `rn-implement.yaml`; no FSM engine changes required
- **Risk**: Low — Fix is confined to counter logic in loop YAML; no changes to Python core or shared state
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-15 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-15T16:01:02 - `6af8e5ab-bf71-4158-bd83-ace02f8dce6e.jsonl`
