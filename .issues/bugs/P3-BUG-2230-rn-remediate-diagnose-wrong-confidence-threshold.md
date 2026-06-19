---
id: BUG-2230
title: "rn-remediate diagnose routes REFINE with wrong confidence threshold"
type: BUG
priority: P3
status: done
captured_at: "2026-06-19T20:23:17Z"
discovered_date: 2026-06-19
discovered_by: capture-issue
completed_at: "2026-06-19T20:23:17Z"
---

# BUG-2230: rn-remediate diagnose routes REFINE with wrong confidence threshold

## Summary

The `diagnose` state in `rn-remediate.yaml` compared `CONFIDENCE` against
`${context.readiness_threshold}` (default 85 — the IMPLEMENT gate) in the
combined REFINE routing condition instead of `${context.diagnose_confidence_floor}`
(default 50 — the diagnose-specific lower floor). This caused issues with
confidence scores between 50–84 to route correctly in some cases but made the
routing logic semantically wrong and broke the regression test.

## Root Cause

- **File**: `scripts/little_loops/loops/rn-remediate.yaml`
- **Line**: 258
- **Function/anchor**: `diagnose` state `action` shell script

The combined REFINE elif branch read:

```bash
elif [ "$COMPLEXITY" -ge "${context.diagnose_complexity_threshold}" ] || [ "$CONFIDENCE" -lt "${context.readiness_threshold}" ] || [ "$OUTCOME" -lt "${context.outcome_threshold}" ]; then
```

`${context.readiness_threshold}` is the high-water mark for routing to IMPLEMENT
(checked on line 241). Using it again as a lower-bound REFINE floor conflates two
distinct thresholds. `${context.diagnose_confidence_floor}` (50) was already
defined in the loop's default context for this purpose but was not wired into the
action.

## Fix

One-line change in `rn-remediate.yaml:258` — replace `${context.readiness_threshold}`
with `${context.diagnose_confidence_floor}` in the CONFIDENCE comparison:

```bash
elif [ "$COMPLEXITY" -ge "${context.diagnose_complexity_threshold}" ] || [ "$CONFIDENCE" -lt "${context.diagnose_confidence_floor}" ] || [ "$OUTCOME" -lt "${context.outcome_threshold}" ]; then
```

## Discovered By

Failing test surfaced during `/ll:run-tests unit`:
`scripts/tests/test_rn_remediate.py::TestBug2007Fixes::test_diagnose_uses_context_thresholds_not_literals`

## Session Log
- `hook:posttooluse-status-done` - 2026-06-19T20:23:39 - `01258524-4106-40bc-a149-3fbaf5f92fdb.jsonl`
- `/ll:capture-issue` - 2026-06-19T20:23:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01258524-4106-40bc-a149-3fbaf5f92fdb.jsonl`

---

## Status

**done** — fixed in this session (2026-06-19). All 3 `TestBug2007Fixes` tests pass.
