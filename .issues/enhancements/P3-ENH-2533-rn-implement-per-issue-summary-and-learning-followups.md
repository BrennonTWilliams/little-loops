---
id: ENH-2533
type: ENH
priority: P3
status: open
captured_at: '2026-07-07T21:00:00Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- ENH-2530
decision_needed: false
labels:
- loops
- observability
---

# ENH-2533: rn-implement — per-issue outcomes and learning followups in summary.json

## Summary

Extend the `report` state in `scripts/little_loops/loops/rn-implement.yaml` so
`summary.json` contains structured per-issue outcomes and a
`learning_followups` list, instead of only bucketed counters.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposals 1 and 6). A 4-issue run
parked 3 issues for 3 distinct reasons, but `summary.json` reported only
`blocked: 2` / `learning_gate_blocked_pre_dequeue: 1`. Reconstructing *why*
each issue was parked required manually grepping `events.jsonl`, `failures.txt`,
and per-issue sidecar files.

## Current Behavior

`report` tallies counters from `blocked.txt`, `failures.txt`, `skipped.txt`,
etc. and writes a flat JSON of counts. Per-issue cause data already exists in
the run_dir as sidecars written by other states:

- `subloop_outcome_<ID>.txt` (IMPLEMENTED / MANUAL_REVIEW_NEEDED / MANUAL_REVIEW_RECOMMENDED / LEARNING_GATE_BLOCKED / ...)
- `pre_scores_<ID>.json` / `post_scores_<ID>.json`
- `convergence_<ID>.json`
- `learning_prove_attempted_<ID>.txt` / `learning_unproven_<ID>.txt`

None of this is aggregated; a subsequent run (or human) has no structured view
of why the previous run parked each issue.

## Expected Behavior

`summary.json` additionally contains:

```json
{
  "per_issue": [
    {"id": "ENH-400", "outcome": "MANUAL_REVIEW_RECOMMENDED",
     "reason": "options-missing", "pre_scores": {...}, "post_scores": {...}}
  ],
  "learning_followups": [
    {"id": "BUG-401", "targets": ["anthropic"],
     "remedy": "/ll:explore-api anthropic"}
  ]
}
```

Aggregation happens entirely in the `report` shell state by reading the
existing sidecars — no new writes needed from other states.

## Proposed Solution

- In `report`, glob `subloop_outcome_*.txt`, `pre_scores_*.json`,
  `post_scores_*.json`, `convergence_*.json`, `learning_unproven_*.txt` and
  assemble the two arrays with an inline python3 heredoc (jq is not a
  dependency).
- Include an `on_error:` route or fail-open echo so a malformed sidecar cannot
  crash the terminal report (MR-10: do not swallow parse errors silently —
  print a diagnostic line).
- Update the human-readable "=== rn-implement Complete ===" echo to mention
  followups count.
- Extend `scripts/tests/test_builtin_loops.py` coverage if it asserts the
  summary schema.

## Impact

- **Severity**: Medium (observability; unblocks audit-loop-run and follow-up runs)
- **Effort**: Small
- **Risk**: Low (additive schema change; report state only)
