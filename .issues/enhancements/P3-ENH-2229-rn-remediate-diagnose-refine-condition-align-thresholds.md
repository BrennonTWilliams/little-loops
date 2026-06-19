---
id: ENH-2229
title: "rn-remediate: align diagnose REFINE condition to readiness/outcome thresholds"
type: ENH
priority: P3
status: done
completed_at: "2026-06-19T18:14:22Z"
---

## Summary

The `diagnose` state in `rn-remediate.yaml` routed to `REFINE` when complexity was
high **or** `confidence < diagnose_confidence_floor` (hardcoded at 50). This floor
was lower than the actual readiness threshold (85) used everywhere else in the loop,
so issues with confidence in the 50–84 range could bypass refine and proceed toward
`DECOMPOSE` or `REFINE_LIGHT` when they should have been refined.

## Change

Updated the REFINE branch condition in `diagnose` (Phase 2) from:

```bash
elif [ "$COMPLEXITY" -ge "${context.diagnose_complexity_threshold}" ] \
    || [ "$CONFIDENCE" -lt "${context.diagnose_confidence_floor}" ]; then
  echo "REFINE"
```

To:

```bash
elif [ "$COMPLEXITY" -ge "${context.diagnose_complexity_threshold}" ] \
    || [ "$CONFIDENCE" -lt "${context.readiness_threshold}" ] \
    || [ "$OUTCOME" -lt "${context.outcome_threshold}" ]; then
  echo "REFINE"
```

The `diagnose_confidence_floor` context variable (default 50) is no longer
referenced by this condition. The condition now uses the canonical loop thresholds
(`readiness_threshold: 85`, `outcome_threshold: 75`) so `diagnose` routing agrees
with `check_readiness` and `check_convergence` under any threshold override.

## Files Changed

- `scripts/little_loops/loops/rn-remediate.yaml` — REFINE routing condition in `diagnose` state


## Session Log
- `hook:posttooluse-status-done` - 2026-06-19T18:14:46 - `775e908c-0906-4100-b0b5-1ff22a869756.jsonl`
